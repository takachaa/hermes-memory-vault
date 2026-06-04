from __future__ import annotations

from typing import Any
import hashlib
import json

from .config import VaultConfig
from .db import ensure_database, now_ms


def enqueue_job(config: VaultConfig, kind: str, payload: dict[str, Any] | None = None, *, job_id: str | None = None) -> str:
    payload = payload or {}
    ts = now_ms()
    if job_id is None:
        raw = f"{kind}\0{json.dumps(payload, sort_keys=True, ensure_ascii=False)}\0{ts}"
        job_id = "job_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    conn = ensure_database(config.index_path)
    try:
        conn.execute(
            "INSERT INTO jobs (id, kind, status, payload_json, result_json, attempts, error, created_at_ms, updated_at_ms) "
            "VALUES (?, ?, 'pending', ?, '{}', 0, '', ?, ?)",
            (job_id, kind, json.dumps(payload, ensure_ascii=False), ts, ts),
        )
        conn.commit()
    finally:
        conn.close()
    return job_id


def claim_next_job(config: VaultConfig) -> dict[str, Any] | None:
    conn = ensure_database(config.index_path)
    try:
        row = conn.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY created_at_ms LIMIT 1").fetchone()
        if not row:
            return None
        ts = now_ms()
        conn.execute("UPDATE jobs SET status='running', attempts=attempts+1, updated_at_ms=? WHERE id=?", (ts, row["id"]))
        conn.commit()
        return _job_dict(row, status="running", attempts=int(row["attempts"] or 0) + 1)
    finally:
        conn.close()


def complete_job(config: VaultConfig, job_id: str, *, result: dict[str, Any] | None = None) -> None:
    _finish_job(config, job_id, status="done", result=result or {}, error="")


def fail_job(config: VaultConfig, job_id: str, error: str, *, result: dict[str, Any] | None = None) -> None:
    _finish_job(config, job_id, status="failed", result=result or {}, error=error)


def _finish_job(config: VaultConfig, job_id: str, *, status: str, result: dict[str, Any], error: str) -> None:
    conn = ensure_database(config.index_path)
    try:
        conn.execute(
            "UPDATE jobs SET status=?, result_json=?, error=?, updated_at_ms=? WHERE id=?",
            (status, json.dumps(result, ensure_ascii=False), error, now_ms(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_jobs(config: VaultConfig, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    conn = ensure_database(config.index_path)
    try:
        if status:
            rows = conn.execute("SELECT * FROM jobs WHERE status=? ORDER BY created_at_ms DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at_ms DESC LIMIT ?", (limit,)).fetchall()
        return [_job_dict(row) for row in rows]
    finally:
        conn.close()


def _job_dict(row, **overrides) -> dict[str, Any]:
    data = {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"] or "{}"),
        "result": json.loads(row["result_json"] or "{}"),
        "attempts": int(row["attempts"] or 0),
        "error": row["error"] or "",
    }
    data.update(overrides)
    return data
