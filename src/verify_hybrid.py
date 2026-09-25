"""Smoke-check real hybrid routing against the measured calibration snapshot."""

from .contracts import validate_search_results
from .corpus_io import read_json, utc_now, write_json
from .task4_chunking_indexing import ROOT, get_collection, load_documents, chunk_documents
from .task9_retrieval_pipeline import SCORE_THRESHOLD, retrieve_with_trace


def main() -> None:
    calibration = read_json(ROOT / "reports/THRESHOLD_CALIBRATION.json")
    assert calibration["threshold"] == SCORE_THRESHOLD, "Recalibrate after changing threshold"
    assert calibration["chunk_sha256"] == get_collection().metadata["chunk_sha256"]
    expected = {chunk["id"]: chunk for chunk in chunk_documents(load_documents())}
    # One supported query, one clearly outside corpus, one near-domain question
    # that looks relevant but cannot be answered from these public documents.
    selected = [next(p for p in calibration["probes"] if p["label"] == label)
                for label in ("in_domain", "out_of_domain", "unsupported_near_domain")]
    probes = []
    for probe in selected:
        trace = retrieve_with_trace(probe["query"], top_k=5)
        assert trace["rrf_calls"] == 1
        assert trace["fallback_attempted"] == probe["fallback_expected"]
        assert abs(trace["best_dense_score"] - probe["best_dense_score"]) < 1e-6
        validate_search_results(trace["results"], top_k=5)
        for result in trace["results"]:
            if result["retrieval_method"] == "hybrid":
                assert result["content"] == expected[result["id"]]["content"]
                assert result["metadata"] == expected[result["id"]]["metadata"]
        probes.append({"label": probe["label"], "query": probe["query"], **trace})
        print(f"{probe['label']}: cosine={trace['best_dense_score']:.6f}, "
              f"RRF={trace['rrf_calls']}, fallback={trace['fallback_status']}, "
              f"results={len(trace['results'])}", flush=True)
    report = {"checked_at": utc_now(), "corpus_sha256": calibration["corpus_sha256"],
              "chunk_sha256": calibration["chunk_sha256"], "threshold": SCORE_THRESHOLD,
              "purpose": "real index routing smoke test; no simulated provider response",
              "probes": probes}
    write_json(ROOT / "reports/HYBRID_CHECKPOINT.json", report)


if __name__ == "__main__":
    main()
