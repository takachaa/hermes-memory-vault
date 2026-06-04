import json
from pathlib import Path

from hermes_memory_vault.config import VaultConfig
from hermes_memory_vault.ingest import ingest_turn
from hermes_memory_vault.provider import HermesMemoryVaultProvider


def test_ingest_turn_writes_markdown_and_indexes_once_per_sequence(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")

    first = ingest_turn(cfg, "hello", "world", session_id="session-a", seq_in_source=1, source_ref="cli")
    second = ingest_turn(cfg, "hello", "world", session_id="session-a", seq_in_source=1, source_ref="cli")

    assert first.id == second.id
    assert (cfg.vault_path / first.content_path).exists()

    import sqlite3
    conn = sqlite3.connect(cfg.index_path)
    count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    assert count == 1


def test_provider_sync_prefetch_tools_and_health(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    provider = HermesMemoryVaultProvider(config=cfg)

    assert provider.name == "hermes_memory_vault"
    assert provider.is_available() is True

    provider.initialize("session-a", hermes_home=str(tmp_path), platform="test")
    provider.sync_turn("I prefer reversible Hermes plugins", "Noted", session_id="session-a")

    prefetch = provider.prefetch("reversible plugins", session_id="session-a")
    assert "Memory Vault Context" in prefetch
    assert "reversible Hermes plugins" in prefetch

    tool_names = {schema["name"] for schema in provider.get_tool_schemas()}
    assert {"memory_vault_search", "memory_vault_fetch", "memory_vault_health"} <= tool_names

    search_result = json.loads(provider.handle_tool_call("memory_vault_search", {"query": "reversible plugins", "limit": 2}))
    assert search_result["hits"][0]["id"]

    fetch_result = json.loads(provider.handle_tool_call("memory_vault_fetch", {"ids": [search_result["hits"][0]["id"]]}))
    assert "I prefer reversible Hermes plugins" in fetch_result["chunks"][0]["body"]

    health = json.loads(provider.handle_tool_call("memory_vault_health", {"deep": True}))
    assert health["ok"] is True
