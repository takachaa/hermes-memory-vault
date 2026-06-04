from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

from .config import VaultConfig
from .content_store import compose_markdown, parse_markdown, atomic_write_text
from .db import ensure_database, now_ms
from .retrieval import _fts_query

_ALLOWED_KINDS = {"person", "org", "project", "concept"}


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.lower()).strip("-")
    return slug or "entity"


def entity_id(kind: str, display_name: str) -> str:
    kind = normalize_kind(kind)
    return f"{kind}:{slugify(display_name)}"


def normalize_kind(kind: str) -> str:
    kind = (kind or "concept").strip().lower()
    return kind if kind in _ALLOWED_KINDS else "concept"


def _entity_path(kind: str, display_name: str) -> Path:
    return Path("entities") / normalize_kind(kind) / f"{slugify(display_name)}.md"


def upsert_entity(
    config: VaultConfig,
    *,
    kind: str,
    display_name: str,
    aliases: list[str] | None = None,
    body: str = "",
) -> dict[str, Any]:
    kind = normalize_kind(kind)
    display_name = display_name.strip()
    if not display_name:
        raise ValueError("display_name is required")
    aliases = aliases or []
    eid = entity_id(kind, display_name)
    rel = _entity_path(kind, display_name)
    ts = now_ms()
    iso = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    markdown_body = body if body.endswith("\n") or not body else body + "\n"
    meta = {
        "id": eid,
        "kind": kind,
        "display_name": display_name,
        "aliases": aliases,
        "created_at": iso,
        "updated_at": iso,
    }
    abs_path = config.vault_path / rel
    atomic_write_text(abs_path, compose_markdown(meta, markdown_body))

    conn = ensure_database(config.index_path)
    try:
        existing = conn.execute("SELECT created_at_ms FROM entities WHERE id=?", (eid,)).fetchone()
        created_at_ms = existing["created_at_ms"] if existing else ts
        conn.execute(
            "INSERT INTO entities (id, kind, display_name, aliases_json, path, created_at_ms, updated_at_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, display_name=excluded.display_name, "
            "aliases_json=excluded.aliases_json, path=excluded.path, updated_at_ms=excluded.updated_at_ms",
            (eid, kind, display_name, json.dumps(aliases, ensure_ascii=False), rel.as_posix(), created_at_ms, ts),
        )
        conn.execute("DELETE FROM entities_fts WHERE id=?", (eid,))
        conn.execute(
            "INSERT INTO entities_fts (id, kind, display_name, aliases, body) VALUES (?, ?, ?, ?, ?)",
            (eid, kind, display_name, " ".join(aliases), markdown_body),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": eid, "kind": kind, "display_name": display_name, "aliases": aliases, "path": rel.as_posix()}


def search_entities(config: VaultConfig, query: str, *, kind: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    conn = ensure_database(config.index_path)
    try:
        where = ["entities_fts MATCH ?"]
        params: list[Any] = [_fts_query(query)]
        if kind:
            where.append("e.kind = ?")
            params.append(normalize_kind(kind))
        params.append(max(1, min(int(limit or 10), 50)))
        rows = conn.execute(
            f"SELECT e.*, bm25(entities_fts) AS score FROM entities_fts "
            f"JOIN entities e ON e.id = entities_fts.id WHERE {' AND '.join(where)} "
            f"ORDER BY score ASC, e.updated_at_ms DESC LIMIT ?",
            params,
        ).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "display_name": row["display_name"],
                "aliases": json.loads(row["aliases_json"] or "[]"),
                "path": row["path"],
                "score": float(row["score"] or 0.0),
            }
            for row in rows
        ]
    finally:
        conn.close()


def link_chunk_entity(config: VaultConfig, chunk_id: str, entity_id: str, *, relation: str = "mentions", confidence: float = 1.0) -> None:
    conn = ensure_database(config.index_path)
    try:
        conn.execute(
            "INSERT INTO chunk_entities (chunk_id, entity_id, relation, confidence, created_at_ms) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(chunk_id, entity_id, relation) DO UPDATE SET confidence=excluded.confidence",
            (chunk_id, entity_id, relation or "mentions", float(confidence), now_ms()),
        )
        conn.commit()
    finally:
        conn.close()


def list_chunk_entities(config: VaultConfig, chunk_id: str) -> list[dict[str, Any]]:
    conn = ensure_database(config.index_path)
    try:
        rows = conn.execute(
            "SELECT entity_id, relation, confidence FROM chunk_entities WHERE chunk_id=? ORDER BY entity_id, relation",
            (chunk_id,),
        ).fetchall()
        return [
            {"entity_id": row["entity_id"], "relation": row["relation"], "confidence": float(row["confidence"])}
            for row in rows
        ]
    finally:
        conn.close()
