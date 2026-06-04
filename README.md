# Hermes Memory Vault

Markdown-first long-term memory provider plugin for Hermes Agent.

## Design

- Hermes core is not modified.
- The plugin lives at `$HERMES_HOME/plugins/hermes_memory_vault` when installed.
- Markdown files under `$HERMES_HOME/memory-vault` are the source of truth.
- SQLite FTS files under `.memory-vault/` are rebuildable index/cache files.
- OpenHuman is treated as architectural inspiration only; this repository does not copy OpenHuman code.
- Google Drive / Dropbox / iCloud / Obsidian Sync sharing is intentionally out of scope for the MVP.

## Implemented features

- `sync_turn()` persists Hermes turns as Markdown.
- SQLite `chunks` metadata table + FTS5 search index.
- `prefetch()` injects bounded relevant snippets.
- Deep health checks and Markdown-to-SQLite reindex.
- Markdown-backed entity registry.
- Optional embedding cache / semantic-search foundation.
- SQLite-backed queue, daily summaries, and `on_session_end()` summary enqueue/direct generation.
- Memory tree drill-down / leaf fetch.
- Memory tools:
  - `memory_vault_search`
  - `memory_vault_fetch`
  - `memory_vault_health`
  - `memory_vault_reindex`
  - `memory_vault_search_entities`
  - `memory_vault_upsert_entity`
  - `memory_vault_semantic_search`
  - `memory_vault_drill_down`
  - `memory_vault_fetch_leaves`
  - `memory_vault_ingest_file`
  - `memory_vault_recent`
  - `memory_vault_summarize`

## Install locally

Hermes currently discovers user-installed memory providers from:

```text
$HERMES_HOME/plugins/<provider_name>/
```

So for the default profile:

```bash
mkdir -p ~/.hermes/plugins
ln -s ~/hermes-memory-vault/hermes_memory_vault ~/.hermes/plugins/hermes_memory_vault
```

Enable:

```bash
hermes config set memory.provider hermes_memory_vault
# restart gateway or start a fresh Hermes session
```

Optional config block:

```yaml
memory:
  memory_enabled: true
  user_profile_enabled: true
  provider: hermes_memory_vault
  hermes_memory_vault:
    vault_path: $HERMES_HOME/memory-vault
    index_path: $HERMES_HOME/memory-vault/.memory-vault/index.sqlite
    auto_ingest_sessions: true
    prefetch_enabled: true
    prefetch_max_chunks: 5
    prefetch_max_chars: 6000
    fts_enabled: true
    embeddings:
      enabled: false
      provider: none
      model: none
    summaries:
      enabled: false
      on_session_end: false  # enqueue/generate daily summary when a Hermes session ends
    queue:
      enabled: false
```

## Rollback / removal

See `docs/ROLLBACK.md`.

Quick rollback:

```bash
hermes config set memory.provider ""
# or
hermes memory off

mv ~/.hermes/plugins/hermes_memory_vault ~/.hermes/plugins/hermes_memory_vault.disabled
mv ~/.hermes/memory-vault ~/.hermes/memory-vault.disabled
```

## Development

```bash
uv run --with pytest python -m pytest tests -q
```

## Repository contents

```text
hermes_memory_vault/
  __init__.py          # plugin register(ctx) entrypoint
  memory_provider.py   # design-brief-compatible provider re-export
  provider.py          # MemoryProvider implementation
  config.py            # config loading and path expansion
  paths.py             # resolved vault/index/cache paths helper
  db.py                # SQLite connection/migration/upsert
  schema.sql           # chunks + FTS5 + entities + embeddings + queue + summaries schema
  content_store.py     # Markdown frontmatter/body/hash I/O
  canonicalize.py      # canonicalization compatibility exports
  chunker.py           # deterministic text chunking helper
  ingest.py            # Hermes turn/file canonicalization and indexing
  retrieval.py         # FTS search, recent listing, and body fetch
  reindex.py           # Markdown source-of-truth index rebuild
  entities.py          # Markdown-backed entity registry
  embeddings.py        # optional embedding providers/cache/search
  queue.py             # SQLite job queue
  summaries.py         # daily Markdown summaries
  worker.py            # queue drain worker
  memory_tree.py       # drill-down/fetch leaves
  tools.py             # Memory tool schemas and handlers
  health.py            # integrity/freshness checks and vault scaffold
  cli.py               # small local utility CLI
```
