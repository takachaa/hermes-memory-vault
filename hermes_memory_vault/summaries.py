from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import hashlib

from .config import VaultConfig
from .content_store import write_chunk_markdown
from .db import ensure_database, now_ms
from .ingest import estimate_tokens


def _day_bounds_ms(date: str) -> tuple[int, int]:
    start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def create_daily_summary(config: VaultConfig, date: str) -> dict[str, Any]:
    start_ms, end_ms = _day_bounds_ms(date)
    conn = ensure_database(config.index_path)
    try:
        rows = conn.execute(
            "SELECT id, source_kind, preview, content_path, timestamp_ms FROM chunks "
            "WHERE timestamp_ms >= ? AND timestamp_ms < ? ORDER BY timestamp_ms, seq_in_source",
            (start_ms, end_ms),
        ).fetchall()
    finally:
        conn.close()

    rel = Path("summaries") / "daily" / f"{date}.md"
    summary_id = "summary_daily_" + date.replace("-", "")
    lines = [f"# Daily Memory Summary: {date}", ""]
    if not rows:
        lines.append("No indexed chunks for this day.")
    else:
        lines.append(f"Indexed chunks: {len(rows)}")
        lines.append("")
        lines.append("## Highlights")
        for row in rows:
            preview = row["preview"] or row["id"]
            lines.append(f"- `{row['id']}` {preview}")
        lines.append("")
        lines.append("## Source chunks")
        for row in rows:
            lines.append(f"- {row['content_path']}")
    body = "\n".join(lines) + "\n"
    ts = now_ms()
    meta = {
        "id": summary_id,
        "kind": "daily",
        "date": date,
        "source_kind": "summary_daily",
        "source_id": date,
        "path_scope": config.path_scope,
        "timestamp_ms": start_ms,
        "chunk_count": len(rows),
        "token_count": estimate_tokens(body),
        "created_at_ms": ts,
        "updated_at_ms": ts,
    }
    write_result = write_chunk_markdown(config.vault_path / rel, meta, body)

    conn = ensure_database(config.index_path)
    try:
        conn.execute(
            "INSERT INTO summaries (id, kind, date, path, chunk_count, content_sha256, created_at_ms, updated_at_ms) "
            "VALUES (?, 'daily', ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET path=excluded.path, chunk_count=excluded.chunk_count, "
            "content_sha256=excluded.content_sha256, updated_at_ms=excluded.updated_at_ms",
            (summary_id, date, rel.as_posix(), len(rows), write_result.content_sha256, ts, ts),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": summary_id, "path": rel.as_posix(), "chunk_count": len(rows), "content_sha256": write_result.content_sha256}
