"""Load provenance, chunk deterministically, embed locally, and synchronize Chroma."""

import copy
import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml
from dotenv import load_dotenv

from .contracts import validate_document
from .corpus_io import read_json, sha256, write_json

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
STANDARDIZED_DIR = ROOT / "data" / "standardized"
CHROMA_DIR = ROOT / "chroma_db"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
CHUNKING_METHOD = "recursive"
CHUNK_VERSION = "recursive-pages-v1"
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_REVISION = os.getenv("EMBEDDING_REVISION") or (
    "5617a9f61b028005a4858fdac845db406aefb181" if EMBEDDING_MODEL == "BAAI/bge-m3" else ""
)
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM") or (1024 if EMBEDDING_MODEL == "BAAI/bge-m3" else 0))
EMBEDDING_MAX_TOKENS = 512
EMBEDDING_BATCH_SIZE = 16
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "rag_documents")
UPSERT_BATCH_SIZE = 128


def embedding_config() -> dict:
    if EMBEDDING_PROVIDER != "sentence_transformers":
        raise ValueError("This retrieval implementation uses sentence_transformers; no paid provider is called")
    if not EMBEDDING_REVISION or EMBEDDING_DIM <= 0:
        raise ValueError("Set EMBEDDING_REVISION and EMBEDDING_DIM when changing the local model")
    return {"provider": EMBEDDING_PROVIDER, "model": EMBEDDING_MODEL,
            "revision": EMBEDDING_REVISION, "dimension": EMBEDDING_DIM,
            "max_tokens": EMBEDDING_MAX_TOKENS, "normalize": True, "prompt": ""}


@lru_cache(maxsize=1)
def _embedding_model():
    import torch
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    from sentence_transformers import SentenceTransformer
    config = embedding_config()
    cache = os.getenv("SENTENCE_TRANSFORMERS_HOME")
    torch.set_num_threads(min(8, os.cpu_count() or 1))
    try:
        model_path = snapshot_download(config["model"], revision=config["revision"],
                                       cache_dir=cache, local_files_only=True)
        model = SentenceTransformer(model_path, device="cpu", local_files_only=True,
                                    trust_remote_code=False)
    except LocalEntryNotFoundError:
        model = SentenceTransformer(config["model"], revision=config["revision"],
                                    cache_folder=cache, device="cpu", trust_remote_code=False)
    model.max_seq_length = EMBEDDING_MAX_TOKENS
    if model.get_embedding_dimension() != EMBEDDING_DIM:
        raise ValueError("Configured dimension does not match the embedding model")
    return model


def _validate_vectors(vectors, expected: int) -> np.ndarray:
    array = np.asarray(vectors, dtype=np.float32)
    if array.shape != (expected, EMBEDDING_DIM):
        raise ValueError(f"Expected {expected} vectors of dimension {EMBEDDING_DIM}; got {array.shape}")
    if not np.isfinite(array).all() or np.any(np.linalg.norm(array, axis=1) <= 0):
        raise ValueError("Embedding vectors must be finite and nonzero")
    return array


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Identical normalized encoder for corpus/query; never silently truncate."""
    if not texts:
        return []
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("Embedding input must contain non-empty strings")
    model = _embedding_model()
    lengths = model.tokenizer(texts, truncation=False, padding=False, return_length=True)["length"]
    if max(lengths) > EMBEDDING_MAX_TOKENS:
        raise ValueError(f"Input exceeds {EMBEDDING_MAX_TOKENS} tokens; shorten query/chunks before embedding")
    vectors = model.encode(texts, batch_size=EMBEDDING_BATCH_SIZE, normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=False)
    return _validate_vectors(vectors, len(texts)).tolist()


@lru_cache(maxsize=2)
def _client(directory: str):
    import chromadb
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=directory, settings=Settings(anonymized_telemetry=False))


def get_collection():
    """Persist cosine distance and reject same-dimension/different-model reuse."""
    signature = json.dumps(embedding_config(), sort_keys=True)
    collection = _client(str(CHROMA_DIR)).get_or_create_collection(
        name=COLLECTION_NAME, embedding_function=None,
        configuration={"hnsw": {"space": "cosine"}},
        metadata={"embedding_config": signature, "index_state": "empty"})
    if (collection.metadata or {}).get("embedding_config") != signature:
        raise ValueError("Embedding configuration differs from this collection; use a new CHROMA_COLLECTION and reindex")
    if collection.configuration_json["hnsw"]["space"] != "cosine":
        raise ValueError("Dense retrieval requires a cosine collection")
    return collection


def ensure_ready(collection) -> None:
    # Minimal query() doubles used by offline contract tests have no metadata.
    if hasattr(collection, "metadata") and (collection.metadata or {}).get("index_state") != "ready":
        raise RuntimeError("Index is empty or incomplete. Run python -m src.task4_chunking_indexing")


def load_documents() -> list[dict]:
    documents = []
    seen = set()
    manifest_path = STANDARDIZED_DIR.parent / "corpus_manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else None
    recorded = ({entry["standardized_file"]: entry["standardized_sha256"]
                 for entry in manifest["documents"]} if manifest else {})
    loaded_paths = set()
    for path in sorted(STANDARDIZED_DIR.glob("*/*.md")):
        relative = f"data/standardized/{path.parent.name}/{path.name}"
        digest = sha256(path.read_bytes())
        if manifest and recorded.get(relative) != digest:
            raise ValueError(f"Corpus manifest mismatch for {relative}; rerun Task 3 and review the corpus")
        loaded_paths.add(relative)
        text = path.read_text(encoding="utf-8")
        parts = text.split("---\n", 2)
        if len(parts) != 3 or parts[0]:
            raise ValueError(f"Missing YAML provenance in {path}")
        front = yaml.safe_load(parts[1])
        content = re.sub(r"\A# [^\n]+\n+", "", parts[2].strip()).strip()
        identifier = front.get("id")
        if identifier in seen:
            raise ValueError(f"Duplicate document ID: {identifier}")
        seen.add(identifier)
        metadata = {"source": path.name, "title": front.get("title"),
                    "doc_type": front.get("doc_type"), "url": front.get("url"),
                    "document_id": identifier,
                    "standardized_file": relative, "standardized_sha256": digest}
        for key in ("landing_file", "landing_sha256", "date_crawled", "edition", "language"):
            if key in front:
                metadata[key] = str(front[key])
        if metadata["doc_type"] != path.parent.name or metadata["doc_type"] not in {"legal", "news"}:
            raise ValueError(f"Document type/path mismatch: {path}")
        document = {"id": identifier, "content": content, "metadata": metadata}
        validate_document(document)
        documents.append(document)
    if not documents:
        raise ValueError("No standardized documents found; run the corpus phase first")
    if manifest and loaded_paths != set(recorded):
        raise ValueError("Some corpus manifest files are missing; restore the corpus before indexing")
    return documents


def _sections(document: dict):
    content = document["content"]
    markers = list(re.finditer(r"^## PDF page (\d+)\s*$", content, re.MULTILINE))
    if not markers:
        yield None, content
        return
    for i, marker in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(content)
        lines = content[marker.end():end].strip().splitlines()
        # Only running NIST headers and standalone printed page footers.
        if lines and re.match(r"NIST SP 800-63", lines[0]):
            while lines and (re.match(r"NIST SP 800-63|July 2025", lines[0]) or
                             lines[0] in {"Authentication and Authenticator Management", "Federation and Assertions"}):
                lines.pop(0)
        if lines and re.fullmatch(r"\d+|[ivxlcdm]+", lines[-1].strip()):
            lines.pop()
        body = "\n".join(lines).replace("<br>", " ").strip()
        if body:
            yield int(marker.group(1)), body


def chunk_documents(documents: list[dict]) -> list[dict]:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""], length_function=len)
    chunks = []
    if len({d["id"] for d in documents}) != len(documents):
        raise ValueError("Duplicate document IDs")
    for document in documents:
        validate_document(document)
        index = 0
        for page, body in _sections(document):
            for text in splitter.split_text(body):
                metadata = {**document["metadata"], "document_id": document["id"], "chunk_index": index}
                if page is not None:
                    metadata["pdf_page"] = page
                chunk = {"id": f"{document['id']}::chunk-{index}", "content": text, "metadata": metadata}
                validate_document(chunk, require_chunk=True)
                chunks.append(chunk)
                index += 1
    return chunks


def embed_chunks(chunks: list[dict]) -> list[dict]:
    embedded = []
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[start:start + EMBEDDING_BATCH_SIZE]
        for chunk in batch:
            validate_document(chunk, require_chunk=True)
        vectors = embed_texts([chunk["content"] for chunk in batch])
        _validate_vectors(vectors, len(batch))
        embedded.extend({**copy.deepcopy(chunk), "embedding": vector} for chunk, vector in zip(batch, vectors, strict=True))
        print(f"Embedded {len(embedded)}/{len(chunks)} chunks", flush=True)
    return embedded


def chunk_fingerprint(chunks: list[dict]) -> str:
    payload = [{key: chunk[key] for key in ("id", "content", "metadata")} for chunk in chunks]
    return sha256(json.dumps(sorted(payload, key=lambda c: c["id"]), sort_keys=True, ensure_ascii=False).encode())


def stored_chunks(collection, *, embeddings=False) -> list[dict]:
    chunks = []
    for offset in range(0, collection.count(), 500):
        fields = ["documents", "metadatas"] + (["embeddings"] if embeddings else [])
        response = collection.get(limit=500, offset=offset, include=fields)
        for i, identifier in enumerate(response["ids"]):
            metadata = dict(response["metadatas"][i])
            metadata.setdefault("url", None)
            chunk = {"id": identifier, "content": response["documents"][i], "metadata": metadata}
            if embeddings:
                chunk["embedding"] = response["embeddings"][i].tolist()
            validate_document(chunk, require_chunk=True)
            chunks.append(chunk)
    return sorted(chunks, key=lambda chunk: chunk["id"])


def index_to_vectorstore(chunks: list[dict]) -> None:
    """Synchronize the FULL snapshot: upsert, then remove stale chunk IDs."""
    if not chunks:
        raise ValueError("Refusing to replace an index with an empty corpus")
    identifiers = [chunk["id"] for chunk in chunks]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate chunk IDs")
    for chunk in chunks:
        validate_document(chunk, require_chunk=True)
    _validate_vectors([chunk["embedding"] for chunk in chunks], len(chunks))
    collection = get_collection()
    previous_ids = set(collection.get(include=[])["ids"])
    metadata = {**collection.metadata, "index_state": "building"}
    collection.modify(metadata=metadata)
    # Any failure leaves 'building'; searches reject a partial update.
    for start in range(0, len(chunks), UPSERT_BATCH_SIZE):
        batch = chunks[start:start + UPSERT_BATCH_SIZE]
        collection.upsert(ids=[c["id"] for c in batch], documents=[c["content"] for c in batch],
            embeddings=[c["embedding"] for c in batch],
            metadatas=[{k: v for k, v in c["metadata"].items() if v is not None} for c in batch])
    stale = sorted(previous_ids - set(identifiers))
    for start in range(0, len(stale), UPSERT_BATCH_SIZE):
        collection.delete(ids=stale[start:start + UPSERT_BATCH_SIZE])
    if collection.count() != len(chunks):
        raise RuntimeError("Indexed count does not match the chunk snapshot")
    collection.modify(metadata={**metadata, "index_state": "ready", "chunk_count": len(chunks),
                                "chunk_sha256": chunk_fingerprint(chunks),
                                "chunk_version": CHUNK_VERSION, "chunk_size": CHUNK_SIZE,
                                "chunk_overlap": CHUNK_OVERLAP})


def run_pipeline() -> None:
    started = time.perf_counter()
    documents = load_documents()
    chunks = chunk_documents(documents)
    print(f"Loaded {len(documents)} documents; created {len(chunks)} chunks", flush=True)
    collection = get_collection()
    existing = {chunk["id"]: chunk for chunk in stored_chunks(collection, embeddings=True)}
    missing = [chunk for chunk in chunks if chunk["id"] not in existing or
               existing[chunk["id"]]["content"] != chunk["content"]]
    fresh = {chunk["id"]: chunk for chunk in embed_chunks(missing)}
    embedded = [{**chunk, "embedding": (fresh.get(chunk["id"]) or existing[chunk["id"]])["embedding"]}
                for chunk in chunks]
    index_to_vectorstore(embedded)
    report = {"documents": len(documents), "chunks": len(chunks), "collection_count": collection.count(),
        "embedded_this_run": len(missing), "reused_embeddings": len(chunks) - len(missing),
        "seconds": round(time.perf_counter() - started, 3), "embedding": embedding_config(),
        "chunking": {"method": CHUNKING_METHOD, "version": CHUNK_VERSION, "size": CHUNK_SIZE, "overlap": CHUNK_OVERLAP},
        "chunk_sha256": chunk_fingerprint(chunks), "collection": COLLECTION_NAME}
    write_json(ROOT / "data/index/chunks.json", chunks)
    write_json(ROOT / "data/index/index_summary.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    run_pipeline()
