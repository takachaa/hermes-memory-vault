from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json

from .config import VaultConfig
from .db import ensure_database
from .entities import search_entities, upsert_entity
from .embeddings import provider_from_config, semantic_search
from .health import run_health
from .reindex import reindex_vault
from .retrieval import fetch_chunks, search_chunks


def _parse_iso_ms(value: str | None) -> int | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


SEARCH_SCHEMA = {
    "name": "memory_vault_search",
    "description": "Search the local Markdown-backed Hermes Memory Vault using SQLite FTS5.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "limit": {"type": "integer", "description": "Maximum hits, default 5."},
            "source_kind": {"type": "string", "description": "Optional source kind filter, e.g. hermes_turn."},
            "after": {"type": "string", "description": "Optional ISO timestamp lower bound."},
            "before": {"type": "string", "description": "Optional ISO timestamp upper bound."},
        },
        "required": ["query"],
    },
}

FETCH_SCHEMA = {
    "name": "memory_vault_fetch",
    "description": "Fetch full Markdown bodies for Memory Vault chunk IDs.",
    "parameters": {
        "type": "object",
        "properties": {
            "ids": {"type": "array", "items": {"type": "string"}, "description": "Chunk IDs to fetch."},
            "max_chars_per_chunk": {"type": "integer", "description": "Maximum body characters per chunk."},
        },
        "required": ["ids"],
    },
}

HEALTH_SCHEMA = {
    "name": "memory_vault_health",
    "description": "Check Memory Vault database, content paths, and optional SHA integrity.",
    "parameters": {
        "type": "object",
        "properties": {"deep": {"type": "boolean", "description": "Also verify body SHA-256 values."}},
        "required": [],
    },
}

REINDEX_SCHEMA = {
    "name": "memory_vault_reindex",
    "description": "Rebuild the SQLite FTS index from Markdown files in the local Memory Vault.",
    "parameters": {
        "type": "object",
        "properties": {"clear": {"type": "boolean", "description": "Clear existing index before rebuilding; default true."}},
        "required": [],
    },
}

SEARCH_ENTITIES_SCHEMA = {
    "name": "memory_vault_search_entities",
    "description": "Search Markdown-backed Memory Vault entity registry (person, org, project, concept).",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Entity search query."},
            "kind": {"type": "string", "enum": ["person", "org", "project", "concept"], "description": "Optional entity kind filter."},
            "limit": {"type": "integer", "description": "Maximum hits, default 10."},
        },
        "required": ["query"],
    },
}

UPSERT_ENTITY_SCHEMA = {
    "name": "memory_vault_upsert_entity",
    "description": "Create or update a Markdown-backed entity note in the Memory Vault registry.",
    "parameters": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["person", "org", "project", "concept"]},
            "display_name": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
            "body": {"type": "string", "description": "Free-form Markdown note body."},
        },
        "required": ["kind", "display_name"],
    },
}

SEMANTIC_SEARCH_SCHEMA = {
    "name": "memory_vault_semantic_search",
    "description": "Semantic search using the configured optional embedding provider and cached vectors.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "description": "Maximum hits, default 5."},
        },
        "required": ["query"],
    },
}


def schemas() -> list[dict[str, Any]]:
    return [
        SEARCH_SCHEMA,
        FETCH_SCHEMA,
        HEALTH_SCHEMA,
        REINDEX_SCHEMA,
        SEARCH_ENTITIES_SCHEMA,
        UPSERT_ENTITY_SCHEMA,
        SEMANTIC_SEARCH_SCHEMA,
    ]


def handle_tool(config: VaultConfig, tool_name: str, args: dict[str, Any]) -> str:
    try:
        if tool_name == "memory_vault_health":
            return json.dumps(run_health(config, deep=bool(args.get("deep", False))), ensure_ascii=False)
        if tool_name == "memory_vault_reindex":
            return json.dumps(reindex_vault(config, clear=bool(args.get("clear", True))), ensure_ascii=False)
        if tool_name == "memory_vault_search_entities":
            query = str(args.get("query") or "").strip()
            if not query:
                return json.dumps({"hits": [], "error": "query is required"}, ensure_ascii=False)
            return json.dumps({"hits": search_entities(config, query, kind=args.get("kind") or None, limit=int(args.get("limit") or 10))}, ensure_ascii=False)
        if tool_name == "memory_vault_upsert_entity":
            entity = upsert_entity(
                config,
                kind=str(args.get("kind") or "concept"),
                display_name=str(args.get("display_name") or ""),
                aliases=list(args.get("aliases") or []),
                body=str(args.get("body") or ""),
            )
            return json.dumps({"ok": True, "entity": entity}, ensure_ascii=False)
        if tool_name == "memory_vault_semantic_search":
            if not config.embeddings_enabled:
                return json.dumps({"hits": [], "error": "embeddings are disabled"}, ensure_ascii=False)
            provider = provider_from_config(config)
            hits = semantic_search(config, str(args.get("query") or ""), provider, limit=int(args.get("limit") or 5))
            return json.dumps({"hits": hits}, ensure_ascii=False)

        conn = ensure_database(config.index_path)
        try:
            if tool_name == "memory_vault_search":
                query = str(args.get("query") or "").strip()
                if not query:
                    return json.dumps({"hits": [], "error": "query is required"}, ensure_ascii=False)
                hits = search_chunks(
                    conn,
                    query,
                    vault_path=config.vault_path,
                    limit=int(args.get("limit") or 5),
                    source_kind=args.get("source_kind") or None,
                    after_ms=_parse_iso_ms(args.get("after")),
                    before_ms=_parse_iso_ms(args.get("before")),
                )
                return json.dumps({"hits": hits}, ensure_ascii=False)

            if tool_name == "memory_vault_fetch":
                ids = args.get("ids") or []
                if isinstance(ids, str):
                    ids = [ids]
                chunks = fetch_chunks(
                    conn,
                    [str(i) for i in ids],
                    vault_path=config.vault_path,
                    max_chars_per_chunk=int(args.get("max_chars_per_chunk") or 4000),
                )
                return json.dumps({"chunks": chunks}, ensure_ascii=False)
        finally:
            conn.close()

        return json.dumps({"error": f"unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
