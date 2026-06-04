from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .config import VaultConfig
from .content_store import body_sha256, parse_markdown
from .db import ensure_database, upsert_chunk
from .ingest import estimate_tokens, preview_text

_REQUIRED = {"id", "source_kind", "source_id", "content_sha256"}


def iter_markdown_files(vault_path: Path):
    for root_name in ("content", "entities", "summaries"):
        root = vault_path / root_name
        if root.exists():
            yield from sorted(root.rglob("*.md"))


def validate_frontmatter(path: Path) -> tuple[dict[str, Any] | None, str | None, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return None, "missing frontmatter fence", text
    raw = text[4:text.find("\n---\n", 4)]
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            return None, f"invalid frontmatter line: {line}", text
    meta, body = parse_markdown(text)
    missing = sorted(k for k in _REQUIRED if not meta.get(k))
    if missing:
        return None, f"missing required frontmatter keys: {', '.join(missing)}", text
    actual = body_sha256(text)
    if meta.get("content_sha256") != actual:
        # This is not fatal for reindex: Markdown body is source of truth.
        meta = dict(meta)
        meta["content_sha256"] = actual
    return meta, None, text


def _row_from_markdown(config: VaultConfig, path: Path, meta: dict[str, Any], text: str) -> dict[str, Any]:
    _, body = parse_markdown(text)
    tags = meta.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    rel = path.relative_to(config.vault_path).as_posix()
    ts = int(meta.get("timestamp_ms") or meta.get("updated_at_ms") or meta.get("created_at_ms") or 0)
    return {
        "id": str(meta["id"]),
        "source_kind": str(meta["source_kind"]),
        "source_id": str(meta["source_id"]),
        "path_scope": str(meta.get("path_scope") or config.path_scope),
        "source_ref": meta.get("source_ref") or "",
        "owner": meta.get("owner") or "user",
        "timestamp_ms": ts,
        "time_range_start_ms": int(meta.get("time_range_start_ms") or ts or 0),
        "time_range_end_ms": int(meta.get("time_range_end_ms") or ts or 0),
        "tags_json": json.dumps(tags, ensure_ascii=False),
        "preview": preview_text(body),
        "token_count": int(meta.get("token_count") or estimate_tokens(body)),
        "seq_in_source": int(meta.get("seq_in_source") or 0),
        "created_at_ms": int(meta.get("created_at_ms") or ts or 0),
        "updated_at_ms": int(meta.get("updated_at_ms") or ts or 0),
        "content_path": rel,
        "content_sha256": str(meta["content_sha256"]),
        "title": body.splitlines()[0].lstrip("# ").strip() if body.splitlines() else "",
        "body": body,
        "tags": " ".join(str(t) for t in tags),
    }


def reindex_vault(config: VaultConfig, *, clear: bool = True) -> dict[str, Any]:
    config.vault_path.mkdir(parents=True, exist_ok=True)
    conn = ensure_database(config.index_path)
    indexed = 0
    errors: list[str] = []
    try:
        if clear:
            conn.execute("DELETE FROM chunks_fts")
            conn.execute("DELETE FROM chunks")
            conn.commit()
        for path in iter_markdown_files(config.vault_path):
            # Entity/summary markdown may not be chunk records; skip non-chunk docs.
            meta, error, text = validate_frontmatter(path)
            if error:
                errors.append(f"{path.relative_to(config.vault_path).as_posix()}: {error}")
                continue
            if not meta or not str(meta.get("id", "")).startswith("chunk_"):
                continue
            upsert_chunk(conn, _row_from_markdown(config, path, meta, text))
            indexed += 1
    finally:
        conn.close()
    return {"ok": not errors, "indexed": indexed, "errors": errors}
