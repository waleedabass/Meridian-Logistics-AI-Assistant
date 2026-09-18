"""Ingest every PDF in corpus/ and write data/index.json.

    python -m app.ingest

Steps
  1. Extract positioned blocks per page (text layer, tables, or OCR for scans).
  2. Collapse boilerplate: a paragraph repeated 3+ times inside the same document is
     kept once, in a single "standard provisions" chunk, instead of 100 times.
     (operations_manual_full.pdf is 67 pages; 982 of its 1,048 blocks are repeats.)
  3. Split each document into sections on its numbered headings. A section is the
     retrieval / citation unit; every character keeps its source page, so a citation
     can point at the exact page even when a section spans a page break.
  4. Detect document versions: documents sharing a title (e.g. the 2024 and 2025
     employee handbooks) are grouped and all but the newest are marked superseded.
"""
from __future__ import annotations

import collections
import json
import re
import sys
import time
from pathlib import Path

from app.config import CORPUS_DIR, INDEX_PATH
from app.pdf_extract import Block, SpaceRepairer, extract_pdf, text_layer_vocab

HEADING = re.compile(r"^(\d{1,2})\s*\.\s+\S.{0,70}$")
SUBNUMBER = re.compile(r"^\d+\.\d+$")  # bare "10.1" labels in the operations manual
BOILERPLATE_MIN_REPEATS = 3
MAX_SECTION_CHARS = 4000


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def is_heading(b: Block) -> bool:
    return b.kind != "table" and "\n" not in b.text and bool(HEADING.match(b.text))


# --------------------------------------------------------------------------- versions
def doc_year(meta_line: str, filename: str) -> int | None:
    years = [int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", meta_line)]
    if not years:
        years = [int(y) for y in re.findall(r"(19\d\d|20\d\d)", filename)]
    return max(years) if years else None


def assign_versions(docs: list[dict]) -> None:
    families = collections.defaultdict(list)
    for d in docs:
        families[norm(d["title"])].append(d)
    for members in families.values():
        for d in members:
            d["status"], d["superseded_by"], d["other_versions"] = "current", None, []
        if len(members) < 2:
            continue
        members.sort(key=lambda d: d["year"] or 0)
        newest = members[-1]
        for d in members:
            d["other_versions"] = [m["file"] for m in members if m is not d]
        for d in members[:-1]:
            d["status"], d["superseded_by"] = "superseded", newest["file"]


# --------------------------------------------------------------------------- chunks
class ChunkBuilder:
    """Accumulates blocks into one chunk while remembering which page each char came from."""

    def __init__(self, doc: str, section: str, kind: str = "section"):
        self.doc, self.section, self.kind = doc, section, kind
        self.parts: list[str] = []
        self.spans: list[dict] = []
        self.length = 0

    def add(self, b: Block) -> None:
        if self.parts:
            self.parts.append("\n")
            self.length += 1
        self.spans.append({"start": self.length, "end": self.length + len(b.text), "page": b.page})
        self.parts.append(b.text)
        self.length += len(b.text)

    @property
    def text(self) -> str:
        return "".join(self.parts)

    def to_dict(self, cid: str, **extra) -> dict:
        pages = sorted({s["page"] for s in self.spans})
        return {"id": cid, "doc": self.doc, "section": self.section, "kind": self.kind,
                "text": self.text, "pages": pages, "spans": self.spans, **extra}


def build_document(path: Path, repairer: SpaceRepairer) -> tuple[dict, list[ChunkBuilder]]:
    blocks, report = extract_pdf(str(path), repairer)

    # ---- boilerplate collapse (within this document only: identical text in two
    # different documents, e.g. two handbook versions, is legitimately separate)
    counts = collections.Counter(norm(b.text) for b in blocks if not is_heading(b))
    repeated = {t for t, c in counts.items() if c >= BOILERPLATE_MIN_REPEATS and len(t) > 40}
    boiler = ChunkBuilder(path.name, "Standard provisions repeated throughout this document", "boilerplate")
    seen_boiler: set[str] = set()
    boiler_pages: set[int] = set()
    kept: list[Block] = []
    removed = 0
    for b in blocks:
        t = norm(b.text)
        if SUBNUMBER.match(b.text.strip()):
            removed += 1
            continue
        if t in repeated:
            boiler_pages.add(b.page)
            if t not in seen_boiler:
                seen_boiler.add(t)
                boiler.add(b)
            else:
                removed += 1
            continue
        kept.append(b)

    title = kept[0].text.split("\n")[0].strip() if kept else path.stem
    meta_line = kept[1].text.split("\n")[0].strip() if len(kept) > 1 else ""

    # ---- sections
    sections: list[ChunkBuilder] = [ChunkBuilder(path.name, "Document header")]
    toc_page = None
    for b in kept:
        if norm(b.text) == "contents":
            toc_page = b.page
        in_toc = toc_page is not None and b.page == toc_page
        if is_heading(b) and not in_toc:
            sections.append(ChunkBuilder(path.name, b.text.strip()))
        sections[-1].add(b)
    # drop headings whose whole body was boilerplate (e.g. "13. Fleet Maintenance")
    empty_sections = [s.section for s in sections if len(s.spans) <= 1 and s.section != "Document header"]
    sections = [s for s in sections if len(s.spans) > 1 or s.section == "Document header"]
    if seen_boiler:
        sections.append(boiler)

    # ---- split very long sections on block boundaries
    final: list[ChunkBuilder] = []
    for s in sections:
        if s.length <= MAX_SECTION_CHARS:
            final.append(s)
            continue
        part = ChunkBuilder(s.doc, s.section, s.kind)
        for span in s.spans:
            blk = Block(text=s.text[span["start"]:span["end"]], page=span["page"], y=0)
            if part.length + len(blk.text) > MAX_SECTION_CHARS and part.spans:
                final.append(part)
                part = ChunkBuilder(s.doc, s.section + " (cont.)", s.kind)
            part.add(blk)
        final.append(part)

    doc = {
        "file": path.name,
        "title": title,
        "meta_line": meta_line,
        "year": doc_year(meta_line, path.name),
        "pages": report["pages"],
        "ocr_pages": report["ocr_pages"],
        "tables": report["tables"],
        "blocks_extracted": len(blocks),
        "blocks_removed_as_duplicates": removed,
        "boilerplate_paragraphs": len(seen_boiler),
        "boilerplate_pages": sorted(boiler_pages),
        "sections_only_boilerplate": empty_sections,
        "ocr_min_confidence": min((b.meta.get("ocr_min_confidence", 1.0) for b in blocks), default=None)
        if report["ocr_pages"] else None,
    }
    return doc, final


def run(corpus_dir: Path = CORPUS_DIR, index_path: Path = INDEX_PATH) -> dict:
    t0 = time.time()
    pdfs = sorted(corpus_dir.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs found in {corpus_dir}")
    repairer = SpaceRepairer(text_layer_vocab([str(p) for p in pdfs]))

    docs, chunks = [], []
    for p in pdfs:
        doc, builders = build_document(p, repairer)
        ids = []
        for b in builders:
            cid = f"C{len(chunks) + 1:02d}"
            chunks.append(b.to_dict(cid))
            ids.append(cid)
        doc["chunk_ids"] = ids
        docs.append(doc)
        extra = f" OCR pages {doc['ocr_pages']}" if doc["ocr_pages"] else ""
        print(f"  {p.name:36s} pages={doc['pages']:3d} chunks={len(ids):2d} "
              f"tables={doc['tables']} dup_removed={doc['blocks_removed_as_duplicates']}{extra}")

    assign_versions(docs)
    for d in docs:
        if d["status"] == "superseded":
            print(f"  {d['file']} is superseded by {d['superseded_by']}")

    index = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus_files": {p.name: p.stat().st_mtime for p in pdfs},
        "documents": docs,
        "chunks": chunks,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    total_chars = sum(len(c["text"]) for c in chunks)
    print(f"Indexed {len(docs)} documents, {len(chunks)} chunks, {total_chars:,} chars "
          f"(~{total_chars // 4:,} tokens) in {time.time() - t0:.1f}s -> {index_path}")
    return index


if __name__ == "__main__":
    run()
