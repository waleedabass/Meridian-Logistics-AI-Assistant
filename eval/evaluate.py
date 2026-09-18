# Runs all the questions in eval_questions.json against the running service
# and grades them with eval/expected.json.
#
#   python eval/evaluate.py --url http://127.0.0.1:8000 --repeat 3
#
# Output: eval/results.json (all raw responses) and eval/results.md (report)

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


def percentile(values, p):
    # nearest-rank percentile
    values = sorted(values)
    rank = math.ceil(p / 100 * len(values))
    return values[max(0, rank - 1)]


def clean(text):
    # lowercase, drop commas (so "24,500" matches "24500"), collapse spaces
    text = text.lower().replace(",", "")
    return re.sub(r"\s+", " ", text).strip()


def grade(response, expected):
    """Returns (passed, list of problems)."""
    problems = []

    if expected["type"] == "unanswerable":
        if response["status"] != "not_found":
            problems.append(f"expected not_found, got {response['status']}")
        return len(problems) == 0, problems

    if response["status"] != "answered":
        problems.append(f"status {response['status']}")
    if not response["sources"]:
        problems.append("no sources (automatic fail)")

    answer = clean(response["answer"])
    for options in expected["must_include"]:
        # at least one of the options has to be in the answer
        found = False
        for option in options:
            if clean(option) in answer:
                found = True
        if not found:
            problems.append(f"missing {options}")

    source_docs = set(s["document"] for s in response["sources"])
    if not source_docs & set(expected["expected_docs"]):
        problems.append(f"no source from {expected['expected_docs']}")

    return len(problems) == 0, problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--repeat", type=int, default=1, help="how many times to run the whole question set")
    parser.add_argument("--questions", default=str(ROOT / "eval_questions.json"))
    parser.add_argument("--out", default=str(ROOT / "eval"))
    args = parser.parse_args()

    with open(args.questions, encoding="utf-8") as f:
        questions = json.load(f)["questions"]
    with open(ROOT / "eval" / "expected.json", encoding="utf-8") as f:
        expected = json.load(f)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = []
    client = httpx.Client(base_url=args.url, timeout=60)
    health = client.get("/health").json()
    print(f"Service: model={health['model']} mode={health['mode']} chunks={health['chunks']}")

    for rep in range(args.repeat):
        for q in questions:
            t0 = time.perf_counter()
            r = client.post("/ask", json={"question": q["question"]})
            client_ms = (time.perf_counter() - t0) * 1000

            if r.status_code != 200:
                print(f"  [{q['id']:2d}] HTTP {r.status_code}: {r.text[:200]}")
                runs.append({"id": q["id"], "pass": rep, "question": q["question"],
                             "http_status": r.status_code, "error": r.text, "client_ms": client_ms})
                continue

            body = r.json()
            passed, problems = grade(body, expected[str(q["id"])])
            runs.append({"id": q["id"], "pass": rep, "question": q["question"], "response": body,
                         "client_ms": round(client_ms), "correct": passed, "problems": problems})

            line = f"  [{q['id']:2d}] {'PASS' if passed else 'FAIL'} {body['latency_ms']:5d} ms  {q['question'][:60]}"
            if not passed:
                line += f"  -> {problems}"
            print(line)
    client.close()

    ok_runs = [r for r in runs if "response" in r]
    first_pass = [r for r in ok_runs if r["pass"] == 0]
    server_ms = [r["response"]["latency_ms"] for r in ok_runs]
    client_ms = [r["client_ms"] for r in ok_runs]
    costs = [r["response"]["cost_usd"] for r in ok_runs]

    mean_usage = {}
    for key in ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens", "calls"]:
        mean_usage[key] = round(statistics.mean(r["response"]["usage"][key] for r in ok_runs), 1)

    no_source = 0
    for r in ok_runs:
        if r["response"]["status"] == "answered" and not r["response"]["sources"]:
            no_source += 1

    summary = {
        "model": health["model"],
        "mode": health["mode"],
        "questions": len(questions),
        "repeat": args.repeat,
        "samples": len(ok_runs),
        "http_errors": len(runs) - len(ok_runs),
        "correct_first_pass": sum(1 for r in first_pass if r["correct"]),
        "correct_all_passes": f"{sum(1 for r in ok_runs if r['correct'])}/{len(ok_runs)}",
        "answers_without_sources": no_source,
        "latency_server_ms": {"p50": percentile(server_ms, 50), "p95": percentile(server_ms, 95),
                              "max": max(server_ms), "mean": round(statistics.mean(server_ms))},
        "latency_client_ms": {"p50": percentile(client_ms, 50), "p95": percentile(client_ms, 95),
                              "max": max(client_ms)},
        "cost_usd_per_query": {"mean": round(statistics.mean(costs), 6), "max": max(costs)},
        "mean_usage_per_query": mean_usage,
    }

    with open(out_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "runs": runs}, f, indent=2, ensure_ascii=False)
    write_report(out_dir / "results.md", summary, first_pass, expected)

    print(json.dumps(summary, indent=2))
    print(f"Wrote {out_dir / 'results.json'} and {out_dir / 'results.md'}")
    return 0


def write_report(path, s, first_pass, expected):
    lat = s["latency_server_ms"]
    cl = s["latency_client_ms"]
    cost = s["cost_usd_per_query"]
    u = s["mean_usage_per_query"]

    lines = [
        "# Evaluation results",
        "",
        f"Model `{s['model']}`, mode `{s['mode']}`, {s['questions']} questions x {s['repeat']} pass(es) "
        f"= {s['samples']} requests. Generated {time.strftime('%Y-%m-%d %H:%M')}.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Correct (first pass, graded against `eval/expected.json`) | {s['correct_first_pass']}/{s['questions']} |",
        f"| Correct (all passes) | {s['correct_all_passes']} |",
        f"| Answers returned without a source | {s['answers_without_sources']} |",
        f"| Server latency p50 / p95 / max (ms) | {lat['p50']} / {lat['p95']} / {lat['max']} |",
        f"| Client round-trip p50 / p95 / max (ms) | {cl['p50']} / {cl['p95']} / {cl['max']} |",
        f"| Cost per query, mean / max (USD) | ${cost['mean']:.5f} / ${cost['max']:.5f} |",
        f"| Mean tokens per query | uncached in {u['input_tokens']}, cache write {u['cache_creation_input_tokens']}, "
        f"cache read {u['cache_read_input_tokens']}, out {u['output_tokens']} |",
        "",
        "## Answers (first pass)",
        "",
    ]

    for r in first_pass:
        resp = r["response"]
        exp = expected[str(r["id"])]
        lines.append(f"### {r['id']}. {r['question']}")
        result = "PASS" if r["correct"] else "FAIL"
        status_line = f"**{result}** · status `{resp['status']}` · {resp['latency_ms']} ms · ${resp['cost_usd']:.5f}"
        if r["problems"]:
            status_line += f" · problems: {r['problems']}"
        lines.append(status_line)
        if exp.get("trap"):
            lines.append(f"\n_What this question tests: {exp['trap']}_")
        lines.append("\n" + resp["answer"].replace("\n", "\n\n") + "\n")
        for src in resp["sources"]:
            note = ""
            if src.get("document_status"):
                note = f" ({src['document_status']})"
            lines.append(f"- `{src['document']}`, {src['location']}{note}: \"{src['snippet']}\"")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
