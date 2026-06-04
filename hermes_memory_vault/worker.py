from __future__ import annotations

from typing import Any

from .config import VaultConfig
from .queue import claim_next_job, complete_job, fail_job
from .reindex import reindex_vault
from .summaries import create_daily_summary


def process_job(config: VaultConfig, job: dict[str, Any]) -> dict[str, Any]:
    kind = job["kind"]
    payload = job.get("payload") or {}
    if kind == "summary_daily":
        date = payload.get("date")
        if not date:
            raise ValueError("summary_daily job requires payload.date")
        return create_daily_summary(config, str(date))
    if kind == "reindex":
        return reindex_vault(config, clear=bool(payload.get("clear", True)))
    raise ValueError(f"unknown job kind: {kind}")


def drain_queue(config: VaultConfig, *, max_jobs: int = 10) -> dict[str, Any]:
    processed = 0
    failed = 0
    results: list[dict[str, Any]] = []
    for _ in range(max(1, max_jobs)):
        job = claim_next_job(config)
        if not job:
            break
        try:
            result = process_job(config, job)
            complete_job(config, job["id"], result=result)
            results.append({"id": job["id"], "kind": job["kind"], "ok": True, "result": result})
            processed += 1
        except Exception as exc:
            fail_job(config, job["id"], str(exc))
            results.append({"id": job["id"], "kind": job["kind"], "ok": False, "error": str(exc)})
            failed += 1
    return {"processed": processed, "failed": failed, "results": results}
