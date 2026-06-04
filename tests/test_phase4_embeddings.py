from pathlib import Path

from hermes_memory_vault.config import VaultConfig
from hermes_memory_vault.db import ensure_database, upsert_chunk
from hermes_memory_vault.embeddings import (
    EmbeddingProvider,
    embedding_signature,
    embed_and_cache_chunk,
    get_cached_embedding,
    semantic_search,
)


class StaticEmbeddingProvider(EmbeddingProvider):
    provider_name = "static"
    model_name = "unit"
    dimensions = 3

    def embed(self, text: str):
        if "alpha" in text.lower():
            return [1.0, 0.0, 0.0]
        if "beta" in text.lower():
            return [0.0, 1.0, 0.0]
        return [0.9, 0.1, 0.0]


def _insert_chunk(cfg: VaultConfig, chunk_id: str, body: str):
    conn = ensure_database(cfg.index_path)
    upsert_chunk(
        conn,
        {
            "id": chunk_id,
            "source_kind": "hermes_turn",
            "source_id": chunk_id,
            "path_scope": "default",
            "source_ref": "test",
            "owner": "user",
            "timestamp_ms": 1,
            "tags_json": "[]",
            "preview": body,
            "token_count": 1,
            "seq_in_source": 1,
            "created_at_ms": 1,
            "updated_at_ms": 1,
            "content_path": f"content/sessions/{chunk_id}.md",
            "content_sha256": "sha",
            "title": chunk_id,
            "body": body,
            "tags": "",
        },
    )
    conn.close()


def test_embedding_signature_tracks_provider_model_and_dimensions():
    provider = StaticEmbeddingProvider()
    assert embedding_signature(provider) == "static:unit:3"


def test_embedding_cache_roundtrip(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    provider = StaticEmbeddingProvider()

    vector = embed_and_cache_chunk(cfg, "chunk_alpha", "alpha text", provider)
    cached = get_cached_embedding(cfg, "chunk_alpha", embedding_signature(provider))

    assert vector == [1.0, 0.0, 0.0]
    assert cached == [1.0, 0.0, 0.0]


def test_semantic_search_uses_cached_vectors(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    provider = StaticEmbeddingProvider()
    _insert_chunk(cfg, "chunk_alpha", "alpha memory")
    _insert_chunk(cfg, "chunk_beta", "beta memory")
    embed_and_cache_chunk(cfg, "chunk_alpha", "alpha memory", provider)
    embed_and_cache_chunk(cfg, "chunk_beta", "beta memory", provider)

    hits = semantic_search(cfg, "alpha question", provider, limit=2)

    assert hits[0]["id"] == "chunk_alpha"
    assert hits[0]["score"] > hits[1]["score"]
