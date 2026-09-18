# Reading text out of the PDFs.
# Normal pages -> pymupdf text blocks
# Tables       -> pymupdf find_tables, turned into markdown + one sentence per row
# Scanned pages (no text layer) -> OCR with RapidOCR

import re
from dataclasses import dataclass, field

import numpy as np
import pymupdf
import wordninja

OCR_DPI = 200
MIN_TEXT_CHARS = 20  # if a page has less text than this we treat it as a scan

_ocr_engine = None


@dataclass
class Block:
    text: str
    page: int  # starts at 1
    y: float  # position on the page, used for sorting
    kind: str = "text"  # "text", "table" or "ocr"
    meta: dict = field(default_factory=dict)


def get_ocr_engine():
    # loading the model takes a few seconds so only do it if we actually need it
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


# ---------- tables ----------

def clean_cell(value):
    if value is None:
        return ""
    value = value.replace("<br>", " ")
    return re.sub(r"\s+", " ", value).strip()


def table_to_block(table, page_no):
    rows = []
    for row in table.extract():
        cells = [clean_cell(c) for c in row]
        if any(cells):
            rows.append(cells)
    header = rows[0]
    body = rows[1:]

    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "---|" * len(header))
    for row in body:
        lines.append("| " + " | ".join(row) + " |")

    # also write each row as a sentence with the column names in it,
    # so a single row still makes sense when it's read on its own
    sentences = []
    for row in body:
        parts = []
        for col, val in zip(header, row):
            if val:
                parts.append(col + ": " + val)
        sentences.append("Row - " + "; ".join(parts) + ".")

    text = "Table:\n" + "\n".join(lines) + "\n\nTable rows as text:\n" + "\n".join(sentences)
    return Block(text=text, page=page_no, y=table.bbox[1], kind="table",
                 meta={"columns": header, "n_rows": len(body)})


def is_inside(box, rect, tol=2.0):
    x0, y0, x1, y1 = box
    return x0 >= rect[0] - tol and y0 >= rect[1] - tol and x1 <= rect[2] + tol and y1 <= rect[3] + tol


# ---------- OCR ----------

class SpaceFixer:
    """RapidOCR gets the letters right but drops a lot of spaces
    ("termsareNet45days"). This puts them back using wordninja."""

    def __init__(self, known_words):
        # known_words = words from the normal (non scanned) pdfs.
        # wordninja splits some of our words wrong, e.g. "invoice" -> "in voice",
        # so if two pieces join into a word we've seen before we join them back
        self.known_words = set(w.lower() for w in known_words)

    def split_word(self, word):
        if len(word) < 8 or word.lower() in self.known_words:
            return word
        result = []
        for piece in wordninja.split(word):
            if result and (result[-1] + piece).lower() in self.known_words:
                result[-1] = result[-1] + piece
            else:
                result.append(piece)
        return " ".join(result)

    def fix_line(self, line):
        line = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", line)  # TheVendor -> The Vendor

        fixed = ""
        for part in re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9]+", line):
            if part.isalnum():
                fixed += self.split_word(part)
            else:
                fixed += part

        fixed = re.sub(r"(?<=[.,;:])(?=[A-Za-z(])", " ", fixed)  # handover.Roadside
        fixed = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", fixed)  # within3hours
        fixed = re.sub(r" {2,}", " ", fixed)
        return fixed.strip()


HEADING_OCR = re.compile(r"^\d+\s*\.\s*[A-Z][A-Z .]+$")  # e.g. "3.PAYMENTTERMS"


def ocr_page(page, page_no, fixer=None):
    pix = page.get_pixmap(dpi=OCR_DPI)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    result, _ = get_ocr_engine()(img)
    if not result:
        return []

    lines = []
    for box, text, conf in result:
        lines.append({"y": box[0][1], "text": text, "conf": float(conf)})
    lines.sort(key=lambda l: l["y"])

    # group the lines into paragraphs: a gap much bigger than the normal
    # line spacing means a new paragraph starts
    gaps = []
    for i in range(len(lines) - 1):
        gaps.append(lines[i + 1]["y"] - lines[i]["y"])
    normal_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0  # median

    paragraphs = [[lines[0]]]
    for i in range(1, len(lines)):
        if normal_gap and lines[i]["y"] - lines[i - 1]["y"] > normal_gap * 1.35:
            paragraphs.append([lines[i]])
        else:
            paragraphs[-1].append(lines[i])

    blocks = []
    for para in paragraphs:
        # headings come out stuck to the paragraph below them, split them off
        groups = [[]]
        for line in para:
            heading = HEADING_OCR.match(line["text"])
            if heading and groups[-1]:
                groups.append([])
            groups[-1].append(line)
            if heading:
                groups.append([])

        for group in groups:
            if not group:
                continue
            texts = []
            for line in group:
                if fixer:
                    texts.append(fixer.fix_line(line["text"]))
                else:
                    texts.append(line["text"])
            min_conf = min(line["conf"] for line in group)
            y = group[0]["y"] * 72 / OCR_DPI  # pixels back to pdf points
            blocks.append(Block(text="\n".join(texts), page=page_no, y=y, kind="ocr",
                                meta={"ocr_min_confidence": round(min_conf, 3)}))
    return blocks


# ---------- main ----------

def extract_pdf(path, fixer=None):
    """Returns (blocks in reading order, small report dict)."""
    doc = pymupdf.open(path)
    blocks = []
    report = {"pages": doc.page_count, "ocr_pages": [], "tables": 0}

    for i, page in enumerate(doc):
        page_no = i + 1

        if len(page.get_text().strip()) < MIN_TEXT_CHARS and page.get_images():
            blocks.extend(ocr_page(page, page_no, fixer))
            report["ocr_pages"].append(page_no)
            continue

        tables = page.find_tables().tables
        report["tables"] += len(tables)
        page_blocks = [table_to_block(t, page_no) for t in tables]

        for x0, y0, x1, y1, text, *rest in page.get_text("blocks"):
            # skip text that belongs to a table, the table block already has it
            in_table = False
            for t in tables:
                if is_inside((x0, y0, x1, y1), t.bbox):
                    in_table = True
            text = text.strip()
            if text and not in_table:
                page_blocks.append(Block(text=text, page=page_no, y=y0))

        page_blocks.sort(key=lambda b: b.y)

        # if a paragraph got cut by the page break, glue the two halves together
        # (last page ends mid sentence and this page starts with a lowercase word)
        if blocks and page_blocks:
            prev = blocks[-1]
            first = page_blocks[0]
            if (prev.kind == "text" and first.kind == "text" and prev.page == page_no - 1
                    and not re.search(r"[.:;!?)]\s*$", prev.text)
                    and re.match(r"^[a-z]", first.text)):
                prev.text = prev.text + "\n" + first.text
                prev.meta["continues_on_page"] = page_no
                page_blocks.pop(0)

        blocks.extend(page_blocks)

    return blocks, report


def get_known_words(paths):
    words = set()
    for path in paths:
        for page in pymupdf.open(path):
            words.update(re.findall(r"[A-Za-z]{3,}", page.get_text()))
    return words
