from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import re

from .config import VaultConfig
from .content_store import write_chunk_markdown
from .db import ensure_database, now_ms, upsert_chunk


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def safe_slug(text: str, max_len: int = 80) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", text or "session").strip("-._")
    return (slug or "session")[:max_len]


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def preview_text(text: str, max_chars: int = 240) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    return one_line[:max_chars]


def canonicalize_turn(user_content: str, assistant_content: str, *, session_id: str, timestamp_iso: str) -> tuple[str, str]:
    title = "Hermes turn"
    body = (
        f"# {title}\n\n"
        f"- Session: `{session_id}`\n"
        f"- Timestamp: {timestamp_iso}\n\n"
        "## User\n\n"
        f"{user_content.strip()}\n\n"
        "## Assistant\n\n"
        f"{assistant_content.strip()}\n"
    )
    return title, body


@dataclass(slots=True)
class IngestResult:
    id: str
    content_path: str
    content_sha256: str


def ingest_turn(
    config: VaultConfig,
    user_content: str,
    assistant_content: str,
    *,
    session_id: str = "",
    seq_in_source: int = 0,
    source_ref: str = "",
    timestamp_ms: int | None = None,
) -> IngestResult:
    timestamp_ms = timestamp_ms or now_ms()
    session_id = session_id or f"session-{timestamp_ms}"
    created = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone()
    timestamp_iso = created.isoformat(timespec="seconds")
    if seq_in_source <= 0:
        conn_for_seq = ensure_database(config.index_path)
        try:
            seq_in_source = 1 + int(conn_for_seq.execute(
                "SELECT COALESCE(MAX(seq_in_source), 0) FROM chunks WHERE source_kind=? AND source_id=?",
                ("hermes_turn", session_id),
            ).fetchone()[0])
        finally:
            conn_for_seq.close()

    stable = hashlib.sha256(f"hermes_turn\0{session_id}\0{seq_in_source}".encode("utf-8")).hexdigest()[:16]
    chunk_id = f"chunk_{stable}"
    title, body = canonicalize_turn(user_content, assistant_content, session_id=session_id, timestamp_iso=timestamp_iso)
    rel_path = Path("content") / "sessions" / f"{created:%Y}" / f"{created:%m}" / f"{safe_slug(session_id)}-{seq_in_source:04d}.md"
    abs_path = config.vault_path / rel_path
    tags = ["conversation", "hermes", "memory"]
    meta: dict[str, Any] = {
        "id": chunk_id,
        "source_kind": "hermes_turn",
        "source_id": session_id,
        "source_ref": source_ref,
        "path_scope": config.path_scope,
        "owner": "user",
        "timestamp_ms": timestamp_ms,
        "time_range_start_ms": timestamp_ms,
        "time_range_end_ms": timestamp_ms,
        "tags": tags,
        "token_count": estimate_tokens(body),
        "seq_in_source": seq_in_source,
        "created_at": timestamp_iso,
        "updated_at": timestamp_iso,
    }
    write_result = write_chunk_markdown(abs_path, meta, body)

    conn = ensure_database(config.index_path)
    try:
        upsert_chunk(
            conn,
            {
                "id": chunk_id,
                "source_kind": "hermes_turn",
                "source_id": session_id,
                "path_scope": config.path_scope,
                "source_ref": source_ref,
                "owner": "user",
                "timestamp_ms": timestamp_ms,
                "time_range_start_ms": timestamp_ms,
                "time_range_end_ms": timestamp_ms,
                "tags_json": json.dumps(tags, ensure_ascii=False),
                "preview": preview_text(user_content),
                "token_count": estimate_tokens(body),
                "seq_in_source": seq_in_source,
                "created_at_ms": timestamp_ms,
                "updated_at_ms": timestamp_ms,
                "content_path": rel_path.as_posix(),
                "content_sha256": write_result.content_sha256,
                "title": title,
                "body": body,
                "tags": " ".join(tags),
            },
        )
    finally:
        conn.close()
    return IngestResult(id=chunk_id, content_path=rel_path.as_posix(), content_sha256=write_result.content_sha256)
