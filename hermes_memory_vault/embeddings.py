from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
import json
import math
import os
import urllib.request

from .config import VaultConfig
from .db import ensure_database, now_ms


class EmbeddingProvider(ABC):
    provider_name: str = "none"
    model_name: str = "none"
    dimensions: int = 0

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class NoopEmbeddingProvider(EmbeddingProvider):
    provider_name = "none"
    model_name = "none"
    dimensions = 0

    def embed(self, text: str) -> list[float]:
        raise RuntimeError("embeddings are disabled")


class OllamaEmbeddingProvider(EmbeddingProvider):
    provider_name = "ollama"

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434", dimensions: int = 0):
        self.model_name = model
        self.base_url = base_url.rstrip("/")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        payload = json.dumps({"model": self.model_name, "prompt": text}).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/api/embeddings", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec - user-configured local endpoint
            data = json.loads(resp.read().decode("utf-8"))
        vector = [float(x) for x in data.get("embedding", [])]
        self.dimensions = len(vector)
        return vector


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    provider_name = "openai-compatible"

    def __init__(self, model: str, base_url: str, api_key: str | None = None, dimensions: int = 0):
        self.model_name = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        payload = json.dumps({"model": self.model_name, "input": text}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.base_url + "/embeddings", data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:  # nosec - user-configured endpoint
            data = json.loads(resp.read().decode("utf-8"))
        vector = [float(x) for x in data["data"][0]["embedding"]]
        self.dimensions = len(vector)
        return vector


def provider_from_config(config: VaultConfig) -> EmbeddingProvider:
    if not config.embeddings_enabled or config.embeddings_provider in {"", "none"}:
        return NoopEmbeddingProvider()
    if config.embeddings_provider == "ollama":
        return OllamaEmbeddingProvider(config.embeddings_model, config.embeddings_base_url or "http://127.0.0.1:11434", config.embeddings_dimensions)
    if config.embeddings_provider in {"openai", "openai-compatible"}:
        base = config.embeddings_base_url or "https://api.openai.com/v1"
        return OpenAICompatibleEmbeddingProvider(config.embeddings_model, base, dimensions=config.embeddings_dimensions)
    raise ValueError(f"unsupported embeddings provider: {config.embeddings_provider}")


def embedding_signature(provider: EmbeddingProvider) -> str:
    return f"{provider.provider_name}:{provider.model_name}:{provider.dimensions}"


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    aa = _normalize(a)
    bb = _normalize(b)
    return float(sum(x * y for x, y in zip(aa, bb)))


def embed_and_cache_chunk(config: VaultConfig, chunk_id: str, text: str, provider: EmbeddingProvider, *, content_sha256: str = "") -> list[float]:
    vector = provider.embed(text)
    if not getattr(provider, "dimensions", 0):
        provider.dimensions = len(vector)
    sig = embedding_signature(provider)
    conn = ensure_database(config.index_path)
    try:
        conn.execute(
            "INSERT INTO embeddings (chunk_id, signature, provider, model, dimensions, vector_json, content_sha256, created_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(chunk_id, signature) DO UPDATE SET vector_json=excluded.vector_json, content_sha256=excluded.content_sha256, created_at_ms=excluded.created_at_ms",
            (chunk_id, sig, provider.provider_name, provider.model_name, int(provider.dimensions), json.dumps(vector), content_sha256, now_ms()),
        )
        conn.commit()
    finally:
        conn.close()
    return vector


def get_cached_embedding(config: VaultConfig, chunk_id: str, signature: str) -> list[float] | None:
    conn = ensure_database(config.index_path)
    try:
        row = conn.execute("SELECT vector_json FROM embeddings WHERE chunk_id=? AND signature=?", (chunk_id, signature)).fetchone()
        return [float(x) for x in json.loads(row["vector_json"])] if row else None
    finally:
        conn.close()


def semantic_search(config: VaultConfig, query: str, provider: EmbeddingProvider, *, limit: int = 5) -> list[dict[str, Any]]:
    qvec = provider.embed(query)
    if not getattr(provider, "dimensions", 0):
        provider.dimensions = len(qvec)
    sig = embedding_signature(provider)
    conn = ensure_database(config.index_path)
    try:
        rows = conn.execute(
            "SELECT e.chunk_id, e.vector_json, c.source_kind, c.timestamp_ms, c.content_path, c.preview "
            "FROM embeddings e JOIN chunks c ON c.id=e.chunk_id WHERE e.signature=?",
            (sig,),
        ).fetchall()
        scored = []
        for row in rows:
            score = cosine_similarity(qvec, [float(x) for x in json.loads(row["vector_json"])])
            scored.append(
                {
                    "id": row["chunk_id"],
                    "score": score,
                    "source_kind": row["source_kind"],
                    "timestamp_ms": row["timestamp_ms"],
                    "path": row["content_path"],
                    "preview": row["preview"],
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[: max(1, min(int(limit or 5), 50))]
    finally:
        conn.close()
