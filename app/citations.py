"""Citation verification.

The model must return, for every claim, a chunk id and a quote copied from that chunk.
We never trust that: each quote is located inside the chunk's real text (tolerant of
whitespace, case and punctuation, and lightly tolerant of typos). Only quotes that are
found become sources, and the snippet we return is the document's own text, not the
model's copy of it. The match position also tells us the exact page.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

MIN_QUOTE_CHARS = 6
FUZZY_RATIO = 0.9
SNIPPET_MAX = 400


def _normalize(text: str) -> tuple[str, list[int]]:
    """Lowercase alphanumerics only, plus a map from normalized index -> original index."""
    chars, index = [], []
    for i, ch in enumerate(text):
        if ch.isalnum():
            chars.append(ch.lower())
            index.append(i)
    return "".join(chars), index


def locate(quote: str, text: str) -> tuple[int, int] | None:
    """Return (start, end) of the quote inside text in original coordinates, or None."""
    qn, _ = _normalize(quote)
    tn, idx = _normalize(text)
    if len(qn) < MIN_QUOTE_CHARS or not tn:
        return None
    pos = tn.find(qn)
    if pos >= 0:
        start, end = pos, pos + len(qn)
    else:
        m = SequenceMatcher(None, tn, qn, autojunk=False).find_longest_match(0, len(tn), 0, len(qn))
        if m.size < min(20, len(qn)):
            return None
        start = max(0, m.a - m.b)
        end = min(len(tn), start + len(qn))
        if SequenceMatcher(None, tn[start:end], qn, autojunk=False).ratio() < FUZZY_RATIO:
            return None
    return idx[start], idx[end - 1] + 1


def page_at(chunk: dict, offset: int) -> int:
    for span in chunk["spans"]:
        if span["start"] <= offset < span["end"] + 1:
            return span["page"]
    return chunk["pages"][0]


def snippet(text: str, start: int, end: int) -> str:
    """The located text, widened to whole lines so it reads naturally."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end < 0 else line_end
    s = re.sub(r"\s+", " ", text[line_start:line_end]).strip()
    if len(s) > SNIPPET_MAX:  # a long table row block etc: keep the quoted part
        s = re.sub(r"\s+", " ", text[start:end]).strip()
    return s


def verify(citations: list[dict], chunks: dict[str, dict], documents: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Split model citations into (verified sources, rejected citations)."""
    sources, rejected, seen = [], [], set()
    for cit in citations:
        chunk = chunks.get(cit.get("chunk_id", "").strip())
        loc = locate(cit.get("quote", ""), chunk["text"]) if chunk else None
        if not loc:
            rejected.append({**cit, "reason": "unknown chunk id" if not chunk else "quote not found in chunk"})
            continue
        start, end = loc
        page = page_at(chunk, start)
        snip = snippet(chunk["text"], start, end)
        key = (chunk["doc"], page, snip)
        if key in seen:
            continue
        seen.add(key)
        doc = documents[chunk["doc"]]
        src = {
            "document": chunk["doc"],
            "location": f"page {page}",
            "snippet": snip,
            "section": chunk["section"],
            "chunk_id": chunk["id"],
        }
        if doc["status"] == "superseded":
            src["document_status"] = f"superseded by {doc['superseded_by']}"
        if doc["ocr_pages"]:
            src["extraction"] = "ocr"
        sources.append(src)
    return sources, rejected
