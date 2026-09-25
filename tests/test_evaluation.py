"""Invariants for the reproducible A/B evaluation artifact."""

import json
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_golden_context_ids_exist_in_the_index_snapshot():
    dataset = json.loads((ROOT / "group_project/evaluation/golden_dataset.json").read_text(encoding="utf-8"))
    chunk_ids = {item["id"] for item in json.loads((ROOT / "data/index/chunks.json").read_text(encoding="utf-8"))}
    assert len(dataset) >= 15
    assert len({item["id"] for item in dataset}) == len(dataset)
    for item in dataset:
        assert item["question"].strip() and item["expected_answer"].strip()
        assert set(item["expected_context"]) <= chunk_ids


def test_ab_artifact_has_same_controls_and_bounded_metrics():
    artifact = json.loads((ROOT / "reports/AB_RESULTS.json").read_text(encoding="utf-8"))
    a, b = artifact["config_a"], artifact["config_b"]
    assert artifact["golden_dataset_size"] >= 15
    assert a["top_k"] == b["top_k"] == artifact["top_k"] == 5
    assert len(a["cases"]) == len(b["cases"]) == artifact["golden_dataset_size"]
    assert a["use_reranking"] is False and b["use_reranking"] is True
    assert a["score_threshold"] == b["score_threshold"] == -1.0
    for config in (a, b):
        assert set(config["metrics"]) == {"faithfulness", "answer_relevance", "context_recall", "context_precision", "average"}
        assert all(0 <= value <= 1 for value in config["metrics"].values())
    assert artifact["shared_prompt"]


def test_result_report_has_analysis_without_placeholders():
    report = (ROOT / "group_project/evaluation/RESULT.md").read_text(encoding="utf-8")
    lowered = report.lower()
    assert "todo" not in lowered
    for heading in ("overall scores", "a/b comparison", "worst performers", "recommendations"):
        assert heading in lowered
