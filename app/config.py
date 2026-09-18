import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CORPUS_DIR = Path(os.getenv("CORPUS_DIR", ROOT / "corpus"))
INDEX_PATH = Path(os.getenv("INDEX_PATH", ROOT / "data" / "index.json"))

MODEL = os.getenv("MODEL", "claude-haiku-4-5")
# "low" keeps latency down on models that support effort; ignored for Haiku 4.5.
EFFORT = os.getenv("EFFORT", "low")
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1200"))

# full_context: whole (deduplicated) corpus in a cached prompt, no retrieval step.
# retrieval:    BM25 top-k chunks only. auto: full_context while the corpus fits.
MODE = os.getenv("MODE", "auto")
FULL_CONTEXT_TOKEN_BUDGET = int(os.getenv("FULL_CONTEXT_TOKEN_BUDGET", "60000"))
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "8"))

# USD per million tokens (Anthropic list prices). Cache writes (5-minute TTL) bill at
# 1.25x input, cache reads at 0.1x input.
PRICES = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00},
}
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10
