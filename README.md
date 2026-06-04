# Hermes Memory Vault

Markdown-first long-term memory provider plugin for Hermes Agent.

## Design

- Hermes core is not modified.
- The plugin lives at `$HERMES_HOME/plugins/hermes_memory_vault` when installed.
- Markdown files under `$HERMES_HOME/memory-vault` are the source of truth.
- SQLite FTS files under `.memory-vault/` are rebuildable index/cache files.
- OpenHuman is treated as architectural inspiration only; this repository does not copy OpenHuman code.
- Google Drive / Dropbox / iCloud / Obsidian Sync sharing is intentionally out of scope for the MVP.

## MVP features

- `sync_turn()` persists Hermes turns as Markdown.
- SQLite `chunks` metadata table + FTS5 search index.
- `prefetch()` injects bounded relevant snippets.
- Memory tools:
  - `memory_vault_search`
  - `memory_vault_fetch`
  - `memory_vault_health`

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
  provider.py          # MemoryProvider implementation
  config.py            # config loading and path expansion
  db.py                # SQLite connection/migration/upsert
  schema.sql           # chunks + FTS5 schema
  content_store.py     # Markdown frontmatter/body/hash I/O
  ingest.py            # Hermes turn canonicalization and indexing
  retrieval.py         # FTS search and body fetch
  tools.py             # Memory tool schemas and handlers
  health.py            # integrity/freshness checks
  cli.py               # small local utility CLI
```
