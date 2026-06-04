import json
from pathlib import Path

from hermes_memory_vault.config import VaultConfig
from hermes_memory_vault.db import ensure_database
from hermes_memory_vault.entities import upsert_entity, search_entities, link_chunk_entity, list_chunk_entities
from hermes_memory_vault.tools import handle_tool, schemas


def test_upsert_entity_writes_markdown_and_sqlite_registry(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")

    entity = upsert_entity(
        cfg,
        kind="person",
        display_name="Example Person",
        aliases=["Example P"],
        body="Important free-form notes.",
    )

    path = cfg.vault_path / entity["path"]
    assert path.exists()
    assert entity["id"] == "person:example-person"
    assert "Important free-form notes" in path.read_text(encoding="utf-8")

    hits = search_entities(cfg, "Example", kind="person")
    assert hits[0]["id"] == "person:example-person"
    assert hits[0]["display_name"] == "Example Person"


def test_chunk_entity_links_are_indexed(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    upsert_entity(cfg, kind="project", display_name="Memory Vault")

    link_chunk_entity(cfg, "chunk_abc", "project:memory-vault", relation="mentions", confidence=0.8)
    links = list_chunk_entities(cfg, "chunk_abc")

    assert links == [{"entity_id": "project:memory-vault", "relation": "mentions", "confidence": 0.8}]


def test_memory_vault_search_entities_tool(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    upsert_entity(cfg, kind="org", display_name="Tiny Humans AI", aliases=["OpenHuman"])

    names = {schema["name"] for schema in schemas()}
    result = json.loads(handle_tool(cfg, "memory_vault_search_entities", {"query": "OpenHuman", "kind": "org"}))

    assert "memory_vault_search_entities" in names
    assert result["hits"][0]["id"] == "org:tiny-humans-ai"
