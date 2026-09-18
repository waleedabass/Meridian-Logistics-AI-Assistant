import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CORPUS_DIR = Path(os.getenv("CORPUS_DIR", ROOT / "corpus"))
INDEX_PATH = Path(os.getenv("INDEX_PATH", ROOT / "data" / "index.json"))

MODEL = os.getenv("MODEL", "claude-haiku-4-5")
EFFORT = os.getenv("EFFORT", "low")  # not used for haiku
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1200"))

# auto = send the whole corpus if it fits in the budget, otherwise use bm25 retrieval
MODE = os.getenv("MODE", "auto")
FULL_CONTEXT_TOKEN_BUDGET = int(os.getenv("FULL_CONTEXT_TOKEN_BUDGET", "60000"))
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "8"))

# $ per million tokens, from anthropic's pricing page
PRICES = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00},
}
# cache writes cost 1.25x the input price, cache reads 0.1x
CACHE_WRITE_MULT = 1.25
CACHE_READ_MULT = 0.10
