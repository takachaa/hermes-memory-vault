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
from .db import ensure_database, max_seq_for_source, now_ms, upsert_chunk


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


def canonicalize_file(path: Path, *, source_kind: str = "document", title: str = "") -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    inferred_title = title.strip()
    if not inferred_title:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                inferred_title = stripped.lstrip("#").strip()
                break
    if not inferred_title:
        inferred_title = path.stem.replace("-", " ").replace("_", " ").strip() or "Imported file"
    body = text if text.endswith("\n") else text + "\n"
    if not body.lstrip().startswith("#"):
        body = f"# {inferred_title}\n\n{body}"
    return inferred_title, body


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


def ingest_file(
    config: VaultConfig,
    path: str | Path,
    *,
    source_kind: str = "document",
    source_id: str = "",
    source_ref: str = "",
    title: str = "",
    tags: list[str] | None = None,
    timestamp_ms: int | None = None,
) -> dict[str, Any]:
    """Import a local text/Markdown file into the Markdown vault and FTS index."""
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(str(source_path))
    timestamp_ms = timestamp_ms or now_ms()
    created = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).astimezone()
    timestamp_iso = created.isoformat(timespec="seconds")
    normalized_kind = (source_kind or "document").strip().lower()
    source_id = source_id or source_path.as_posix()
    title_text, body = canonicalize_file(source_path, source_kind=normalized_kind, title=title)
    conn_for_seq = ensure_database(config.index_path)
    try:
        seq_in_source = 1 + max_seq_for_source(conn_for_seq, normalized_kind, source_id)
    finally:
        conn_for_seq.close()
    stable = hashlib.sha256(f"{normalized_kind}\0{source_id}\0{seq_in_source}\0{body}".encode("utf-8")).hexdigest()[:16]
    chunk_id = f"chunk_{stable}"
    dir_map = {"hermes_session": "sessions", "hermes_turn": "sessions", "chat": "chats", "document": "documents", "note": "notes"}
    directory = dir_map.get(normalized_kind, "documents")
    rel_path = Path("content") / directory / f"{created:%Y}" / f"{created:%m}" / f"{safe_slug(source_path.stem)}-{seq_in_source:04d}.md"
    tag_values = list(tags or [])
    if normalized_kind not in tag_values:
        tag_values.append(normalized_kind)
    meta: dict[str, Any] = {
        "id": chunk_id,
        "source_kind": normalized_kind,
        "source_id": source_id,
        "source_ref": source_ref or source_path.as_posix(),
        "path_scope": config.path_scope,
        "owner": "user",
        "timestamp_ms": timestamp_ms,
        "time_range_start_ms": timestamp_ms,
        "time_range_end_ms": timestamp_ms,
        "tags": tag_values,
        "token_count": estimate_tokens(body),
        "seq_in_source": seq_in_source,
        "created_at": timestamp_iso,
        "updated_at": timestamp_iso,
    }
    write_result = write_chunk_markdown(config.vault_path / rel_path, meta, body)
    conn = ensure_database(config.index_path)
    try:
        upsert_chunk(
            conn,
            {
                "id": chunk_id,
                "source_kind": normalized_kind,
                "source_id": source_id,
                "path_scope": config.path_scope,
                "source_ref": source_ref or source_path.as_posix(),
                "owner": "user",
                "timestamp_ms": timestamp_ms,
                "time_range_start_ms": timestamp_ms,
                "time_range_end_ms": timestamp_ms,
                "tags_json": json.dumps(tag_values, ensure_ascii=False),
                "preview": preview_text(body),
                "token_count": estimate_tokens(body),
                "seq_in_source": seq_in_source,
                "created_at_ms": timestamp_ms,
                "updated_at_ms": timestamp_ms,
                "content_path": rel_path.as_posix(),
                "content_sha256": write_result.content_sha256,
                "title": title_text,
                "body": body,
                "tags": " ".join(tag_values),
            },
        )
    finally:
        conn.close()
    return {
        "id": chunk_id,
        "content_path": rel_path.as_posix(),
        "content_sha256": write_result.content_sha256,
        "source_kind": normalized_kind,
        "source_id": source_id,
        "date": f"{created:%Y-%m-%d}",
    }
