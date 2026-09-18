"""PDF -> positioned text blocks.

Three extraction paths, chosen per page:
  * text layer   - PyMuPDF paragraph blocks (fast, exact)
  * tables       - PyMuPDF table finder; each table becomes one block containing
                   a markdown table plus one plain sentence per row, so both the
                   LLM and keyword search can read it
  * OCR          - pages with no text layer (scans) are rendered at 200 dpi and read
                   with RapidOCR (local ONNX model, no network). The OCR model drops
                   spaces between words, so a word-segmentation pass repairs them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

OCR_DPI = 200
MIN_TEXT_CHARS = 20  # below this a page is treated as image-only


@dataclass
class Block:
    text: str
    page: int  # 1-based
    y: float  # top coordinate, used for ordering
    kind: str = "text"  # text | table | ocr
    meta: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- tables
def _cell(v) -> str:
    return re.sub(r"\s+", " ", (v or "").replace("<br>", " ")).strip()


def table_block(table, page_no: int) -> Block:
    rows = [[_cell(c) for c in r] for r in table.extract()]
    rows = [r for r in rows if any(r)]
    header, body = rows[0], rows[1:]
    md = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    md += ["| " + " | ".join(r) + " |" for r in body]
    sentences = []
    for r in body:
        pairs = [f"{h}: {v}" for h, v in zip(header, r) if v]
        sentences.append("Row - " + "; ".join(pairs) + ".")
    text = "Table:\n" + "\n".join(md) + "\n\nTable rows as text:\n" + "\n".join(sentences)
    return Block(text=text, page=page_no, y=table.bbox[1], kind="table",
                 meta={"columns": header, "n_rows": len(body)})


def _inside(bbox, rect, tol=2.0) -> bool:
    x0, y0, x1, y1 = bbox
    return x0 >= rect[0] - tol and y0 >= rect[1] - tol and x1 <= rect[2] + tol and y1 <= rect[3] + tol


# --------------------------------------------------------------------------- OCR
_ocr_engine = None


def _ocr():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


class SpaceRepairer:
    """Re-inserts spaces the OCR model dropped ("termsareNet45days" -> "terms are Net 45 days").

    wordninja supplies an English unigram model. Its dictionary is general-web, so it
    splits domain words it thinks are rare ("invoice" -> "in voice"). We fix that by
    re-merging adjacent pieces whenever the merged word appears in the vocabulary of
    the corpus's own text-layer documents.
    """

    def __init__(self, corpus_vocab: set[str]):
        import wordninja
        self._split = wordninja.split
        self.vocab = {w.lower() for w in corpus_vocab}

    def _segment(self, run: str) -> str:
        if len(run) < 8 or run.lower() in self.vocab:
            return run
        parts = self._split(run)
        merged: list[str] = []
        for p in parts:
            if merged and (merged[-1] + p).lower() in self.vocab:
                merged[-1] += p
            else:
                merged.append(p)
        return " ".join(merged)

    def repair(self, line: str) -> str:
        line = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", line)  # camelCase joins: TheVendor
        out = []
        for part in re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9]+", line):
            out.append(self._segment(part) if part.isalnum() else part)
        s = "".join(out)
        s = re.sub(r"(?<=[.,;:])(?=[A-Za-z(])", " ", s)  # "handover.Roadside"
        s = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", s)  # "within3hours"
        return re.sub(r" {2,}", " ", s).strip()


def ocr_blocks(page, page_no: int, repairer: SpaceRepairer | None) -> list[Block]:
    import numpy as np

    pix = page.get_pixmap(dpi=OCR_DPI)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    result, _ = _ocr()(img)
    if not result:
        return []
    lines = sorted(
        ({"y": b[0][1], "h": b[2][1] - b[0][1], "text": t, "conf": float(c)} for b, t, c in result),
        key=lambda d: d["y"],
    )
    # group lines into paragraphs using vertical gaps
    gaps = [b["y"] - a["y"] for a, b in zip(lines, lines[1:])]
    typical = sorted(gaps)[len(gaps) // 2] if gaps else 0
    paras: list[list[dict]] = [[lines[0]]]
    for prev, cur in zip(lines, lines[1:]):
        if typical and cur["y"] - prev["y"] > typical * 1.35:
            paras.append([cur])
        else:
            paras[-1].append(cur)
    scale = 72 / OCR_DPI
    blocks = []
    for para in paras:
        # a heading like "3.PAYMENTTERMS" is its own line; split it from its body
        groups: list[list[dict]] = [[]]
        for ln in para:
            if re.match(r"^\d+\s*\.\s*[A-Z][A-Z .]+$", ln["text"]) and groups[-1]:
                groups.append([])
            groups[-1].append(ln)
            if re.match(r"^\d+\s*\.\s*[A-Z][A-Z .]+$", ln["text"]):
                groups.append([])
        for g in (g for g in groups if g):
            texts = [repairer.repair(ln["text"]) if repairer else ln["text"] for ln in g]
            conf = min(ln["conf"] for ln in g)
            blocks.append(Block(text="\n".join(texts), page=page_no, y=g[0]["y"] * scale,
                                kind="ocr", meta={"ocr_min_confidence": round(conf, 3)}))
    return blocks


# --------------------------------------------------------------------------- main
def extract_pdf(path: str, repairer: SpaceRepairer | None = None) -> tuple[list[Block], dict]:
    """Return ordered blocks for the whole document plus an extraction report."""
    doc = pymupdf.open(path)
    blocks: list[Block] = []
    report = {"pages": doc.page_count, "ocr_pages": [], "tables": 0}
    for i, page in enumerate(doc):
        page_no = i + 1
        if len(page.get_text().strip()) < MIN_TEXT_CHARS and page.get_images():
            blocks.extend(ocr_blocks(page, page_no, repairer))
            report["ocr_pages"].append(page_no)
            continue
        tables = list(page.find_tables().tables)
        report["tables"] += len(tables)
        page_blocks = [table_block(t, page_no) for t in tables]
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            if any(_inside((x0, y0, x1, y1), t.bbox) for t in tables):
                continue  # already represented by the table block
            text = text.strip()
            if text:
                page_blocks.append(Block(text=text, page=page_no, y=y0))
        page_blocks.sort(key=lambda b: b.y)
        # Re-join a paragraph that was split by a page break: the previous page ends
        # mid-sentence and this page starts with a lowercase continuation.
        if (blocks and page_blocks and blocks[-1].kind == "text" and page_blocks[0].kind == "text"
                and blocks[-1].page == page_no - 1
                and not re.search(r"[.:;!?)]\s*$", blocks[-1].text)
                and re.match(r"^[a-z]", page_blocks[0].text)):
            cont = page_blocks.pop(0)
            prev = blocks[-1]
            prev.text = prev.text + "\n" + cont.text
            prev.meta["continues_on_page"] = page_no
        blocks.extend(page_blocks)
    return blocks, report


def text_layer_vocab(paths: list[str]) -> set[str]:
    vocab: set[str] = set()
    for p in paths:
        for page in pymupdf.open(p):
            vocab.update(re.findall(r"[A-Za-z]{3,}", page.get_text()))
    return vocab
