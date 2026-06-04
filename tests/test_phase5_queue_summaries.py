from pathlib import Path

from hermes_memory_vault.config import VaultConfig
from hermes_memory_vault.db import ensure_database, upsert_chunk
from hermes_memory_vault.queue import enqueue_job, list_jobs, claim_next_job, complete_job
from hermes_memory_vault.summaries import create_daily_summary
from hermes_memory_vault.worker import drain_queue


def _insert_chunk(cfg: VaultConfig, chunk_id: str, body: str, ts: int):
    conn = ensure_database(cfg.index_path)
    upsert_chunk(
        conn,
        {
            "id": chunk_id,
            "source_kind": "hermes_turn",
            "source_id": chunk_id,
            "path_scope": "default",
            "source_ref": "test",
            "owner": "user",
            "timestamp_ms": ts,
            "tags_json": "[]",
            "preview": body,
            "token_count": 1,
            "seq_in_source": 1,
            "created_at_ms": ts,
            "updated_at_ms": ts,
            "content_path": f"content/sessions/{chunk_id}.md",
            "content_sha256": "sha",
            "title": chunk_id,
            "body": body,
            "tags": "",
        },
    )
    conn.close()


def test_queue_lifecycle(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")

    job_id = enqueue_job(cfg, "summary_daily", {"date": "2026-06-04"})
    claimed = claim_next_job(cfg)
    complete_job(cfg, job_id, result={"ok": True})
    jobs = list_jobs(cfg)

    assert claimed["id"] == job_id
    assert claimed["kind"] == "summary_daily"
    assert jobs[0]["status"] == "done"


def test_create_daily_summary_writes_markdown_and_index_row(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    # 2026-06-04T00:00:00Z
    _insert_chunk(cfg, "chunk_a", "User discussed queue based summaries.", 1780531200000)
    _insert_chunk(cfg, "chunk_b", "Assistant proposed daily digest.", 1780534800000)

    result = create_daily_summary(cfg, "2026-06-04")
    path = cfg.vault_path / result["path"]

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "queue based summaries" in text
    assert result["chunk_count"] == 2


def test_worker_drains_summary_job(tmp_path: Path):
    cfg = VaultConfig(vault_path=tmp_path / "vault", index_path=tmp_path / "vault/.memory-vault/index.sqlite")
    _insert_chunk(cfg, "chunk_a", "Worker should summarize this.", 1780531200000)
    enqueue_job(cfg, "summary_daily", {"date": "2026-06-04"})

    result = drain_queue(cfg, max_jobs=5)

    assert result["processed"] == 1
    assert (cfg.vault_path / "summaries/daily/2026-06-04.md").exists()
