"""Loads the index and decides what the model gets to read.

full_context mode: every chunk, grouped by document with version/OCR notes. After
  deduplication the whole corpus is ~7k tokens, so there is nothing to retrieve;
  sending all of it removes retrieval misses entirely and lets prompt caching make
  the repeated prefix cheap.
retrieval mode: BM25 over chunks, top-k, plus the other-version sibling of any
  versioned chunk so conflicts are always visible. This is the path for a corpus that
  outgrows the context budget.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import cached_property
from pathlib import Path

STOP = set("""a an the of to in on for and or is are was were be been by with at from as that this
it its what which who whom how do does did can i we you my our your per any all there their
has have had not no if about into than then""".split())


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", text.lower().replace(",", ""))
    out = []
    for t in toks:
        if t in STOP:
            continue
        if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(map(len, docs)) / max(len(docs), 1)
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def scores(self, query: list[str]) -> list[float]:
        res = []
        for tf, d in zip(self.tf, self.docs):
            s = 0.0
            for t in query:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl))
            res.append(s)
        return res


class Index:
    def __init__(self, path: Path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.documents = {d["file"]: d for d in data["documents"]}
        self.chunks = {c["id"]: c for c in data["chunks"]}
        self.order = [c["id"] for c in data["chunks"]]
        self.built_at = data["built_at"]

    # ------------------------------------------------------------------ rendering
    def doc_attrs(self, d: dict) -> str:
        if d["status"] == "superseded":
            status = f"SUPERSEDED by {d['superseded_by']} (historical; do not use for current policy)"
        elif d["other_versions"]:
            status = f"CURRENT version (older versions: {', '.join(d['other_versions'])})"
        else:
            status = "current"
        notes = []
        if d["ocr_pages"]:
            notes.append("text obtained by OCR from a scanned image")
        if d["blocks_removed_as_duplicates"] > 50:
            notes.append(f"{d['pages']}-page document; {d['blocks_removed_as_duplicates']} repeated boilerplate "
                         f"paragraphs collapsed into one 'Standard provisions' chunk; sections with no other "
                         f"content: {', '.join(d['sections_only_boilerplate'])}")
        attrs = f'file="{d["file"]}" title="{d["title"]}" edition="{d["meta_line"]}" status="{status}"'
        if notes:
            attrs += f' note="{"; ".join(notes)}"'
        return attrs

    def render(self, chunk_ids: list[str]) -> str:
        by_doc: dict[str, list[dict]] = {}
        for cid in chunk_ids:
            c = self.chunks[cid]
            by_doc.setdefault(c["doc"], []).append(c)
        out = ["<documents>"]
        for doc, chunks in by_doc.items():
            out.append(f"<document {self.doc_attrs(self.documents[doc])}>")
            for c in chunks:
                pages = ",".join(map(str, c["pages"]))
                out.append(f'<chunk id="{c["id"]}" section="{c["section"]}" pages="{pages}">\n{c["text"]}\n</chunk>')
            out.append("</document>")
        out.append("</documents>")
        return "\n".join(out)

    @cached_property
    def full_context(self) -> str:
        return self.render(self.order)

    @property
    def full_context_tokens_estimate(self) -> int:
        return len(self.full_context) // 4

    # ------------------------------------------------------------------ retrieval
    @cached_property
    def _bm25(self) -> BM25:
        docs = []
        for cid in self.order:
            c = self.chunks[cid]
            d = self.documents[c["doc"]]
            docs.append(tokenize(f"{d['title']} {d['file']} {c['section']} {c['text']}"))
        return BM25(docs)

    def search(self, query: str, k: int) -> list[str]:
        scores = self._bm25.scores(tokenize(query))
        ranked = [cid for s, cid in sorted(zip(scores, self.order), reverse=True) if s > 0][:k]
        # pull in the same section from other versions of a versioned document
        extra = []
        for cid in ranked:
            c = self.chunks[cid]
            for other in self.documents[c["doc"]]["other_versions"]:
                for oc in self.order:
                    o = self.chunks[oc]
                    if o["doc"] == other and o["section"] == c["section"] and oc not in ranked + extra:
                        extra.append(oc)
        chosen = set(ranked + extra)
        return [cid for cid in self.order if cid in chosen]
