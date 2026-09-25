"""Offline retrieval regressions, including a real temporary Chroma database."""

import copy
import json
import pytest
import yaml

from src import task4_chunking_indexing as indexing
from src import task5_semantic_search as dense
from src import task6_lexical_search as lexical
from src.contracts import validate_search_results


def chunk(identifier="doc::chunk-0", content="password protection", vector=None):
    return {"id": identifier, "content": content,
            "metadata": {"source": "policy.md", "title": "Account security", "doc_type": "legal",
                         "url": None, "chunk_index": int(identifier.rsplit("-", 1)[-1])},
            "embedding": vector if vector is not None else [1.0, 0.0, 0.0]}


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(indexing, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(indexing, "EMBEDDING_DIM", 3)
    monkeypatch.setattr(indexing, "COLLECTION_NAME", "retrieval_test")
    monkeypatch.setattr(lexical, "_CACHE", None)
    monkeypatch.setattr(lexical, "CORPUS", [])
    def no_encoder():
        pytest.fail("Offline regression tests must not load an embedding model")
    monkeypatch.setattr(indexing, "_embedding_model", no_encoder)
    return indexing.get_collection


def test_load_excludes_yaml_and_retains_source_identity(tmp_path, monkeypatch):
    directory = tmp_path / "legal"
    directory.mkdir()
    metadata = {"id": "nist-policy", "title": "Policy", "url": "https://www.nist.gov/policy",
                "doc_type": "legal", "landing_file": "data/landing/legal/policy.pdf",
                "landing_sha256": "abc", "date_crawled": "2026-09-25T00:00:00+00:00"}
    (directory / "policy.md").write_text("---\n" + yaml.safe_dump(metadata) +
        "---\n\n# Policy\n\n## PDF page 3\n\nPasswords require protection.\n", encoding="utf-8")
    monkeypatch.setattr(indexing, "STANDARDIZED_DIR", tmp_path)
    document, = indexing.load_documents()
    assert document["id"] == "nist-policy"
    assert "landing_sha256" not in document["content"]
    assert "date_crawled" not in document["content"]
    assert document["metadata"]["url"] == metadata["url"]
    assert document["metadata"]["source"] == "policy.md"
    assert document["metadata"]["landing_file"] == metadata["landing_file"]


def test_load_rejects_a_changed_corpus_snapshot(tmp_path, monkeypatch):
    directory = tmp_path / "standardized" / "news"
    directory.mkdir(parents=True)
    (directory / "article.md").write_text("modified content", encoding="utf-8")
    (tmp_path / "corpus_manifest.json").write_text(json.dumps({"documents": [
        {"standardized_file": "data/standardized/news/article.md", "standardized_sha256": "original-hash"}
    ]}), encoding="utf-8")
    monkeypatch.setattr(indexing, "STANDARDIZED_DIR", directory.parent)
    with pytest.raises(ValueError, match="manifest mismatch"):
        indexing.load_documents()


def test_page_chunks_are_stable_bounded_and_do_not_mutate_inputs():
    document = chunk()
    document.pop("embedding")
    document["content"] = "## PDF page 11\n\n" + "Passwords protect accounts. " * 45 + "\n\n## PDF page 12\n\n" + "MFA adds protection. " * 45
    before = copy.deepcopy(document)
    chunks = indexing.chunk_documents([document])
    assert document == before
    assert chunks == indexing.chunk_documents([document])
    assert {c["metadata"]["pdf_page"] for c in chunks} == {11, 12}
    assert [c["metadata"]["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert len({c["id"] for c in chunks}) == len(chunks)
    assert all(0 < len(c["content"]) <= indexing.CHUNK_SIZE for c in chunks)
    assert all("PDF page" not in c["content"] for c in chunks)
    assert all(not ("Passwords" in c["content"] and "MFA" in c["content"]) for c in chunks)


def test_embed_chunks_preserves_metadata_and_checks_dimensions(monkeypatch):
    monkeypatch.setattr(indexing, "EMBEDDING_DIM", 3)
    item = chunk()
    item.pop("embedding")
    monkeypatch.setattr(indexing, "embed_texts", lambda texts: [[1, 0, 0] for _ in texts])
    result = indexing.embed_chunks([item])
    assert "embedding" not in item
    assert result[0]["metadata"] == item["metadata"]
    assert result[0]["metadata"] is not item["metadata"]
    monkeypatch.setattr(indexing, "embed_texts", lambda texts: [[1, 0]])
    with pytest.raises(ValueError, match="dimension"):
        indexing.embed_chunks([item])


def test_embedding_refuses_truncation_without_encoding(monkeypatch):
    class Encoder:
        def tokenizer(self, texts, **kwargs):
            return {"length": [indexing.EMBEDDING_MAX_TOKENS + 1]}
        def encode(self, *args, **kwargs):
            pytest.fail("Oversized text must not be silently truncated")
    monkeypatch.setattr(indexing, "_embedding_model", lambda: Encoder())
    with pytest.raises(ValueError, match="exceeds"):
        indexing.embed_texts(["long text"])
    assert indexing.embed_texts([]) == []


def test_real_chroma_upsert_is_idempotent_and_removes_stale_chunks(database):
    data = [chunk(), chunk("doc::chunk-1", "MFA", [0, 1, 0])]
    indexing.index_to_vectorstore(data)
    first = indexing.stored_chunks(database(), embeddings=True)
    indexing.index_to_vectorstore(data)
    assert indexing.stored_chunks(database(), embeddings=True) == first
    assert database().count() == 2
    changed = chunk(content="updated password rule", vector=[0, 0, 1])
    indexing.index_to_vectorstore([changed])
    stored, = indexing.stored_chunks(database(), embeddings=True)
    assert stored == changed
    assert database().count() == 1
    assert database().metadata["chunk_sha256"] == indexing.chunk_fingerprint([changed])


@pytest.mark.parametrize("bad_vector", [[1, 0], [float('nan'), 0, 1], [0, 0, 0]])
def test_bad_embedding_does_not_change_a_ready_index(database, bad_vector):
    indexing.index_to_vectorstore([chunk()])
    before = database().metadata
    with pytest.raises(ValueError):
        indexing.index_to_vectorstore([chunk(vector=bad_vector)])
    assert database().metadata == before
    assert database().count() == 1


def test_duplicate_ids_and_empty_snapshot_cannot_destroy_index(database):
    indexing.index_to_vectorstore([chunk()])
    for data in ([], [chunk(), chunk()]):
        with pytest.raises(ValueError):
            indexing.index_to_vectorstore(data)
    assert database().count() == 1


def test_model_change_even_with_same_dimension_is_rejected(database, monkeypatch):
    indexing.index_to_vectorstore([chunk()])
    monkeypatch.setattr(indexing, "EMBEDDING_REVISION", "different-revision")
    with pytest.raises(ValueError, match="Embedding configuration differs"):
        database()


def test_failed_write_blocks_search_until_repaired(database, monkeypatch):
    indexing.index_to_vectorstore([chunk()])
    collection = database()
    def failed_upsert(*args, **kwargs):
        raise RuntimeError("simulated disk error")
    with monkeypatch.context() as patch:
        patch.setattr(type(collection), "upsert", failed_upsert)
        with pytest.raises(RuntimeError, match="disk error"):
            indexing.index_to_vectorstore([chunk(content="new text")])
    with pytest.raises(RuntimeError, match="incomplete"):
        indexing.ensure_ready(database())
    indexing.index_to_vectorstore([chunk()])
    indexing.ensure_ready(database())


def test_dense_scores_and_bm25_share_stored_ids_metadata(database, monkeypatch):
    items = [chunk(), chunk("doc::chunk-1", "phishing security key", [0, 1, 0])]
    indexing.index_to_vectorstore(items)
    monkeypatch.setattr(dense, "embed_texts", lambda texts: [[1, 0, 0]])
    results = dense.semantic_search("password", 100)
    validate_search_results(results, top_k=100, expected_method="dense")
    assert len(results) == 2
    assert results[0]["id"] == items[0]["id"]
    assert results[0]["score"] == pytest.approx(1)
    assert results[1]["score"] == pytest.approx(0)
    lexical_results = lexical.lexical_search("password", 100)
    assert lexical_results[0]["id"] == items[0]["id"]
    assert lexical_results[0]["metadata"] == results[0]["metadata"]
    assert lexical.lexical_search("qzxw987nomatch", 10) == []
    assert len(lexical._CACHE[1]) == database().count()
    indexing.index_to_vectorstore([chunk("doc::chunk-2", "passkeys")])
    assert lexical.lexical_search("password") == []
    assert lexical.lexical_search("passkeys")[0]["id"] == "doc::chunk-2"


def test_empty_queries_do_not_open_database(monkeypatch):
    def no_db():
        pytest.fail("Empty query must not touch Chroma or the model")
    for module, search in ((dense, dense.semantic_search), (lexical, lexical.lexical_search)):
        monkeypatch.setattr(module, "get_collection", no_db)
        assert search("  ") == []
        assert search("password", 0) == []
        assert search("password", -1) == []
        with pytest.raises(TypeError):
            search("password", 2.5)


def test_dense_preserves_negative_cosine_and_handles_unsorted_duplicates(monkeypatch):
    class Collection:
        def query(self, **kwargs):
            assert kwargs["query_embeddings"] == [[1, 0, 0]]
            return {"ids": [["doc::chunk-0", "doc::chunk-1", "doc::chunk-0", "doc::chunk-2"]],
                    "documents": [["weak", "strong", "weak", "opposite"]],
                    "metadatas": [[chunk()["metadata"] for _ in range(4)]],
                    "distances": [[0.8, 0.1, 0.9, 1.2]]}
    monkeypatch.setattr(dense, "get_collection", Collection)
    monkeypatch.setattr(dense, "embed_texts", lambda texts: [[1, 0, 0]])
    results = dense.semantic_search("protection", 4)
    assert [r["id"] for r in results] == ["doc::chunk-1", "doc::chunk-0", "doc::chunk-2"]
    assert [r["score"] for r in results] == pytest.approx([0.9, 0.2, -0.2])


def test_bm25_supports_small_corpora_and_publication_identifiers():
    items = [chunk(content="NIST SP 800-63B-4 requires secure passwords")]
    model = lexical.build_bm25_index(items)
    assert model.get_scores(lexical.tokenize("800-63b-4"))[0] > 0
    assert model.get_scores(lexical.tokenize("unmatchedxyz"))[0] == 0
    assert lexical.build_bm25_index([]) is None
    assert "800-63b-4" in lexical.tokenize("NIST SP 800-63B-4")
    assert "63b" in lexical.tokenize("NIST SP 800-63B-4")
