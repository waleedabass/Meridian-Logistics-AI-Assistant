# Loads the index and builds the text we send to Claude.
#
# Two modes:
# - full_context: send every chunk. After dedup the whole corpus is only ~7k tokens
#   so there's no point searching, and we can't miss anything this way.
# - retrieval: BM25 top k chunks. Only needed if the corpus gets too big.

import json
import math
import re
from collections import Counter

STOPWORDS = set("""a an the of to in on for and or is are was were be been by with at from as
that this it its what which who whom how do does did can i we you my our your per any all
there their has have had not no if about into than then""".split())


def tokenize(text):
    words = re.findall(r"[a-z0-9]+", text.lower().replace(",", ""))
    tokens = []
    for w in words:
        if w in STOPWORDS:
            continue
        # very basic plural handling: "claims" -> "claim"
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        tokens.append(w)
    return tokens


class BM25:
    # standard BM25, wrote it by hand instead of adding a library for 30 lines
    def __init__(self, docs, k1=1.4, b=0.75):
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.avg_len = sum(len(d) for d in docs) / max(len(docs), 1)
        self.term_freqs = [Counter(d) for d in docs]

        doc_freq = Counter()
        for d in docs:
            for term in set(d):
                doc_freq[term] += 1
        n = len(docs)
        self.idf = {}
        for term, df in doc_freq.items():
            self.idf[term] = math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score_all(self, query_tokens):
        scores = []
        for tf, doc in zip(self.term_freqs, self.docs):
            score = 0.0
            for term in query_tokens:
                if term not in tf:
                    continue
                f = tf[term]
                norm = self.k1 * (1 - self.b + self.b * len(doc) / self.avg_len)
                score += self.idf[term] * f * (self.k1 + 1) / (f + norm)
            scores.append(score)
        return scores


class Index:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.built_at = data["built_at"]
        self.documents = {d["file"]: d for d in data["documents"]}
        self.chunks = {c["id"]: c for c in data["chunks"]}
        self.order = [c["id"] for c in data["chunks"]]

        self.full_context = self.render(self.order)
        self.full_context_tokens_estimate = len(self.full_context) // 4  # rough, ~4 chars per token
        self.bm25 = None  # built the first time search() is called

    def doc_attributes(self, doc):
        if doc["status"] == "superseded":
            status = f"SUPERSEDED by {doc['superseded_by']} (historical; do not use for current policy)"
        elif doc["other_versions"]:
            status = f"CURRENT version (older versions: {', '.join(doc['other_versions'])})"
        else:
            status = "current"

        notes = []
        if doc["ocr_pages"]:
            notes.append("text obtained by OCR from a scanned image")
        if doc["blocks_removed_as_duplicates"] > 50:
            notes.append(f"{doc['pages']}-page document; {doc['blocks_removed_as_duplicates']} repeated boilerplate "
                         f"paragraphs collapsed into one 'Standard provisions' chunk; sections with no other "
                         f"content: {', '.join(doc['sections_only_boilerplate'])}")

        attrs = f'file="{doc["file"]}" title="{doc["title"]}" edition="{doc["meta_line"]}" status="{status}"'
        if notes:
            attrs += f' note="{"; ".join(notes)}"'
        return attrs

    def render(self, chunk_ids):
        # group chunks under their document so the model sees the version status once per doc
        grouped = {}
        for cid in chunk_ids:
            chunk = self.chunks[cid]
            grouped.setdefault(chunk["doc"], []).append(chunk)

        lines = ["<documents>"]
        for doc_name, chunks in grouped.items():
            lines.append(f"<document {self.doc_attributes(self.documents[doc_name])}>")
            for c in chunks:
                pages = ",".join(str(p) for p in c["pages"])
                lines.append(f'<chunk id="{c["id"]}" section="{c["section"]}" pages="{pages}">\n{c["text"]}\n</chunk>')
            lines.append("</document>")
        lines.append("</documents>")
        return "\n".join(lines)

    def search(self, query, k):
        if self.bm25 is None:
            docs = []
            for cid in self.order:
                c = self.chunks[cid]
                d = self.documents[c["doc"]]
                docs.append(tokenize(f"{d['title']} {d['file']} {c['section']} {c['text']}"))
            self.bm25 = BM25(docs)

        scores = self.bm25.score_all(tokenize(query))
        ranked = sorted(zip(scores, self.order), reverse=True)
        top = [cid for score, cid in ranked if score > 0][:k]

        # if we picked a section from a document that has other versions,
        # add the same section from those versions too so the model sees both
        extra = []
        for cid in top:
            chunk = self.chunks[cid]
            for other_doc in self.documents[chunk["doc"]]["other_versions"]:
                for other_id in self.order:
                    other = self.chunks[other_id]
                    if other["doc"] == other_doc and other["section"] == chunk["section"] \
                            and other_id not in top and other_id not in extra:
                        extra.append(other_id)

        selected = set(top + extra)
        return [cid for cid in self.order if cid in selected]  # keep document order
