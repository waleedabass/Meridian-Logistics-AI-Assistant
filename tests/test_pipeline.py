"""Offline tests: no API key or network needed. The model is replaced by a fake client."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import config
from app.citations import locate, verify
from app.ingest import run as ingest
from app.qa import QAService
from app.retrieval import Index


@pytest.fixture(scope="session")
def index(tmp_path_factory) -> Index:
    path = config.INDEX_PATH
    if not path.exists():
        path = tmp_path_factory.mktemp("idx") / "index.json"
        ingest(config.CORPUS_DIR, path)
    return Index(path)


def chunk(index, doc, section_startswith):
    return next(c for c in index.chunks.values() if c["doc"] == doc and c["section"].startswith(section_startswith))


# ------------------------------------------------------------------ ingestion
def test_scanned_vendor_agreement_is_ocrd_and_spaced(index):
    c = chunk(index, "vendor_agreement_scanned.pdf", "3. PAYMENT")
    assert "Net 45 days from the date of a correctly rendered invoice" in c["text"]
    assert index.documents["vendor_agreement_scanned.pdf"]["ocr_pages"] == [1]


def test_operations_manual_boilerplate_collapsed_and_needle_kept(index):
    doc = index.documents["operations_manual_full.pdf"]
    assert doc["pages"] == 67 and doc["blocks_removed_as_duplicates"] > 900
    claims = chunk(index, "operations_manual_full.pdf", "10. Claims")
    assert "within 7 working days of delivery" in claims["text"] and claims["pages"] == [29]
    assert len(doc["chunk_ids"]) <= 5


def test_handbook_versions(index):
    assert index.documents["employee_handbook_2024.pdf"]["status"] == "superseded"
    assert index.documents["employee_handbook_2024.pdf"]["superseded_by"] == "employee_handbook_2025.pdf"
    assert index.documents["employee_handbook_2025.pdf"]["status"] == "current"
    assert "SUPERSEDED" in index.full_context


def test_rate_table_rows_are_readable(index):
    c = chunk(index, "pricing_sheet_2025.pdf", "Document header")
    assert "Origin: Karachi; Destination: Quetta; Distance (km): 690" in c["text"]
    assert "Fuel surcharge: 9.5%" in c["text"]


def test_full_context_fits_budget(index):
    assert index.full_context_tokens_estimate < config.FULL_CONTEXT_TOKEN_BUDGET


# ------------------------------------------------------------------ citations
def test_locate_tolerates_whitespace_case_punctuation(index):
    c = chunk(index, "warehouse_safety_sop.pdf", "4. Incident")
    assert locate("step 3 complete incident form IR-01 within 24 hours of the event", c["text"])
    assert locate("This sentence is not in the document at all, anywhere.", c["text"]) is None


def test_verify_maps_page_across_page_break_and_rejects_fabrication(index):
    c = chunk(index, "warehouse_safety_sop.pdf", "4. Incident")
    sources, rejected = verify([
        {"chunk_id": c["id"], "quote": "Step 6. Corrective actions are assigned with an owner and a due date"},
        {"chunk_id": c["id"], "quote": "Employees receive a bonus for every incident reported."},
        {"chunk_id": "C999", "quote": "anything"},
    ], index.chunks, index.documents)
    assert len(sources) == 1 and sources[0]["location"] == "page 2"
    assert len(rejected) == 2


def test_superseded_source_is_labelled(index):
    c = chunk(index, "employee_handbook_2024.pdf", "4. Annual")
    sources, _ = verify([{"chunk_id": c["id"], "quote": "entitled to 14 days of paid annual leave"}],
                        index.chunks, index.documents)
    assert sources[0]["document_status"] == "superseded by employee_handbook_2025.pdf"


# ------------------------------------------------------------------ retrieval mode
def test_bm25_finds_needle_and_pulls_other_version(index):
    ids = index.search("deadline for filing a damaged cargo claim", 3)
    assert chunk(index, "operations_manual_full.pdf", "10. Claims")["id"] in ids
    ids = index.search("annual leave days", 2)
    docs = {index.chunks[i]["doc"] for i in ids}
    assert {"employee_handbook_2024.pdf", "employee_handbook_2025.pdf"} <= docs


# ------------------------------------------------------------------ QA loop with a fake model
class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kw):
        self.calls.append(kw)
        body = self.replies.pop(0)
        usage = SimpleNamespace(input_tokens=20, cache_creation_input_tokens=0,
                                cache_read_input_tokens=7000, output_tokens=120)
        return SimpleNamespace(stop_reason="end_turn", usage=usage,
                               content=[SimpleNamespace(type="text", text=json.dumps(body))])


def test_answer_keeps_only_verified_sources(index):
    c = chunk(index, "operations_manual_full.pdf", "10. Claims")
    fake = FakeClient([{"status": "answered", "answer": "Within 7 working days of delivery.", "citations": [
        {"chunk_id": c["id"], "quote": "Damaged cargo claims must be filed within 7 working days of delivery."},
        {"chunk_id": c["id"], "quote": "Claims can be filed up to 90 days later with manager approval."}]}])
    a = asyncio.run(QAService(index, client=fake, model="claude-haiku-4-5", mode="full_context").ask("claim deadline?"))
    assert a.status == "answered" and len(a.sources) == 1 and a.sources[0]["location"] == "page 29"
    assert len(a.rejected_citations) == 1 and len(fake.calls) == 1
    # cost: 20 in @ $1/M + 7000 cache-read @ $0.1/M + 120 out @ $5/M
    assert a.usage.cost_usd("claude-haiku-4-5") == pytest.approx(20e-6 + 7000 * 0.1e-6 + 120 * 5e-6)


def test_unverifiable_answer_is_retried_then_withheld(index):
    bad = {"status": "answered", "answer": "The CEO is Jane Doe.",
           "citations": [{"chunk_id": "C01", "quote": "Jane Doe is the chief executive officer."}]}
    fake = FakeClient([bad, bad])
    a = asyncio.run(QAService(index, client=fake, model="claude-haiku-4-5", mode="full_context").ask("Who is the CEO?"))
    assert len(fake.calls) == 2 and a.status == "unverified" and a.sources == []
    assert "Jane Doe" not in a.answer


def test_not_found_passes_through(index):
    fake = FakeClient([{"status": "not_found", "answer": "The documents do not cover salaries.", "citations": []}])
    a = asyncio.run(QAService(index, client=fake, model="claude-haiku-4-5", mode="full_context").ask("salary?"))
    assert a.status == "not_found" and len(fake.calls) == 1


def test_request_shape_caches_corpus_and_uses_schema(index):
    fake = FakeClient([{"status": "not_found", "answer": "x", "citations": []}])
    asyncio.run(QAService(index, client=fake, model="claude-sonnet-5", mode="full_context").ask("q"))
    kw = fake.calls[0]
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "<documents>" in kw["system"][0]["text"]
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["output_config"]["effort"] == config.EFFORT
