from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config import VaultConfig
from .db import ensure_database


def _date_from_ms(timestamp_ms: int | None) -> str:
    ts = int(timestamp_ms or 0) / 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def _root_node(config: VaultConfig) -> dict[str, Any]:
    conn = ensure_database(config.index_path)
    try:
        rows = conn.execute(
            "SELECT timestamp_ms, COUNT(*) AS count FROM chunks "
            "GROUP BY strftime('%Y-%m-%d', timestamp_ms / 1000, 'unixepoch') "
            "ORDER BY timestamp_ms DESC"
        ).fetchall()
        children = [
            {
                "id": f"date:{_date_from_ms(row['timestamp_ms'])}",
                "type": "date",
                "label": _date_from_ms(row["timestamp_ms"]),
                "chunk_count": int(row["count"] or 0),
            }
            for row in rows
        ]
        return {"id": "root", "type": "root", "label": "Memory Vault", "children": children}
    finally:
        conn.close()


def _date_node(config: VaultConfig, date: str) -> dict[str, Any]:
    conn = ensure_database(config.index_path)
    try:
        rows = conn.execute(
            "SELECT source_kind, source_id, COUNT(*) AS count, MIN(timestamp_ms) AS first_ms, MAX(timestamp_ms) AS last_ms "
            "FROM chunks WHERE strftime('%Y-%m-%d', timestamp_ms / 1000, 'unixepoch') = ? "
            "GROUP BY source_kind, source_id ORDER BY first_ms, source_kind, source_id",
            (date,),
        ).fetchall()
        children = [
            {
                "id": f"source:{row['source_kind']}:{row['source_id']}",
                "type": "source",
                "label": f"{row['source_kind']} / {row['source_id']}",
                "source_kind": row["source_kind"],
                "source_id": row["source_id"],
                "chunk_count": int(row["count"] or 0),
                "time_range_start_ms": row["first_ms"],
                "time_range_end_ms": row["last_ms"],
            }
            for row in rows
        ]
        return {"id": f"date:{date}", "type": "date", "label": date, "children": children}
    finally:
        conn.close()


def _source_node(config: VaultConfig, source_kind: str, source_id: str) -> dict[str, Any]:
    leaves = fetch_leaves(config, f"source:{source_kind}:{source_id}")
    children = [
        {
            "id": f"chunk:{leaf['id']}",
            "type": "chunk",
            "label": leaf["id"],
            "path": leaf["path"],
            "preview": leaf["preview"],
        }
        for leaf in leaves
    ]
    return {
        "id": f"source:{source_kind}:{source_id}",
        "type": "source",
        "label": f"{source_kind} / {source_id}",
        "source_kind": source_kind,
        "source_id": source_id,
        "children": children,
    }


def _chunk_node(config: VaultConfig, chunk_id: str) -> dict[str, Any]:
    conn = ensure_database(config.index_path)
    try:
        row = conn.execute("SELECT id, content_path, preview, source_kind, source_id, timestamp_ms FROM chunks WHERE id=?", (chunk_id,)).fetchone()
        if not row:
            return {"id": f"chunk:{chunk_id}", "type": "chunk", "label": chunk_id, "children": [], "missing": True}
        return {
            "id": f"chunk:{row['id']}",
            "type": "chunk",
            "label": row["id"],
            "chunk_id": row["id"],
            "path": row["content_path"],
            "preview": row["preview"],
            "source_kind": row["source_kind"],
            "source_id": row["source_id"],
            "timestamp_ms": row["timestamp_ms"],
            "children": [],
        }
    finally:
        conn.close()


def drill_down(config: VaultConfig, node_id: str = "root") -> dict[str, Any]:
    node_id = node_id or "root"
    if node_id == "root":
        return _root_node(config)
    if node_id.startswith("date:"):
        return _date_node(config, node_id.split(":", 1)[1])
    if node_id.startswith("source:"):
        parts = node_id.split(":", 2)
        if len(parts) != 3:
            return {"id": node_id, "type": "source", "label": node_id, "children": [], "error": "invalid source node id"}
        return _source_node(config, parts[1], parts[2])
    if node_id.startswith("chunk:"):
        return _chunk_node(config, node_id.split(":", 1)[1])
    return {"id": node_id, "type": "unknown", "label": node_id, "children": [], "error": "unknown node id"}


def fetch_leaves(config: VaultConfig, node_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    conn = ensure_database(config.index_path)
    try:
        if node_id == "root":
            rows = conn.execute(
                "SELECT id, content_path, preview FROM chunks ORDER BY timestamp_ms, seq_in_source LIMIT ?", (limit,)
            ).fetchall()
        elif node_id.startswith("date:"):
            date = node_id.split(":", 1)[1]
            rows = conn.execute(
                "SELECT id, content_path, preview FROM chunks "
                "WHERE strftime('%Y-%m-%d', timestamp_ms / 1000, 'unixepoch') = ? "
                "ORDER BY timestamp_ms, seq_in_source LIMIT ?",
                (date, limit),
            ).fetchall()
        elif node_id.startswith("source:"):
            parts = node_id.split(":", 2)
            if len(parts) != 3:
                return []
            rows = conn.execute(
                "SELECT id, content_path, preview FROM chunks WHERE source_kind=? AND source_id=? "
                "ORDER BY timestamp_ms, seq_in_source LIMIT ?",
                (parts[1], parts[2], limit),
            ).fetchall()
        elif node_id.startswith("chunk:"):
            rows = conn.execute(
                "SELECT id, content_path, preview FROM chunks WHERE id=? LIMIT 1",
                (node_id.split(":", 1)[1],),
            ).fetchall()
        else:
            return []
        return [{"id": row["id"], "path": row["content_path"], "preview": row["preview"]} for row in rows]
    finally:
        conn.close()
