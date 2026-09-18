# Builds data/index.json from the pdfs in corpus/
# run with: python -m app.ingest
#
# What it does:
# 1. pulls text out of each pdf (see pdf_extract.py)
# 2. removes repeated boilerplate. The operations manual is 67 pages but almost
#    everything is the same ~10 paragraphs over and over, so we keep one copy
# 3. splits documents into sections using the numbered headings ("4. Annual Leave")
# 4. marks old versions of a document as superseded (handbook 2024 vs 2025)

import json
import re
import sys
import time
from collections import Counter

from app.config import CORPUS_DIR, INDEX_PATH
from app.pdf_extract import Block, SpaceFixer, extract_pdf, get_known_words

HEADING_RE = re.compile(r"^(\d{1,2})\s*\.\s+\S.{0,70}$")
SUBNUMBER_RE = re.compile(r"^\d+\.\d+$")  # the bare "10.1" lines in the ops manual
MIN_REPEATS = 3  # a paragraph showing up this many times in one doc is boilerplate
MAX_SECTION_CHARS = 4000


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def is_heading(block):
    if block.kind == "table" or "\n" in block.text:
        return False
    return HEADING_RE.match(block.text) is not None


def find_year(meta_line, filename):
    years = re.findall(r"\b(19\d\d|20\d\d)\b", meta_line)
    if not years:
        years = re.findall(r"(19\d\d|20\d\d)", filename)
    if not years:
        return None
    return max(int(y) for y in years)


def mark_versions(docs):
    # docs with the same title are versions of each other, newest one wins
    by_title = {}
    for d in docs:
        d["status"] = "current"
        d["superseded_by"] = None
        d["other_versions"] = []
        by_title.setdefault(normalize(d["title"]), []).append(d)

    for versions in by_title.values():
        if len(versions) < 2:
            continue
        versions.sort(key=lambda d: d["year"] or 0)
        newest = versions[-1]
        for d in versions:
            d["other_versions"] = [v["file"] for v in versions if v is not d]
            if d is not newest:
                d["status"] = "superseded"
                d["superseded_by"] = newest["file"]


class Chunk:
    """Collects blocks for one section. Keeps track of which page each part
    of the text came from so citations can point to the right page."""

    def __init__(self, doc, section, kind="section"):
        self.doc = doc
        self.section = section
        self.kind = kind
        self.text = ""
        self.spans = []  # [{start, end, page}] char offsets into self.text

    def add(self, block):
        if self.text:
            self.text += "\n"
        start = len(self.text)
        self.text += block.text
        self.spans.append({"start": start, "end": len(self.text), "page": block.page})

    def to_dict(self, chunk_id):
        pages = sorted(set(s["page"] for s in self.spans))
        return {"id": chunk_id, "doc": self.doc, "section": self.section, "kind": self.kind,
                "text": self.text, "pages": pages, "spans": self.spans}


def process_document(path, fixer):
    blocks, report = extract_pdf(str(path), fixer)

    # --- remove boilerplate ---
    # only inside the same document, the two handbooks share a lot of text but
    # that's on purpose (different versions) so we don't touch that
    counts = Counter(normalize(b.text) for b in blocks if not is_heading(b))
    repeated = set()
    for text, count in counts.items():
        if count >= MIN_REPEATS and len(text) > 40:
            repeated.add(text)

    boilerplate = Chunk(path.name, "Standard provisions repeated throughout this document", "boilerplate")
    already_kept = set()
    boilerplate_pages = set()
    kept = []
    removed = 0
    for b in blocks:
        text = normalize(b.text)
        if SUBNUMBER_RE.match(b.text.strip()):
            removed += 1
        elif text in repeated:
            boilerplate_pages.add(b.page)
            if text in already_kept:
                removed += 1
            else:
                already_kept.add(text)
                boilerplate.add(b)
        else:
            kept.append(b)

    title = kept[0].text.split("\n")[0].strip() if kept else path.stem
    meta_line = kept[1].text.split("\n")[0].strip() if len(kept) > 1 else ""

    # --- split into sections ---
    sections = [Chunk(path.name, "Document header")]
    contents_page = None
    for b in kept:
        if normalize(b.text) == "contents":
            contents_page = b.page
        # the table of contents also looks like headings, ignore those
        on_contents_page = contents_page is not None and b.page == contents_page
        if is_heading(b) and not on_contents_page:
            sections.append(Chunk(path.name, b.text.strip()))
        sections[-1].add(b)

    # sections that were only boilerplate now just have their heading left
    empty_sections = []
    non_empty = []
    for s in sections:
        if len(s.spans) <= 1 and s.section != "Document header":
            empty_sections.append(s.section)
        else:
            non_empty.append(s)
    sections = non_empty
    if already_kept:
        sections.append(boilerplate)

    # --- split sections that are too long ---
    # (doesn't happen with this corpus but just in case)
    chunks = []
    for s in sections:
        if len(s.text) <= MAX_SECTION_CHARS:
            chunks.append(s)
            continue
        part = Chunk(s.doc, s.section, s.kind)
        for span in s.spans:
            block = Block(text=s.text[span["start"]:span["end"]], page=span["page"], y=0)
            if part.spans and len(part.text) + len(block.text) > MAX_SECTION_CHARS:
                chunks.append(part)
                part = Chunk(s.doc, s.section + " (cont.)", s.kind)
            part.add(block)
        chunks.append(part)

    ocr_conf = None
    if report["ocr_pages"]:
        ocr_conf = min(b.meta.get("ocr_min_confidence", 1.0) for b in blocks)

    info = {
        "file": path.name,
        "title": title,
        "meta_line": meta_line,
        "year": find_year(meta_line, path.name),
        "pages": report["pages"],
        "ocr_pages": report["ocr_pages"],
        "tables": report["tables"],
        "blocks_extracted": len(blocks),
        "blocks_removed_as_duplicates": removed,
        "boilerplate_paragraphs": len(already_kept),
        "boilerplate_pages": sorted(boilerplate_pages),
        "sections_only_boilerplate": empty_sections,
        "ocr_min_confidence": ocr_conf,
    }
    return info, chunks


def run(corpus_dir=CORPUS_DIR, index_path=INDEX_PATH):
    start = time.time()
    pdfs = sorted(corpus_dir.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs found in {corpus_dir}")

    fixer = SpaceFixer(get_known_words(pdfs))

    docs = []
    all_chunks = []
    for pdf in pdfs:
        info, chunks = process_document(pdf, fixer)
        info["chunk_ids"] = []
        for c in chunks:
            chunk_id = "C%02d" % (len(all_chunks) + 1)
            all_chunks.append(c.to_dict(chunk_id))
            info["chunk_ids"].append(chunk_id)
        docs.append(info)

        line = f"  {pdf.name:36s} pages={info['pages']:3d} chunks={len(chunks):2d} " \
               f"tables={info['tables']} dup_removed={info['blocks_removed_as_duplicates']}"
        if info["ocr_pages"]:
            line += f" OCR pages {info['ocr_pages']}"
        print(line)

    mark_versions(docs)
    for d in docs:
        if d["status"] == "superseded":
            print(f"  {d['file']} is superseded by {d['superseded_by']}")

    index = {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus_files": {p.name: p.stat().st_mtime for p in pdfs},
        "documents": docs,
        "chunks": all_chunks,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)

    total = sum(len(c["text"]) for c in all_chunks)
    print(f"Indexed {len(docs)} documents, {len(all_chunks)} chunks, {total:,} chars "
          f"(~{total // 4:,} tokens) in {time.time() - start:.1f}s -> {index_path}")
    return index


if __name__ == "__main__":
    run()
