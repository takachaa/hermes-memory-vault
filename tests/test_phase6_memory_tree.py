from pathlib import Path

from hermes_memory_vault.config import VaultConfig
from hermes_memory_vault.db import ensure_database, upsert_chunk
from hermes_memory_vault.memory_tree import drill_down, fetch_leaves
from hermes_memory_vault.tools import handle_tool, schemas
import json


def _insert_chunk(cfg: VaultConfig, chunk_id: str, source_id: str, preview: str, ts: int, seq: int = 1):
    conn = ensure_database(cfg.index_path)
    upsert_chunk(
        conn,
        {
            "id": chunk_id,
            "source_kind": "hermes_turn",
            "source_id": source_id,
            "path_scope": "default",
            "source_ref": "test",
            "owner": "user",
            "timestamp_ms": ts,
            "tags_json": "[]",
            "preview": preview,
            "token_count": 1,
            "seq_in_source": seq,
            "created_at_ms": ts,
            "updated_at_ms": ts,
            "content_path": f"content/sessions/{chunk_id}.md",
            "content_sha256": "sha",
            "title": chunk_id,
            "body": preview,
            "tags": "",
        },
    )
    conn.close()


def test_drill_down_root_date_source_chunk_tree(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    _insert_chunk(cfg, "chunk_a", "session-a", "Alpha preview", 1780531200000, seq=1)
    _insert_chunk(cfg, "chunk_b", "session-a", "Beta preview", 1780534800000, seq=2)

    root = drill_down(cfg, "root")
    date_node = drill_down(cfg, root["children"][0]["id"])
    source_node = drill_down(cfg, date_node["children"][0]["id"])

    assert root["children"][0]["id"] == "date:2026-06-04"
    assert date_node["children"][0]["id"] == "source:hermes_turn:session-a"
    assert [child["id"] for child in source_node["children"]] == ["chunk:chunk_a", "chunk:chunk_b"]


def test_fetch_leaves_from_source_node(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    _insert_chunk(cfg, "chunk_a", "session-a", "Alpha preview", 1780531200000)

    leaves = fetch_leaves(cfg, "source:hermes_turn:session-a")

    assert leaves == [{"id": "chunk_a", "path": "content/sessions/chunk_a.md", "preview": "Alpha preview"}]


def test_memory_vault_drill_down_tool(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    _insert_chunk(cfg, "chunk_a", "session-a", "Alpha preview", 1780531200000)

    names = {schema["name"] for schema in schemas()}
    result = json.loads(handle_tool(cfg, "memory_vault_drill_down", {"node_id": "root"}))

    assert "memory_vault_drill_down" in names
    assert result["node"]["children"][0]["id"] == "date:2026-06-04"
