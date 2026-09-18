# Meridian Logistics Knowledge Assistant

A FastAPI service that answers staff questions about the documents in `corpus/`, with every answer backed by a citation that has been mechanically checked against the source text.

## Run it

Setup, once (Python 3.11+):

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows. macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp. Then put your ANTHROPIC_API_KEY in .env
```

Then one command ingests the corpus, starts the API, runs all 26 evaluation questions and writes the report:

```bash
python run.py                     # add --repeat 3 for steadier latency percentiles
```

Output: `eval/results.md` (readable report) and `eval/results.json` (every raw response).

Other entry points:

| Command | What it does |
|---|---|
| `python -m app.ingest` | Build `data/index.json` from everything in `corpus/` |
| `python run.py serve` | Ingest if needed, then serve on `http://127.0.0.1:8000` |
| `python eval/evaluate.py --url http://127.0.0.1:8000` | Evaluate an already running service |
| `pytest` | Offline tests (no API key needed; the model is faked) |

```bash
curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d "{\"question\": \"How many annual leave days do I get?\"}"
```

The response has the required `answer`, `sources[] {document, location, snippet}` and `latency_ms`, plus `status` (`answered` / `not_found` / `unverified`), token `usage` and `cost_usd`. `GET /documents` shows what ingestion found in each file.

## What is actually in the corpus

Reading the documents before writing code changed the design. The corpus is small but contains six deliberate traps, and most of the 26 questions land on one of them.

| Trap | Where | What a naive pipeline does |
|---|---|---|
| **Two versions of the handbook.** 2024 says 14 leave days, 3 months probation, 1 remote day, 30 days notice. 2025 says 20, 6, 2, 60. | `employee_handbook_2024.pdf`, `employee_handbook_2025.pdf` | Retrieves whichever chunk scores higher and answers from the outdated policy. |
| **A scanned contract with no text layer.** | `vendor_agreement_scanned.pdf` | Extracts nothing, so the payment-terms question fails. |
| **A 67-page manual that is 94% repeated boilerplate.** Ten standard paragraphs recur across every section; the one real fact (damaged-cargo claims within 7 working days) is a single paragraph on page 29. | `operations_manual_full.pdf` | The boilerplate floods the index and the needle is outranked. |
| **Rate tables.** Plain text extraction emits one cell per line, destroying rows. | `pricing_sheet_2025.pdf`, `quarterly_review_q3_2025.pdf` | Cannot tell which number belongs to which route and weight band. |
| **Look-alike facts in different documents.** Client payment terms are 30 days, vendor terms are Net 45. The only "insurance" is vendor public liability cover. | onboarding process, vendor agreement | Answers the vendor question with client terms, or "answers" the health-insurance question with liability cover. |
| **Questions with no answer.** Salary ranges, health insurance, maternity leave, the CEO's name, and international refund policy appear nowhere. | 5 of 26 questions | Makes up a plausible answer. |

## Approach

### Ingestion (`app/ingest.py`, `app/pdf_extract.py`)

1. **Per-page extraction with three paths.** Text-layer pages use PyMuPDF paragraph blocks. Tables go through PyMuPDF's table finder and become a markdown table plus one plain sentence per row ("Origin: Karachi; Destination: Quetta; ... Fuel surcharge: 9.5%"). Pages without a text layer are rendered at 200 dpi and read by RapidOCR, a local ONNX model with no network calls.
2. **OCR space repair.** RapidOCR reads every character correctly but often drops spaces ("termsareNet45days"). A word-segmentation pass (wordninja) re-inserts them. Its general-English dictionary splits some domain words ("in voice"), so pieces are re-merged whenever the joined word appears in the vocabulary of the corpus's own text-layer documents.
3. **Boilerplate collapse.** A paragraph that repeats three or more times inside one document is kept once, in a "standard provisions" chunk, and dropped elsewhere. Paragraphs split by a page break are re-joined first so their fragments deduplicate too. This removes 982 blocks from the manual and leaves 3 chunks: the header and table of contents, the claims section on page 29, and one copy of the provisions. Deduplication is deliberately within a document only, because identical text across the two handbooks is legitimately separate.
4. **Sections as the unit.** Documents are split on their numbered headings. Each character keeps its source page, so a citation inside a section that crosses a page break still gets the right page. For example, incident-reporting step 6 cites page 2.
5. **Version detection.** Documents with the same title form a family. The newest edition, by the year in the header line, is marked current and the others superseded. The model sees this status on every chunk.

Result: 9 documents, 58 chunks, about 6,600 tokens of text.

### Answering (`app/qa.py`, `app/retrieval.py`)

**The obvious approach, embeddings plus a vector store plus top-k retrieval, is the wrong one for this corpus.** After deduplication the entire corpus is about 6,600 tokens. Retrieval can only lose information here, and four of the traps above are exactly retrieval failures. The page 29 needle is outranked by boilerplate. The incident steps split across a page break. "Which route is most expensive" needs the whole table. "Has the leave policy changed" needs both handbook versions at once.

So the service puts the whole deduplicated corpus into the system prompt, tagged by document, version status and chunk id, and marks it for **prompt caching**. Every request after the first reads the roughly 9,000-token prefix from cache at 10% of the input price, which keeps both cost and latency low. The server warms the cache at startup.

`MODE=retrieval` is also implemented, for when the corpus outgrows the budget. It uses BM25 over the same chunks, and whenever it retrieves a section of a versioned document it also pulls the matching section from the other version, so conflicts stay visible. `MODE=auto` switches when the rendered corpus exceeds `FULL_CONTEXT_TOKEN_BUDGET`, 60,000 tokens by default.

### Citations are verified, not trusted (`app/citations.py`)

The model returns structured JSON through the API's JSON-schema output mode: a list of `{chunk_id, quote}` pairs, then the answer, then a status. The quotes come first on purpose, so the answer is written after the evidence is chosen.

Every quote is then located inside the real chunk text. Matching ignores case, whitespace and punctuation, and tolerates small typos at a 0.9 similarity ratio. Only quotes that are found become sources. The returned snippet is the document's own text, not the model's copy, and the match position gives the exact page.

If the model says "answered" but none of its citations verify, it gets one corrective retry that tells it which quotes failed. If that also fails, the service withholds the answer and returns `status: "unverified"`. **An answer is never returned without a verified source.** Questions the documents do not cover return `status: "not_found"` with a plain statement, and cite the closest related passage when one exists.

### Model

The default is **Claude Haiku 4.5** (`claude-haiku-4-5`). The task is grounded extraction over a small, cached context, with a hard p95 latency limit of 4 seconds. That favours the fastest model that answers these questions correctly. `MODEL=claude-sonnet-5` and `MODEL=claude-opus-5` are supported by setting an environment variable, run with low effort and thinking disabled to protect latency. I only ran the full evaluation on Haiku 4.5, so all numbers below are for Haiku.

## Results

Measured with `python run.py --repeat 3` on 18 Sep 2026: 26 questions, 3 passes, 78 requests to the running service. Full per-question output is in `eval/results.md`, raw responses in `eval/results.json`.

| Metric | Result |
|---|---|
| Correct, first pass | 25 / 26 |
| Correct, all passes | 76 / 78 |
| Answers returned without a source | 0 |
| Server latency p50 | 2,055 ms |
| Server latency p95 | **4,571 ms (misses the 4,000 ms target)** |
| Server latency max | 6,302 ms |
| Cost per query, mean | **$0.00178** |
| Cost per query, max | $0.00298 |

Grading is automatic. `eval/expected.json` is a key I wrote by reading the documents by hand. It lists the facts each answer must contain and which document a source must come from. For the five questions the documents can't answer, the expected result is `not_found`.

The two failures are the same question, #16 ("most expensive per kg in the 2T-10T band"). On 2 of 3 runs the model said Islamabad-Gilgit at PKR 84,000, but Karachi-Islamabad is higher at PKR 88,500. So the table extraction is fine and the mistake is the model comparing numbers. A small calculator/lookup step would fix this (see "With two more days").

Latency: p95 is over the limit. The slowest answers are the long list answers (KYC documents, SLA sign-off steps, new clients), which write about 250 output tokens against a median of 99. Latency grows with answer length, not with the question.

### Cost per query: how I got the number

Model is Claude Haiku 4.5. Prices from Anthropic's pricing page, per million tokens:

| Token type | Price per 1M tokens |
|---|---|
| Normal input | $1.00 |
| Cache write (1.25 x input) | $1.25 |
| Cache read (0.10 x input) | $0.10 |
| Output | $5.00 |

Formula (the service returns this as `cost_usd` on every response, see `Usage.cost_usd` in `app/qa.py`):

```
cost = input x $1.00/M + cache_write x $1.25/M + cache_read x $0.10/M + output x $5.00/M
```

Token counts are not estimated. They are the `usage` numbers the API returned, averaged over all 78 requests:

| Part | Avg tokens per query | Price per 1M | Cost |
|---|---|---|---|
| Question text (not cached) | 25.4 | $1.00 | $0.0000254 |
| Instructions + all documents, read from cache | 10,531 | $0.10 | $0.0010531 |
| Cache write | 0 | $1.25 | $0.0000000 |
| Answer + citations (output) | 139.4 | $5.00 | $0.0006970 |
| **Total** | | | **$0.0017755** |

That matches the measured average of $0.001775 per query. About 59% of the cost is reading the cached documents and 39% is the output.

Notes on the numbers:

- The cached prefix is 10,141 tokens. The average is a bit higher (10,531) because question #12 needed the citation retry on all 3 runs, so it read the prefix twice. That's also the most expensive query, $0.00298.
- Cache writes show 0 because the server sends a warm-up question on startup, which pays the write before the evaluation starts. The cache stays alive as long as there's at least one question every 5 minutes (each read resets the timer).
- The first question after the cache expires is the expensive one: 10,141 x $1.25/M = $0.0127 for the write, plus the normal question and output, about **$0.0134** for that one query.
- Without prompt caching every query would pay full price for the 10,141 prefix tokens: about $0.0109 per query. Caching makes a normal query about 84% cheaper.
- The whole evaluation (78 requests) cost $0.138, plus one cache write at startup.

Rough example: 500 questions a day during office hours at $0.00178 each is about $0.89 a day, plus about $0.013 every time the cache goes cold after a gap of more than 5 minutes.

## What I tried, what I rejected

- **Rejected: vector store with embeddings.** At about 6,600 tokens it adds infrastructure and a new failure mode, retrieval misses, while buying nothing. BM25 retrieval mode is kept as the path for scale.
- **Rejected: plain text extraction for tables.** It produced one cell per line with no row structure. Table detection fixed it.
- **Rejected: Tesseract OCR.** It needs a system install, which breaks one-command setup. RapidOCR installs with pip and bundles its model. **Considered: Claude vision for OCR.** It would be more accurate, but it makes ingestion depend on a paid API for one page that local OCR already reads perfectly after space repair.
- **Rejected: fixed-size token chunks.** They split lists, such as the KYC documents and incident steps, and lose headings. Numbered sections are the natural unit in every document here.
- **Rejected: trusting model citations.** A model can cite a real chunk with an invented quote. Mechanical verification turns "must carry its sources" from a hope into a guarantee.

## What is weak in this submission

- **Full-context mode has a ceiling.** It works up to roughly 60,000 tokens. The retrieval fallback is keyword-only BM25 with no embeddings or reranker, and it has only been tested on this corpus.
- **Version detection is heuristic.** It depends on identical titles and a year in the header line. A renamed document or an undated revision would not be linked.
- **Deduplication could hide a meaningful repeat.** A clause repeated on purpose, three or more times in one document, is kept only once. It is never lost, but its other locations are not cited.
- **Paragraphs re-joined across a page break cite the first page.** This is correct for the start of the paragraph and one page early for the tail.
- **The grader is keyword-based.** It checks required facts and source documents, not whether the prose is good. A correct answer phrased unexpectedly could fail, and a wrong one containing the keywords could pass.
- **OCR confidence is recorded but not surfaced.** Answers from the scanned contract are flagged `"extraction": "ocr"` but do not carry a confidence warning.
- **There is no authentication, rate limiting, or per-document access control.** A real deployment would need all three.
- **p95 latency misses the target.** Measured p95 is 4.6 s against the 4 s limit, driven by long list answers. It also depends on the API's speed on the day of measurement.
- **Comparing numbers across a table is unreliable.** Question #16 picked the wrong route on 2 of 3 runs.

## With two more days

1. Build hybrid retrieval, BM25 plus embeddings with a reranker, and test it on a synthetic corpus a hundred times larger so the retrieval path is proven rather than theoretical.
2. Grow the evaluation to paraphrased and adversarial variants of each question, and add a model-graded check of answer quality beside the keyword check.
3. Add a small calculator tool for rate-card arithmetic, so surcharge totals are computed rather than generated.
4. Replace title-matching with a document registry holding effective dates, owners and supersession links, maintained alongside the corpus.
5. Stream responses, add per-query logging with cost dashboards, and put authentication in front of `/ask`.

## Questions I would have emailed

The brief invites questions. These are the ones I would have sent, with the assumption I made instead.

1. **"Most expensive per kg in the 2T-10T band."** The rate card gives a flat price per band, not per kg. I assumed a comparison at equal weight, which makes the highest band rate the most expensive: Karachi to Islamabad at PKR 88,500. The service states this reading in its answer.
2. **Superseded documents.** Should the 2024 handbook be answerable at all? I assumed the current version wins and the older figure is mentioned only as a change.
3. **Latency measurement point.** I report both the server's own `latency_ms` and the client round trip.
4. **Unanswerable questions.** I assumed a clear "not covered" with `status: not_found` is the correct result, and not a failure for lacking a source.

## Layout

```
app/
  pdf_extract.py   text-layer blocks, table finder, OCR and space repair
  ingest.py        dedup, sections, versions -> data/index.json
  retrieval.py     index loading, context rendering, BM25 retrieval mode
  citations.py     quote verification and page mapping
  qa.py            prompt, structured output, retry, cost accounting
  main.py          FastAPI app: /ask, /health, /documents
eval/
  evaluate.py      runs eval_questions.json against the service
  expected.json    hand-written grading key
tests/             offline tests with a fake model client
run.py             one-command pipeline
```
