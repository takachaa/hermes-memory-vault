from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .db import ensure_database
from .health import run_health
from .ingest import ingest_file
from .reindex import reindex_vault
from .queue import enqueue_job, list_jobs
from .retrieval import fetch_chunks, recent_chunks, search_chunks
from .summaries import create_daily_summary
from .worker import drain_queue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes-memory-vault")
    sub = parser.add_subparsers(dest="cmd", required=True)
    health = sub.add_parser("health")
    health.add_argument("--deep", action="store_true")
    reindex = sub.add_parser("reindex")
    reindex.add_argument("--no-clear", action="store_true", help="Do not clear existing index first")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("ids", nargs="+")
    fetch.add_argument("--max-chars", type=int, default=4000)
    ingest = sub.add_parser("ingest-file")
    ingest.add_argument("path")
    ingest.add_argument("--source-kind", default="document")
    ingest.add_argument("--source-id", default="")
    ingest.add_argument("--title", default="")
    ingest.add_argument("--tag", action="append", default=[])
    recent = sub.add_parser("recent")
    recent.add_argument("--limit", type=int, default=10)
    recent.add_argument("--source-kind")
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--date")
    qadd = sub.add_parser("queue-add")
    qadd.add_argument("kind", choices=["summary_daily", "reindex"])
    qadd.add_argument("--date")
    qadd.add_argument("--clear", action="store_true")
    qlist = sub.add_parser("queue-list")
    qlist.add_argument("--status")
    qdrain = sub.add_parser("queue-drain")
    qdrain.add_argument("--max-jobs", type=int, default=10)
    args = parser.parse_args(argv)

    cfg = load_config()
    if args.cmd == "health":
        print(json.dumps(run_health(cfg, deep=args.deep), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "reindex":
        print(json.dumps(reindex_vault(cfg, clear=not args.no_clear), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "queue-add":
        payload = {"date": args.date} if args.kind == "summary_daily" else {"clear": bool(args.clear)}
        print(json.dumps({"id": enqueue_job(cfg, args.kind, payload)}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "queue-list":
        print(json.dumps(list_jobs(cfg, status=args.status), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "queue-drain":
        print(json.dumps(drain_queue(cfg, max_jobs=args.max_jobs), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "ingest-file":
        print(json.dumps({"ok": True, "chunk": ingest_file(cfg, args.path, source_kind=args.source_kind, source_id=args.source_id, title=args.title, tags=args.tag)}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "summarize":
        from datetime import datetime, timezone
        date = args.date or datetime.now(timezone.utc).date().isoformat()
        print(json.dumps({"ok": True, "summary": create_daily_summary(cfg, date)}, ensure_ascii=False, indent=2))
        return 0
    conn = ensure_database(cfg.index_path)
    try:
        if args.cmd == "search":
            print(json.dumps(search_chunks(conn, args.query, vault_path=cfg.vault_path, limit=args.limit), ensure_ascii=False, indent=2))
        elif args.cmd == "fetch":
            print(json.dumps(fetch_chunks(conn, args.ids, vault_path=cfg.vault_path, max_chars_per_chunk=args.max_chars), ensure_ascii=False, indent=2))
        elif args.cmd == "recent":
            print(json.dumps(recent_chunks(conn, vault_path=cfg.vault_path, limit=args.limit, source_kind=args.source_kind), ensure_ascii=False, indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
