from pathlib import Path
import json

from hermes_memory_vault.config import VaultConfig, from_mapping
from hermes_memory_vault.health import run_health
from hermes_memory_vault.provider import HermesMemoryVaultProvider
from hermes_memory_vault.queue import list_jobs
from hermes_memory_vault.tools import handle_tool, schemas


def test_config_parses_queue_and_summary_blocks(tmp_path: Path):
    cfg = from_mapping(
        {
            "vault_path": str(tmp_path / "vault"),
            "index_path": str(tmp_path / "vault/.memory-vault/index.sqlite"),
            "queue": {"enabled": True},
            "summaries": {"enabled": True, "on_session_end": True},
        }
    )

    assert cfg.queue_enabled is True
    assert cfg.summaries_enabled is True
    assert cfg.summaries_on_session_end is True


def test_health_scaffolds_full_design_brief_vault_layout(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")

    result = run_health(cfg, deep=False)

    assert result["ok"] is True
    for rel in [
        "SCHEMA.md",
        "index.md",
        "log.md",
        "content/sessions",
        "content/chats",
        "content/documents",
        "content/notes",
        "raw/sessions",
        "raw/imports",
        "raw/assets",
        "entities/person",
        "entities/org",
        "entities/project",
        "entities/concept",
        "summaries/daily",
        "summaries/weekly",
        "summaries/monthly",
        "summaries/projects",
        ".memory-vault/migrations",
        ".memory-vault/locks",
    ]:
        assert (cfg.vault_path / rel).exists(), rel


def test_missing_design_brief_tools_are_exposed_and_work(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    source = tmp_path / "brief-note.md"
    source.write_text("# Brief note\n\nMemory Vault ingest file marker.", encoding="utf-8")

    schema_names = {schema["name"] for schema in schemas()}
    assert {"memory_vault_ingest_file", "memory_vault_recent", "memory_vault_summarize"} <= schema_names

    ingested = json.loads(handle_tool(cfg, "memory_vault_ingest_file", {"path": str(source), "source_kind": "document", "tags": ["brief"]}))
    assert ingested["ok"] is True
    chunk_id = ingested["chunk"]["id"]

    recent = json.loads(handle_tool(cfg, "memory_vault_recent", {"limit": 5}))
    assert any(hit["id"] == chunk_id for hit in recent["hits"])

    summary = json.loads(handle_tool(cfg, "memory_vault_summarize", {"date": ingested["chunk"]["date"]}))
    assert summary["ok"] is True
    assert (cfg.vault_path / summary["summary"]["path"]).exists()


def test_provider_on_session_end_enqueues_daily_summary_when_enabled(tmp_path: Path):
    cfg = VaultConfig(
        vault_path=tmp_path / "vault",
        index_path=tmp_path / "vault/.memory-vault/index.sqlite",
        queue_enabled=True,
        summaries_enabled=True,
        summaries_on_session_end=True,
    )
    provider = HermesMemoryVaultProvider(cfg)
    provider.initialize("session-a", platform="test")

    provider.on_session_end([{"role": "user", "content": "bye", "timestamp_ms": 1780531200000}])

    jobs = list_jobs(cfg)
    assert len(jobs) == 1
    assert jobs[0]["kind"] == "summary_daily"
    assert jobs[0]["payload"]["date"] == "2026-06-04"


def test_design_brief_compatibility_modules_are_importable():
    import hermes_memory_vault.memory_provider as memory_provider
    import hermes_memory_vault.paths as paths
    import hermes_memory_vault.canonicalize as canonicalize
    import hermes_memory_vault.chunker as chunker

    assert memory_provider.HermesMemoryVaultProvider.__name__ == "HermesMemoryVaultProvider"
    assert callable(paths.resolve_paths)
    assert callable(canonicalize.canonicalize_turn)
    assert callable(chunker.chunk_text)
