from pathlib import Path

from hermes_memory_vault.config import VaultConfig, from_mapping
from hermes_memory_vault.health import run_health
from hermes_memory_vault.ingest import ingest_file, ingest_turn
from hermes_memory_vault.provider import HermesMemoryVaultProvider


def test_health_scaffolds_openhuman_inspired_layers_and_schema(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")

    result = run_health(cfg, deep=False)

    assert result["ok"] is True
    for rel in [
        "notes",
        "summaries/source",
        "summaries/topic",
        "summaries/global",
        "summaries/daily",
        "entities/person",
        "entities/org",
        "entities/project",
        "entities/concept",
        "raw/sessions",
    ]:
        assert (cfg.vault_path / rel).exists(), rel

    schema = (cfg.vault_path / "SCHEMA.md").read_text(encoding="utf-8")
    assert "raw archive" in schema
    assert "source tree" in schema
    assert "topic tree" in schema
    assert "global tree" in schema


def test_health_refreshes_old_generated_schema_without_overwriting_custom_notes(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    cfg.vault_path.mkdir(parents=True)
    (cfg.vault_path / "SCHEMA.md").write_text(
        "# Hermes Memory Vault Schema\n\nMarkdown files are the source of truth. SQLite files under `.memory-vault/` are rebuildable indexes and caches.\n",
        encoding="utf-8",
    )
    (cfg.vault_path / "index.md").write_text("# Custom operator index\n\nDo not replace me.\n", encoding="utf-8")

    run_health(cfg, deep=False)

    assert "OpenHuman-inspired layers" in (cfg.vault_path / "SCHEMA.md").read_text(encoding="utf-8")
    assert "Custom operator index" in (cfg.vault_path / "index.md").read_text(encoding="utf-8")


def test_config_supports_openhuman_retrieval_defaults(tmp_path: Path):
    cfg = from_mapping(
        {
            "vault_path": str(tmp_path / "vault"),
            "index_path": str(tmp_path / "vault/.memory-vault/index.sqlite"),
            "prefetch_preferred_source_kinds": ["note", "summary_daily"],
            "prefetch_raw_fallback": False,
        }
    )

    assert cfg.prefetch_preferred_source_kinds == ["note", "summary_daily"]
    assert cfg.prefetch_raw_fallback is False


def test_prefetch_prefers_curated_notes_over_raw_session_turns(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    run_health(cfg, deep=False)

    ingest_turn(
        cfg,
        "OpenHuman priority marker appeared in a raw chat",
        "Raw assistant response should not win when a curated note exists.",
        session_id="raw-session",
        seq_in_source=1,
        timestamp_ms=1780531200000,
    )
    note = tmp_path / "openhuman-note.md"
    note.write_text("# OpenHuman priority marker\n\nCurated note should be recalled first.", encoding="utf-8")
    note_result = ingest_file(
        cfg,
        note,
        source_kind="note",
        source_id="openhuman-note",
        timestamp_ms=1780531300000,
    )

    provider = HermesMemoryVaultProvider(cfg)
    provider.initialize("session-a", platform="test")
    context = provider.prefetch("OpenHuman priority marker")

    assert note_result["content_path"] in context
    assert "Raw assistant response should not win" not in context
