"""Real-index checkpoint: reindex stability, provenance, and bilingual search probes.

Run after Task 4. This is an integration check, not the golden A/B evaluation.
"""

import json
from collections import Counter
from importlib.metadata import version

import numpy as np

from . import task4_chunking_indexing as indexing
from . import task6_lexical_search as lexical
from .contracts import validate_search_results
from .corpus_io import read_json, utc_now, write_json
from .task5_semantic_search import semantic_search

QUERIES = [
    "How long must a password be when used as the only authentication factor?",
    "Mật khẩu dùng làm yếu tố xác thực duy nhất cần dài tối thiểu bao nhiêu ký tự?",
    "NIST SP 800-63B-4 phishing resistance",
    "What are the three types of authentication factors?",
    "Tôi cần làm gì sau khi bị lừa đảo phishing?",
    "audience restriction FAL2 assertions",
]


def main() -> None:
    collection = indexing.get_collection()
    indexing.ensure_ready(collection)
    expected = indexing.chunk_documents(indexing.load_documents())
    before = indexing.stored_chunks(collection, embeddings=True)
    assert indexing.chunk_fingerprint(before) == indexing.chunk_fingerprint(expected)
    vectors_before = np.asarray([c["embedding"] for c in before], dtype=np.float32)
    assert vectors_before.shape == (len(expected), indexing.EMBEDDING_DIM)
    np.testing.assert_allclose(np.linalg.norm(vectors_before, axis=1), 1, atol=1e-5)
    first_summary = read_json(indexing.ROOT / "data/index/index_summary.json")
    indexing.run_pipeline()
    after = indexing.stored_chunks(indexing.get_collection(), embeddings=True)
    second_summary = read_json(indexing.ROOT / "data/index/index_summary.json")
    assert indexing.chunk_fingerprint(before) == indexing.chunk_fingerprint(after), "Reindex changed IDs, content or metadata"
    vectors_after = np.asarray([c["embedding"] for c in after], dtype=np.float32)
    # Chroma normalizes float32 vectors for cosine on every upsert, so a
    # repeated normalization can differ by a few floating-point ULPs.
    np.testing.assert_allclose(vectors_before, vectors_after, rtol=1e-6, atol=1e-6)
    assert second_summary["embedded_this_run"] == 0
    assert indexing.get_collection().count() == len(expected)
    by_id = {c["id"]: c for c in expected}
    probes = []
    for query in QUERIES:
        outputs = {}
        for method, search in (("dense", semantic_search), ("bm25", lexical.lexical_search)):
            results = search(query, top_k=3)
            validate_search_results(results, top_k=3, expected_method=method)
            for result in results:
                original = by_id[result["id"]]
                assert result["content"] == original["content"]
                assert result["metadata"] == original["metadata"]
            outputs[method] = results
            print(f"{method}: {query}", flush=True)
            for item in results:
                print(f"  {item['score']:.5f} {item['id']} page={item['metadata'].get('pdf_page', '-')}", flush=True)
        probes.append({"query": query, **outputs})
    assert len(lexical._CACHE[1]) == len(expected)
    assert indexing.chunk_fingerprint(lexical._CACHE[1]) == indexing.chunk_fingerprint(expected)
    lengths = np.array([len(c["content"]) for c in expected])
    report = {"checked_at": utc_now(), "purpose": "retrieval checkpoint; not an A/B evaluation",
              "corpus_sha256": read_json(indexing.ROOT / "data/corpus_manifest.json")["corpus_sha256"],
              "index_before_check": first_summary, "reindex_run": second_summary,
              "idempotence": {"before_count": len(before), "after_count": len(after),
                              "same_ids_content_metadata": True,
                              "vectors_equal_within_1e_6": True,
                              "maximum_vector_delta": float(np.max(np.abs(vectors_before-vectors_after)))},
              "shared_dense_bm25_chunk_count": len(expected),
              "chunks_per_document": dict(Counter(c["metadata"]["document_id"] for c in expected)),
              "chunk_characters": {"min": int(lengths.min()), "median": float(np.median(lengths)),
                                   "p95": float(np.percentile(lengths, 95)), "max": int(lengths.max())},
              "versions": {name: version(name) for name in ("chromadb", "sentence-transformers", "torch", "rank-bm25", "langchain-text-splitters")},
              "probes": probes}
    output = indexing.ROOT / "reports/RETRIEVAL_CHECKPOINT.json"
    write_json(output, report)
    print(f"Verified {len(expected)} chunks. Evidence: {output}", flush=True)


if __name__ == "__main__":
    main()
