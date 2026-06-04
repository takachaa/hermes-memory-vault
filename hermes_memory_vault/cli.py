from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .db import ensure_database
from .health import run_health
from .retrieval import fetch_chunks, search_chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes-memory-vault")
    sub = parser.add_subparsers(dest="cmd", required=True)
    health = sub.add_parser("health")
    health.add_argument("--deep", action="store_true")
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("ids", nargs="+")
    fetch.add_argument("--max-chars", type=int, default=4000)
    args = parser.parse_args(argv)

    cfg = load_config()
    if args.cmd == "health":
        print(json.dumps(run_health(cfg, deep=args.deep), ensure_ascii=False, indent=2))
        return 0
    conn = ensure_database(cfg.index_path)
    try:
        if args.cmd == "search":
            print(json.dumps(search_chunks(conn, args.query, vault_path=cfg.vault_path, limit=args.limit), ensure_ascii=False, indent=2))
        elif args.cmd == "fetch":
            print(json.dumps(fetch_chunks(conn, args.ids, vault_path=cfg.vault_path, max_chars_per_chunk=args.max_chars), ensure_ascii=False, indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
