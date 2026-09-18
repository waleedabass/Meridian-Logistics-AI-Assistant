# Checks the quotes Claude gives us actually exist in the documents.
#
# Claude returns {chunk_id, quote} for each citation. We look for the quote inside
# that chunk's real text. If we can't find it, the citation is thrown away.
# The snippet we return comes from the document itself, not from Claude.

import re
from difflib import SequenceMatcher

MIN_QUOTE_CHARS = 6
FUZZY_MIN_RATIO = 0.9  # allow small typos
MAX_SNIPPET_CHARS = 400


def normalize_with_positions(text):
    """Keep only letters/digits (lowercased). Also returns where each kept char
    was in the original text so we can map a match back."""
    chars = []
    positions = []
    for i, ch in enumerate(text):
        if ch.isalnum():
            chars.append(ch.lower())
            positions.append(i)
    return "".join(chars), positions


def locate(quote, text):
    """Find quote in text, ignoring case/spaces/punctuation.
    Returns (start, end) in the original text or None."""
    q, _ = normalize_with_positions(quote)
    t, positions = normalize_with_positions(text)
    if len(q) < MIN_QUOTE_CHARS or not t:
        return None

    pos = t.find(q)
    if pos != -1:
        start = pos
        end = pos + len(q)
    else:
        # no exact match, try fuzzy: find the longest common piece and check
        # the area around it is close enough to the quote
        m = SequenceMatcher(None, t, q, autojunk=False).find_longest_match(0, len(t), 0, len(q))
        if m.size < min(20, len(q)):
            return None
        start = max(0, m.a - m.b)
        end = min(len(t), start + len(q))
        ratio = SequenceMatcher(None, t[start:end], q, autojunk=False).ratio()
        if ratio < FUZZY_MIN_RATIO:
            return None

    return positions[start], positions[end - 1] + 1


def page_for_offset(chunk, offset):
    for span in chunk["spans"]:
        if span["start"] <= offset <= span["end"]:
            return span["page"]
    return chunk["pages"][0]


def make_snippet(text, start, end):
    # expand to full lines so the snippet doesn't start mid word
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    snippet = re.sub(r"\s+", " ", text[line_start:line_end]).strip()
    if len(snippet) > MAX_SNIPPET_CHARS:
        # too long (e.g. a whole table), just use the quoted part
        snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    return snippet


def verify(citations, chunks, documents):
    """Returns (sources, rejected). sources = citations we could find in the docs."""
    sources = []
    rejected = []
    seen = set()

    for cit in citations:
        chunk = chunks.get(cit.get("chunk_id", "").strip())
        if chunk is None:
            rejected.append({**cit, "reason": "unknown chunk id"})
            continue
        found = locate(cit.get("quote", ""), chunk["text"])
        if found is None:
            rejected.append({**cit, "reason": "quote not found in chunk"})
            continue

        start, end = found
        page = page_for_offset(chunk, start)
        snippet = make_snippet(chunk["text"], start, end)

        key = (chunk["doc"], page, snippet)
        if key in seen:  # same quote cited twice
            continue
        seen.add(key)

        doc = documents[chunk["doc"]]
        source = {
            "document": chunk["doc"],
            "location": f"page {page}",
            "snippet": snippet,
            "section": chunk["section"],
            "chunk_id": chunk["id"],
        }
        if doc["status"] == "superseded":
            source["document_status"] = f"superseded by {doc['superseded_by']}"
        if doc["ocr_pages"]:
            source["extraction"] = "ocr"
        sources.append(source)

    return sources, rejected
