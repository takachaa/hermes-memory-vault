from __future__ import annotations

from pathlib import Path
from typing import Any
import sqlite3
import time

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def ensure_database(index_path: Path) -> sqlite3.Connection:
    conn = connect(index_path)
    migrate(conn)
    return conn


def now_ms() -> int:
    return int(time.time() * 1000)


def upsert_chunk(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    existing = conn.execute(
        "SELECT id, created_at_ms FROM chunks WHERE source_kind=? AND source_id=? AND seq_in_source=?",
        (row["source_kind"], row["source_id"], row.get("seq_in_source", 0)),
    ).fetchone()
    if existing:
        row = dict(row)
        row["id"] = existing["id"]
        row["created_at_ms"] = existing["created_at_ms"]

    fields = [
        "id", "source_kind", "source_id", "path_scope", "source_ref", "owner",
        "timestamp_ms", "time_range_start_ms", "time_range_end_ms", "tags_json",
        "preview", "token_count", "seq_in_source", "created_at_ms", "updated_at_ms",
        "content_path", "content_sha256",
    ]
    values = [row.get(f) for f in fields]
    updates = ", ".join(f"{f}=excluded.{f}" for f in fields if f != "id")
    conn.execute(
        f"INSERT INTO chunks ({', '.join(fields)}) VALUES ({', '.join(['?'] * len(fields))}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        values,
    )
    conn.execute("DELETE FROM chunks_fts WHERE id=?", (row["id"],))
    conn.execute(
        "INSERT INTO chunks_fts (id, title, preview, body, tags) VALUES (?, ?, ?, ?, ?)",
        (row["id"], row.get("title", ""), row.get("preview", ""), row.get("body", ""), row.get("tags", "")),
    )
    conn.commit()
    return str(row["id"])


def max_seq_for_source(conn: sqlite3.Connection, source_kind: str, source_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(seq_in_source), 0) AS seq FROM chunks WHERE source_kind=? AND source_id=?",
        (source_kind, source_id),
    ).fetchone()
    return int(row["seq"] if row else 0)
