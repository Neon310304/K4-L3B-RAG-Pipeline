"""Measure a small routing calibration set; not a held-out A/B evaluation."""

import argparse

from .corpus_io import read_json, utc_now, write_json
from .task4_chunking_indexing import ROOT, embedding_config, get_collection
from .task5_semantic_search import semantic_search

# Labels are fixed before running; near-domain unsupported queries expose limits
# of using embedding similarity as a proxy for answerability.
PROBES = [
    ("in_domain", "How long must a password be when used as the only authentication factor?"),
    ("in_domain", "Mật khẩu dùng làm yếu tố xác thực duy nhất cần dài tối thiểu bao nhiêu ký tự?"),
    ("in_domain", "What are the three types of authentication factors?"),
    ("in_domain", "NIST SP 800-63B-4 phishing resistance"),
    ("in_domain", "Tôi cần làm gì sau khi bị lừa đảo phishing?"),
    ("in_domain", "audience restriction FAL2 assertions"),
    ("out_of_domain", "How do I bake a chocolate cake?"),
    ("out_of_domain", "Cách nấu phở bò tại nhà như thế nào?"),
    ("out_of_domain", "What is the capital of Australia?"),
    ("out_of_domain", "Explain photosynthesis in plants."),
    ("out_of_domain", "Giải phương trình bậc hai x^2 - 5x + 6 = 0."),
    ("out_of_domain", "How do I replace a bicycle tire?"),
    ("unsupported_near_domain", "What is the password of my personal email account?"),
    ("unsupported_near_domain", "What exact buttons should I press to enable MFA in the current Instagram app?"),
    ("unsupported_near_domain", "Which password manager has the cheapest family subscription today?"),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.60)
    args = parser.parse_args()
    probes = []
    for label, query in PROBES:
        dense = semantic_search(query, top_k=10)
        best = max((item["score"] for item in dense), default=None)
        probes.append({"label": label, "query": query, "best_dense_score": best,
                       "fallback_expected": best is None or best < args.threshold,
                       "dense_top_3": dense[:3]})
        print(f"{label}: {best:.6f} | {query}", flush=True)
    in_scores = [p["best_dense_score"] for p in probes if p["label"] == "in_domain"]
    out_scores = [p["best_dense_score"] for p in probes if p["label"] == "out_of_domain"]
    report = {"measured_at": utc_now(), "purpose": "small routing calibration, not held-out evaluation",
              "corpus_sha256": read_json(ROOT / "data/corpus_manifest.json")["corpus_sha256"],
              "chunk_sha256": get_collection().metadata["chunk_sha256"],
              "embedding": embedding_config(), "candidate_top_k": 10,
              "threshold": args.threshold, "rule": "fallback when no dense result or max(original cosine) < threshold",
              "in_domain_min": min(in_scores), "out_of_domain_max": max(out_scores),
              "separating_interval": [max(out_scores), min(in_scores)], "probes": probes}
    write_json(ROOT / "reports/THRESHOLD_CALIBRATION.json", report)


if __name__ == "__main__":
    main()
