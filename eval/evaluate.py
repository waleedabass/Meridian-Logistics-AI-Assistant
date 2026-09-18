"""Run every question in eval_questions.json against a running /ask service.

    python eval/evaluate.py [--url http://127.0.0.1:8000] [--repeat 3]

Writes eval/results.json (every response, verbatim) and eval/results.md (readable
report: pass/fail per question, latency percentiles, cost per query).

Latency is reported two ways: the server's own latency_ms and the client-observed
round trip. p95 uses the nearest-rank method over all runs (26 x repeat samples).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def _n(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace(",", "")).strip()


def grade(resp: dict, key: dict) -> tuple[bool, list[str]]:
    problems = []
    if key["type"] == "unanswerable":
        if resp["status"] != "not_found":
            problems.append(f"expected not_found, got {resp['status']}")
        return not problems, problems
    if resp["status"] != "answered":
        problems.append(f"status {resp['status']}")
    if not resp["sources"]:
        problems.append("no sources (automatic fail)")
    ans = _n(resp["answer"])
    for group in key["must_include"]:
        if not any(_n(alt) in ans for alt in group):
            problems.append(f"missing {group}")
    docs = {s["document"] for s in resp["sources"]}
    if not docs & set(key["expected_docs"]):
        problems.append(f"no source from {key['expected_docs']}")
    return not problems, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--repeat", type=int, default=1, help="passes over the question set (for latency stats)")
    ap.add_argument("--questions", default=str(ROOT / "eval_questions.json"))
    ap.add_argument("--out", default=str(ROOT / "eval"))
    args = ap.parse_args()

    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))["questions"]
    key = json.loads((ROOT / "eval" / "expected.json").read_text(encoding="utf-8"))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=args.url, timeout=60) as client:
        health = client.get("/health").json()
        print(f"Service: model={health['model']} mode={health['mode']} chunks={health['chunks']}")
        runs = []
        for rep in range(args.repeat):
            for q in questions:
                t0 = time.perf_counter()
                r = client.post("/ask", json={"question": q["question"]})
                rt = (time.perf_counter() - t0) * 1000
                if r.status_code != 200:
                    print(f"  [{q['id']:2d}] HTTP {r.status_code}: {r.text[:200]}")
                    runs.append({"id": q["id"], "pass": rep, "question": q["question"], "http_status": r.status_code,
                                 "error": r.text, "client_ms": rt})
                    continue
                body = r.json()
                ok, problems = grade(body, key[str(q["id"])])
                runs.append({"id": q["id"], "pass": rep, "question": q["question"], "response": body,
                             "client_ms": round(rt), "correct": ok, "problems": problems})
                mark = "PASS" if ok else "FAIL"
                print(f"  [{q['id']:2d}] {mark} {body['latency_ms']:5d} ms  {q['question'][:60]}"
                      + ("" if ok else f"  -> {problems}"))

    good = [r for r in runs if "response" in r]
    first = [r for r in good if r["pass"] == 0]
    server_ms = [r["response"]["latency_ms"] for r in good]
    client_ms = [r["client_ms"] for r in good]
    costs = [r["response"]["cost_usd"] for r in good]
    usage_keys = ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens", "calls"]
    mean_usage = {k: round(statistics.mean(r["response"]["usage"][k] for r in good), 1) for k in usage_keys}
    summary = {
        "model": health["model"], "mode": health["mode"], "questions": len(questions), "repeat": args.repeat,
        "samples": len(good), "http_errors": len(runs) - len(good),
        "correct_first_pass": sum(r["correct"] for r in first),
        "correct_all_passes": f"{sum(r['correct'] for r in good)}/{len(good)}",
        "answers_without_sources": sum(1 for r in good if r["response"]["status"] == "answered" and not r["response"]["sources"]),
        "latency_server_ms": {"p50": pct(server_ms, 50), "p95": pct(server_ms, 95), "max": max(server_ms),
                              "mean": round(statistics.mean(server_ms))},
        "latency_client_ms": {"p50": pct(client_ms, 50), "p95": pct(client_ms, 95), "max": max(client_ms)},
        "cost_usd_per_query": {"mean": round(statistics.mean(costs), 6), "max": max(costs)},
        "mean_usage_per_query": mean_usage,
    }
    (out_dir / "results.json").write_text(json.dumps({"summary": summary, "runs": runs}, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    write_markdown(out_dir / "results.md", summary, first, key)
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_dir / 'results.json'} and {out_dir / 'results.md'}")
    return 0


def write_markdown(path: Path, s: dict, first: list[dict], key: dict) -> None:
    L = [
        "# Evaluation results", "",
        f"Model `{s['model']}`, mode `{s['mode']}`, {s['questions']} questions x {s['repeat']} pass(es) "
        f"= {s['samples']} requests. Generated {time.strftime('%Y-%m-%d %H:%M')}.", "",
        "| Metric | Value |", "|---|---|",
        f"| Correct (first pass, graded against `eval/expected.json`) | {s['correct_first_pass']}/{s['questions']} |",
        f"| Correct (all passes) | {s['correct_all_passes']} |",
        f"| Answers returned without a source | {s['answers_without_sources']} |",
        f"| Server latency p50 / p95 / max (ms) | {s['latency_server_ms']['p50']} / {s['latency_server_ms']['p95']} / {s['latency_server_ms']['max']} |",
        f"| Client round-trip p50 / p95 / max (ms) | {s['latency_client_ms']['p50']} / {s['latency_client_ms']['p95']} / {s['latency_client_ms']['max']} |",
        f"| Cost per query, mean / max (USD) | ${s['cost_usd_per_query']['mean']:.5f} / ${s['cost_usd_per_query']['max']:.5f} |",
        f"| Mean tokens per query | uncached in {s['mean_usage_per_query']['input_tokens']}, cache write {s['mean_usage_per_query']['cache_creation_input_tokens']}, cache read {s['mean_usage_per_query']['cache_read_input_tokens']}, out {s['mean_usage_per_query']['output_tokens']} |",
        "", "## Answers (first pass)", "",
    ]
    for r in first:
        resp = r["response"]
        k = key[str(r["id"])]
        L.append(f"### {r['id']}. {r['question']}")
        L.append(f"**{'PASS' if r['correct'] else 'FAIL'}** · status `{resp['status']}` · {resp['latency_ms']} ms · "
                 f"${resp['cost_usd']:.5f}" + (f" · problems: {r['problems']}" if r["problems"] else ""))
        if k.get("trap"):
            L.append(f"\n_What this question tests: {k['trap']}_")
        L.append("\n" + resp["answer"].replace("\n", "\n\n") + "\n")
        for src in resp["sources"]:
            extra = f" ({src['document_status']})" if src.get("document_status") else ""
            L.append(f"- `{src['document']}`, {src['location']}{extra}: \"{src['snippet']}\"")
        L.append("")
    path.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
