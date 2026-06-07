from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import sqlite3

from .config import VaultConfig
from .content_store import body_sha256, parse_markdown
from .db import ensure_database
from .reindex import iter_markdown_files, validate_frontmatter


def _scaffold_vault(vault_path: Path) -> None:
    vault_path.mkdir(parents=True, exist_ok=True)
    for rel in [
        "content/sessions",
        "content/chats",
        "content/documents",
        "content/notes",
        "notes",
        "raw/sessions",
        "raw/imports",
        "raw/assets",
        "entities/person",
        "entities/org",
        "entities/project",
        "entities/concept",
        "summaries/daily",
        "summaries/weekly",
        "summaries/monthly",
        "summaries/source",
        "summaries/topic",
        "summaries/global",
        "summaries/projects",
        ".memory-vault/migrations",
        ".memory-vault/locks",
    ]:
        (vault_path / rel).mkdir(parents=True, exist_ok=True)
    scaffolds = {
        "SCHEMA.md": """# Hermes Memory Vault Schema

Markdown files are the source of truth. SQLite files under `.memory-vault/` are rebuildable indexes and caches.

## OpenHuman-inspired layers

- `content/sessions/`: raw archive of Hermes conversation turns. This is provenance, not the preferred long-term memory surface.
- `content/documents/`, `content/chats/`, `content/notes/`: canonicalized source chunks from imported documents, chats, and note files.
- `notes/`: human-authored Obsidian notes. Use this for manually curated, durable knowledge that should be ingested into `content/notes/`.
- `entities/{person,org,project,concept}/`: durable entity pages for people, organizations, projects, and concepts.
- `summaries/source/`: source tree summaries that compress one source stream.
- `summaries/topic/`: topic tree summaries for hot entities/projects/concepts.
- `summaries/global/` and `summaries/daily/`: global tree and daily digest outputs.
- `raw/`: non-canonical raw inputs/assets retained for audit or reprocessing.

Raw archive files should remain traceable, but retrieval should prefer curated notes, documents, entities, and summaries before falling back to raw session turns.
""",
        "index.md": """# Hermes Memory Vault

This vault is managed by the Hermes Memory Vault provider.

Start in `notes/`, `entities/`, and `summaries/` for human-readable memory. `content/sessions/` is the raw archive/provenance layer.
""",
        "log.md": "# Memory Vault Log\n\nOperational notes and maintenance events may be appended here.\n",
        "notes/README.md": "# Curated Notes\n\nHuman-authored Obsidian notes live here. Import important notes with `memory_vault_ingest_file` so they become indexed memory chunks.\n",
    }
    for rel, text in scaffolds.items():
        path = vault_path / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            continue
        if rel == "SCHEMA.md":
            legacy_schema = "# Hermes Memory Vault Schema\n\nMarkdown files are the source of truth. SQLite files under `.memory-vault/` are rebuildable indexes and caches.\n"
            try:
                if path.read_text(encoding="utf-8") == legacy_schema:
                    path.write_text(text, encoding="utf-8")
            except OSError:
                pass


def run_health(config: VaultConfig, *, deep: bool = False) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    warnings: list[str] = []

    _scaffold_vault(config.vault_path)
    checks.append({"name": "vault_dirs", "status": "ok"})

    try:
        conn = ensure_database(config.index_path)
        conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        checks.append({"name": "db_open", "status": "ok"})
    except Exception as exc:
        checks.append({"name": "db_open", "status": "error", "detail": str(exc)})
        return {"ok": False, "checks": checks, "warnings": warnings}

    try:
        rows = conn.execute("SELECT id, content_path, content_sha256 FROM chunks").fetchall()
        indexed_paths = {row["content_path"] for row in rows}
        missing = 0
        sha_mismatch = 0
        invalid_frontmatter = 0
        orphan_files = 0
        for row in rows:
            path = config.vault_path / row["content_path"]
            if not path.exists():
                missing += 1
                if deep:
                    warnings.append(f"missing content_path for {row['id']}: {row['content_path']}")
                continue
            if deep:
                actual = body_sha256(path.read_text(encoding="utf-8"))
                if actual != row["content_sha256"]:
                    sha_mismatch += 1
                    warnings.append(f"sha256 mismatch for {row['id']}: {row['content_path']}")
        checks.append({"name": "content_paths", "status": "ok" if missing == 0 else "warn"})
        if deep:
            for md in iter_markdown_files(config.vault_path):
                rel = md.relative_to(config.vault_path).as_posix()
                meta, error, _text = validate_frontmatter(md)
                if error:
                    invalid_frontmatter += 1
                    warnings.append(f"invalid frontmatter in {rel}: {error}")
                    continue
                if meta and str(meta.get("id", "")).startswith("chunk_") and rel not in indexed_paths:
                    orphan_files += 1
                    warnings.append(f"orphan markdown not indexed: {rel}")
            checks.append({"name": "sha256", "status": "ok" if sha_mismatch == 0 else "warn"})
            checks.append({"name": "frontmatter", "status": "ok" if invalid_frontmatter == 0 else "warn"})
            checks.append({"name": "orphan_markdown", "status": "ok" if orphan_files == 0 else "warn"})
    finally:
        conn.close()

    ok = all(c["status"] == "ok" for c in checks)
    return {"ok": ok, "checks": checks, "warnings": warnings}
