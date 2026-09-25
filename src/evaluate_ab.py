"""Reproducible offline A/B evaluation: dense-only vs hybrid + RRF.

The harness deliberately uses a deterministic extractive generator and lexical
metric evaluator because this checkout has no LLM API key. Both configurations
use the same generator, evaluator, prompt-independent tokenizer, corpus snapshot,
and top_k; only retrieval strategy changes. This makes the result useful for
retrieval debugging without pretending to be an LLM-as-judge benchmark.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from collections import Counter
from pathlib import Path

from .corpus_io import read_json, utc_now, write_json
from .task4_chunking_indexing import ROOT, get_collection
from .task9_retrieval_pipeline import retrieve_with_trace

GOLDEN_PATH = ROOT / "group_project/evaluation/golden_dataset.json"
RESULT_PATH = ROOT / "group_project/evaluation/RESULT.md"
JSON_PATH = ROOT / "reports/AB_RESULTS.json"
TOP_K = 5
CONFIG_A_THRESHOLD = -1.0
CONFIG_B_THRESHOLD = -1.0  # disable fallback so only dense vs dense+BM25+RRF differs
SAFE_REFUSAL = "Tôi không thể xác minh thông tin này từ nguồn hiện có."
EVALUATION_PROMPT = "Answer only from retrieved context; do not add outside knowledge."
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
STOPWORDS = {
    "a", "an", "and", "are", "be", "by", "for", "from", "how", "in", "is", "it", "of", "on", "or", "the", "to", "what", "why", "with",
    "các", "cho", "của", "để", "được", "là", "một", "nào", "như", "những", "phải", "sao", "theo", "thế", "và", "về", "với"
}


def tokens(text: str) -> list[str]:
    return [token.casefold() for token in WORD_RE.findall(text) if token.casefold() not in STOPWORDS]


def f1_overlap(answer: str, expected: str) -> float:
    actual, reference = Counter(tokens(answer)), Counter(tokens(expected))
    if not actual or not reference:
        return 0.0
    common = sum((actual & reference).values())
    precision, recall = common / sum(actual.values()), common / sum(reference.values())
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def extractive_generate(results: list[dict], prompt: str = EVALUATION_PROMPT) -> str:
    """Fixed generator shared by A and B; returns only retrieved text."""
    if prompt != EVALUATION_PROMPT:
        raise ValueError("A/B generator prompt is fixed for comparability")
    if not results:
        return SAFE_REFUSAL
    snippets = []
    for result in results[:2]:
        for line in re.split(r"(?:\n|(?<=[.!?])\s+)", result["content"]):
            line = " ".join(line.split())
            if len(line) >= 30 and not line.startswith(("#", "|")):
                snippets.append(line)
                break
    answer = " ".join(snippets)
    return answer[:900] if answer else SAFE_REFUSAL


def score_case(case: dict, trace: dict) -> dict:
    results = trace["results"]
    retrieved_ids = [result["id"] for result in results]
    expected_ids = set(case["expected_context"])
    overlap = expected_ids.intersection(retrieved_ids)
    answer = extractive_generate(results)
    context = "\n".join(result["content"] for result in results)
    answer_tokens = tokens(answer) if answer != SAFE_REFUSAL else []
    context_tokens = set(tokens(context))
    faithfulness = (sum(token in context_tokens for token in answer_tokens) / len(answer_tokens)
                    if answer_tokens else 0.0)
    return {
        "id": case["id"], "question": case["question"], "expected_answer": case["expected_answer"],
        "expected_context": case["expected_context"], "retrieved_ids": retrieved_ids,
        "answer": answer, "answerable_by_fixed_generator": answer != SAFE_REFUSAL,
        "faithfulness": round(faithfulness, 6),
        "answer_relevance": round(f1_overlap(answer, case["expected_answer"]), 6),
        "context_recall": round(len(overlap) / len(expected_ids), 6) if expected_ids else 0.0,
        "context_precision": round(len(overlap) / len(retrieved_ids), 6) if retrieved_ids else 0.0,
        "retrieval_trace": {key: trace.get(key) for key in (
            "best_dense_score", "dense_count", "bm25_count", "rrf_calls", "fallback_attempted", "fallback_status")},
    }


def mean(results: list[dict], key: str) -> float:
    return sum(item[key] for item in results) / len(results) if results else 0.0


def git_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def run_config(name: str, cases: list[dict], *, use_reranking: bool, threshold: float) -> dict:
    rows, started = [], time.perf_counter()
    for case in cases:
        trace = retrieve_with_trace(case["question"], top_k=TOP_K,
                                    score_threshold=threshold, use_reranking=use_reranking)
        rows.append(score_case(case, trace))
    elapsed = time.perf_counter() - started
    metrics = {key: round(mean(rows, key), 6) for key in (
        "faithfulness", "answer_relevance", "context_recall", "context_precision")}
    metrics["average"] = round(sum(metrics.values()) / 4, 6)
    return {"name": name, "use_reranking": use_reranking, "score_threshold": threshold,
            "top_k": TOP_K, "latency_seconds": round(elapsed, 3), "metrics": metrics, "cases": rows}


def failure_stage(row: dict) -> tuple[str, str]:
    if row["context_recall"] < 1.0:
        missing = sorted(set(row["expected_context"]) - set(row["retrieved_ids"]))
        return "retrieval", f"Missed expected context ID(s): {', '.join(missing)}"
    if row["context_precision"] < 0.5:
        return "retrieval", "Expected evidence was retrieved with several non-gold chunks in top_k."
    if row["answer_relevance"] < 0.5:
        return "generation", "The fixed extractive generator returned context text with low overlap to the reference answer."
    if row["faithfulness"] < 0.9:
        return "generation", "Generated tokens were not fully present in retrieved context."
    return "data", "No single metric failure; inspect reference wording and source boundaries."


def render_report(payload: dict) -> str:
    a, b = payload["config_a"], payload["config_b"]
    deltas = {key: round(b["metrics"][key] - a["metrics"][key], 6)
              for key in ("faithfulness", "answer_relevance", "context_recall", "context_precision", "average")}
    rows = []
    for case_a, case_b in zip(a["cases"], b["cases"], strict=True):
        average = sum(case_b[key] for key in ("faithfulness", "answer_relevance", "context_recall", "context_precision")) / 4
        stage, root = failure_stage(case_b)
        rows.append({"row": case_b, "average": average, "stage": stage, "root": root})
    worst = sorted(rows, key=lambda row: (row["average"], row["row"]["id"]))[:3]
    best_metric = max(deltas, key=lambda key: deltas[key])
    recommendations = [
        ("Tăng candidate hoặc rà lại chunk boundary cho các case mất expected_context.",
         "Worst performers có context recall dưới 1 và liệt kê ID bị thiếu.",
         "Tăng candidate chỉ ở bước retrieval và theo dõi recall; không đổi generator.",
         "Chạy lại `python -m src.evaluate_ab` và kiểm tra context_recall từng case."),
        ("Giữ top_k cố định khi tinh chỉnh RRF; xem xét lọc nhiễu sau retrieval.",
         "Một số case có expected evidence nhưng precision thấp do top-5 chứa nhiều chunk khác.",
         "Tăng context precision và giảm context đưa vào generation, đổi lại có thể mất recall.",
         "So sánh precision/recall theo từng case với cùng golden dataset."),
        ("Sau khi thêm LLM key, chạy cùng prompt qua generator thật và đánh giá lại relevance.",
         "Evaluator hiện dùng extractive generator cố định; answer relevance thấp phản ánh wording khác reference.",
         "Đo generation thật mà không thay retrieval, evaluator hoặc top_k giữa A/B.",
         "Ghi model/version và chạy lại cả hai config trong một lần evaluation mới."),
    ]
    lines = ["# RAG evaluation results", "", "## Run information", "",
             "| Field | Value |", "| --- | --- |",
             f"| Evaluation date | {payload['evaluated_at']} |",
             "| Framework and version | `src.evaluate_ab`, deterministic lexical metrics |",
             "| Evaluator model | None; fixed token overlap evaluator |",
             "| Generator model | None; fixed extractive generator shared by A/B |",
             f"| Embedding model | {payload['embedding']['model']} @ `{payload['embedding']['revision']}` |",
             f"| Corpus version/commit | `{payload['git_revision']}`; {payload['working_tree']}; corpus SHA `{payload['corpus_sha256']}` |",
             f"| Golden dataset size | {payload['golden_dataset_size']} |",
             f"| `top_k` | {TOP_K} |",
             f"| Fallback threshold and calibration | Production 0.60; A/B uses -1.0 to disable fallback and isolate retrieval strategy |",
             "", "## Configurations", "",
             "- **Config A — dense-only:** shared local BGE-M3 dense search, no BM25 and no RRF.",
             "- **Config B — hybrid + RRF:** same dense search plus BM25 and one RRF pass (`k=60`).",
             f"- Both use the same corpus snapshot, deterministic extractive generator, evaluator, prompt `{EVALUATION_PROMPT}`, and `top_k=5`. A/B does not call PageIndex.",
             "", "## Overall scores", "",
             "| Metric | Config A | Config B | Delta B−A |", "| --- | ---: | ---: | ---: |"]
    for key, label in (("faithfulness", "Faithfulness"), ("answer_relevance", "Answer relevance"),
                       ("context_recall", "Context recall"), ("context_precision", "Context precision"), ("average", "**Average**")):
        lines.append(f"| {label} | {a['metrics'][key]:.4f} | {b['metrics'][key]:.4f} | {deltas[key]:+.4f} |")
    lines += ["", "## A/B comparison", "",
              f"- Cấu hình có average cao hơn trong lần chạy này: **{'B hybrid + RRF' if deltas['average'] > 0 else 'A dense-only' if deltas['average'] < 0 else 'hòa'}**.",
              f"- Delta theo metric: faithfulness {deltas['faithfulness']:+.4f}, relevance {deltas['answer_relevance']:+.4f}, recall {deltas['context_recall']:+.4f}, precision {deltas['context_precision']:+.4f}.",
              f"- Latency local: A {a['latency_seconds']:.3f}s, B {b['latency_seconds']:.3f}s trên cùng {payload['golden_dataset_size']} query; chênh lệch B−A {b['latency_seconds']-a['latency_seconds']:+.3f}s. Cost API của cả hai là 0 trong evaluator offline.",
              "- Faithfulness ở đây là containment proxy của extractive generator, không phải phán đoán LLM. Không dùng kết quả này để tuyên bố chất lượng generation thật.",
              "", "## Worst performers", "", "| # | Question | Config | Faithfulness | Relevance | Recall | Precision | Failure stage | Root cause |", "| ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- |"]
    for index, item in enumerate(worst, 1):
        row = item["row"]
        lines.append(f"| {index} | {row['question']} | B | {row['faithfulness']:.3f} | {row['answer_relevance']:.3f} | {row['context_recall']:.3f} | {row['context_precision']:.3f} | {item['stage']} | {item['root']} |")
    lines += ["", "## Recommendations", "", "| Priority | Action | Evidence from failure analysis | Expected impact | How to verify |", "| ---: | --- | --- | --- | --- |"]
    for index, recommendation in enumerate(recommendations, 1):
        lines.append(f"| {index} | {recommendation[0]} | {recommendation[1]} | {recommendation[2]} | {recommendation[3]} |")
    lines += ["", "## Reproduction", "", "```powershell", ".\\.venv\\Scripts\\python.exe -m src.evaluate_ab", ".\\.venv\\Scripts\\python.exe -m pytest tests/test_acceptance.py -q", "```", "",
              f"Detailed per-case rows and retrieval traces: [AB_RESULTS.json](../../reports/AB_RESULTS.json). Golden cases: [golden_dataset.json](golden_dataset.json). Production fallback calibration is documented in [THRESHOLD_CALIBRATION.json](../../reports/THRESHOLD_CALIBRATION.json).",
              "", "## Bonus experiments", "", "No bonus experiment is claimed. A real LLM generation run and a reranker comparison require separate controlled measurements with the same dataset and evaluator.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=TOP_K)
    args = parser.parse_args()
    if args.top_k != TOP_K:
        raise SystemExit(f"This report is pinned to top_k={TOP_K}; rerun with the default to keep comparisons reproducible")
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    if len(cases) < 15:
        raise ValueError("Golden dataset must contain at least 15 cases")
    collection = get_collection()
    summary = read_json(ROOT / "data/index/index_summary.json")
    embedding = summary["embedding"]
    corpus_manifest = read_json(ROOT / "data/corpus_manifest.json")
    payload = {"evaluated_at": utc_now(), "git_revision": git_revision(),
               "working_tree": "uncommitted changes present (recorded source snapshot is corpus/chunk SHA)",
               "corpus_sha256": corpus_manifest["corpus_sha256"], "chunk_sha256": collection.metadata["chunk_sha256"],
               "golden_dataset_size": len(cases), "top_k": TOP_K, "embedding": embedding,
               "shared_prompt": EVALUATION_PROMPT,
               "metric_definitions": {"faithfulness": "answer token containment in retrieved context; fixed extractive answer",
                                      "answer_relevance": "token F1 against expected_answer",
                                      "context_recall": "expected_context IDs retrieved / expected_context IDs",
                                      "context_precision": "expected_context IDs / retrieved top_k IDs"}}
    # Warm both local paths before timing so the first model load/BM25 build is
    # not incorrectly attributed to one configuration.
    retrieve_with_trace(cases[0]["question"], top_k=TOP_K, score_threshold=-1.0, use_reranking=False)
    retrieve_with_trace(cases[0]["question"], top_k=TOP_K, score_threshold=-1.0, use_reranking=True)
    payload["config_a"] = run_config("dense-only", cases, use_reranking=False, threshold=CONFIG_A_THRESHOLD)
    payload["config_b"] = run_config("hybrid + RRF", cases, use_reranking=True, threshold=CONFIG_B_THRESHOLD)
    write_json(JSON_PATH, payload)
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(render_report(payload), encoding="utf-8", newline="\n")
    print(json.dumps({"golden_cases": len(cases), "config_a": payload["config_a"]["metrics"],
                      "config_b": payload["config_b"]["metrics"],
                      "latency_seconds": {"A": payload["config_a"]["latency_seconds"], "B": payload["config_b"]["latency_seconds"]},
                      "report": str(RESULT_PATH), "details": str(JSON_PATH)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
