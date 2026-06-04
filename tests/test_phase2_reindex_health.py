from pathlib import Path
import sqlite3

from hermes_memory_vault.config import VaultConfig
from hermes_memory_vault.content_store import compose_markdown, body_sha256
from hermes_memory_vault.db import ensure_database
from hermes_memory_vault.health import run_health
from hermes_memory_vault.reindex import reindex_vault
from hermes_memory_vault.tools import handle_tool, schemas
import json


def _write_chunk(path: Path, chunk_id: str, body: str, **meta):
    data = {
        "id": chunk_id,
        "source_kind": "hermes_turn",
        "source_id": meta.get("source_id", "session-a"),
        "source_ref": "test",
        "path_scope": "default",
        "owner": "user",
        "timestamp_ms": meta.get("timestamp_ms", 1780546301000),
        "tags": ["conversation", "hermes"],
        "token_count": 10,
        "seq_in_source": meta.get("seq_in_source", 1),
        "created_at": "2026-06-04T13:11:41+09:00",
        "updated_at": "2026-06-04T13:11:41+09:00",
        "content_sha256": body_sha256(body),
    }
    data.update(meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(compose_markdown(data, body), encoding="utf-8")


def test_reindex_rebuilds_sqlite_from_markdown_source_of_truth(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    _write_chunk(cfg.vault_path / "content/sessions/2026/06/a.md", "chunk_a", "# A\n\nReindexable markdown memory.\n")

    result = reindex_vault(cfg)
    conn = sqlite3.connect(cfg.index_path)
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    hit = conn.execute("SELECT id FROM chunks_fts WHERE chunks_fts MATCH 'Reindexable'").fetchone()[0]

    assert result["indexed"] == 1
    assert result["errors"] == []
    assert count == 1
    assert hit == "chunk_a"


def test_deep_health_reports_orphan_bad_frontmatter_and_sha_mismatch(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    good = cfg.vault_path / "content/sessions/good.md"
    _write_chunk(good, "chunk_good", "# Good\n\nHealthy body.\n")
    reindex_vault(cfg)

    # Orphan markdown file: exists in content/ but not indexed.
    _write_chunk(cfg.vault_path / "content/sessions/orphan.md", "chunk_orphan", "# Orphan\n\nNot in db.\n")
    # Bad frontmatter file.
    bad = cfg.vault_path / "content/sessions/bad.md"
    bad.write_text("---\nid chunk_bad\n---\n# Bad\n", encoding="utf-8")
    # SHA mismatch for indexed good file.
    text = good.read_text(encoding="utf-8").replace("Healthy body", "Edited body")
    good.write_text(text, encoding="utf-8")

    health = run_health(cfg, deep=True)

    assert health["ok"] is False
    joined = "\n".join(health["warnings"])
    assert "orphan markdown" in joined
    assert "invalid frontmatter" in joined
    assert "sha256 mismatch" in joined


def test_memory_vault_reindex_tool_is_available_and_runs(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    _write_chunk(cfg.vault_path / "content/sessions/a.md", "chunk_a", "# A\n\nTool reindex memory.\n")

    names = {schema["name"] for schema in schemas()}
    result = json.loads(handle_tool(cfg, "memory_vault_reindex", {"clear": True}))

    assert "memory_vault_reindex" in names
    assert result["ok"] is True
    assert result["indexed"] == 1
