from pathlib import Path

from hermes_memory_vault.db import connect, migrate, upsert_chunk
from hermes_memory_vault.retrieval import fetch_chunks, search_chunks


def test_migration_creates_chunks_and_fts(tmp_path: Path):
    db_path = tmp_path / "index.sqlite"
    conn = connect(db_path)
    migrate(conn)

    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual')")}

    assert "chunks" in tables
    assert "chunks_fts" in tables


def test_upsert_chunk_is_searchable_and_fetch_reads_markdown_body(tmp_path: Path):
    vault = tmp_path / "vault"
    db_path = vault / ".memory-vault" / "index.sqlite"
    content_path = vault / "content" / "sessions" / "turn.md"
    content_path.parent.mkdir(parents=True)
    content_path.write_text("---\nid: chunk_1\n---\n# Turn\n\nUser likes reversible plugins.\n", encoding="utf-8")

    conn = connect(db_path)
    migrate(conn)
    upsert_chunk(
        conn,
        {
            "id": "chunk_1",
            "source_kind": "hermes_turn",
            "source_id": "session-a",
            "path_scope": "default",
            "source_ref": "telegram:dm",
            "owner": "user",
            "timestamp_ms": 1780546301000,
            "tags_json": '["conversation"]',
            "preview": "User likes reversible plugins.",
            "token_count": 5,
            "seq_in_source": 1,
            "created_at_ms": 1780546301000,
            "updated_at_ms": 1780546301000,
            "content_path": "content/sessions/turn.md",
            "content_sha256": "sha",
            "title": "Hermes turn",
            "body": "User likes reversible plugins.",
            "tags": "conversation",
        },
    )

    hits = search_chunks(conn, "reversible plugins", vault_path=vault, limit=5)
    fetched = fetch_chunks(conn, ["chunk_1"], vault_path=vault, max_chars_per_chunk=1000)

    assert [h["id"] for h in hits] == ["chunk_1"]
    assert hits[0]["path"] == "content/sessions/turn.md"
    assert fetched[0]["body"] == "# Turn\n\nUser likes reversible plugins.\n"
