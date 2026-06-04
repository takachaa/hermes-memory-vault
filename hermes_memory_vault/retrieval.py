from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
import re
import sqlite3

from .content_store import read_body


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w\u3040-\u30ff\u3400-\u9fff]+", query, flags=re.UNICODE)
    if not tokens:
        return '""'
    return " AND ".join(tokens[:12])


def search_chunks(
    conn: sqlite3.Connection,
    query: str,
    *,
    vault_path: Path,
    limit: int = 5,
    source_kind: str | None = None,
    after_ms: int | None = None,
    before_ms: int | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 5), 50))
    where = ["chunks_fts MATCH ?"]
    params: list[Any] = [_fts_query(query)]
    if source_kind:
        where.append("c.source_kind = ?")
        params.append(source_kind)
    if after_ms is not None:
        where.append("c.timestamp_ms >= ?")
        params.append(after_ms)
    if before_ms is not None:
        where.append("c.timestamp_ms <= ?")
        params.append(before_ms)
    params.append(limit)
    sql = f"""
        SELECT c.*, bm25(chunks_fts) AS score
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.id
        WHERE {' AND '.join(where)}
        ORDER BY score ASC, c.timestamp_ms DESC
        LIMIT ?
    """
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    hits: list[dict[str, Any]] = []
    for row in rows:
        path = row["content_path"]
        hits.append(
            {
                "id": row["id"],
                "score": float(row["score"] or 0.0),
                "source_kind": row["source_kind"],
                "timestamp_ms": row["timestamp_ms"],
                "path": path,
                "preview": row["preview"] or "",
                "content_sha256": row["content_sha256"],
            }
        )
    return hits


def fetch_chunks(
    conn: sqlite3.Connection,
    ids: Iterable[str],
    *,
    vault_path: Path,
    max_chars_per_chunk: int = 4000,
) -> list[dict[str, Any]]:
    max_chars_per_chunk = max(100, min(int(max_chars_per_chunk or 4000), 50000))
    result: list[dict[str, Any]] = []
    for chunk_id in ids:
        row = conn.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone()
        if not row:
            continue
        rel = row["content_path"]
        path = vault_path / rel
        try:
            body = read_body(path)
        except Exception as exc:
            body = f"[missing or unreadable content: {exc}]"
        truncated = len(body) > max_chars_per_chunk
        result.append(
            {
                "id": row["id"],
                "path": rel,
                "source_kind": row["source_kind"],
                "timestamp_ms": row["timestamp_ms"],
                "body": body[:max_chars_per_chunk],
                "truncated": truncated,
            }
        )
    return result
