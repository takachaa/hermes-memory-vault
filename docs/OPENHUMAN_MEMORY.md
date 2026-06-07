# OpenHuman-Inspired Memory Direction

Hermes Memory Vault treats OpenHuman as architectural inspiration, not as copied code. The goal is to keep memory local, inspectable, editable in Obsidian, and compressible into navigable knowledge layers.

## Design principles

1. **Markdown is the source of truth**
   - Full memory bodies live as Markdown files.
   - SQLite FTS, embedding caches, queues, and summary indexes are rebuildable.

2. **Raw archive is provenance, not the final memory surface**
   - `content/sessions/` stores Hermes turns as raw leaves.
   - Raw turns are useful for auditability and trace-back.
   - Retrieval should prefer curated and compressed layers before raw session turns.

3. **Curated memory should be human-readable**
   - `notes/` is for human-authored Obsidian notes.
   - `content/notes/` is the indexed canonical form of imported notes.
   - `entities/` holds person/org/project/concept pages.

4. **Memory should compress into trees**
   - `summaries/source/`: source-specific rolling summaries.
   - `summaries/topic/`: hot entity/project/concept summaries.
   - `summaries/global/` and `summaries/daily/`: cross-source digests.

5. **Retrieval should be layered**
   - First search durable memory surfaces: notes, documents, summaries.
   - Use raw session turns only as fallback.
   - The current user request always overrides recalled memory.

## Current implementation status

Implemented now:

- Raw Hermes turn archival under `content/sessions/`.
- Markdown-first content store.
- SQLite FTS index and rebuild.
- Obsidian-friendly scaffold including `notes/`, `entities/`, and `summaries/{source,topic,global,daily}`.
- Prefetch priority for curated notes/documents/summaries before raw session archive.
- Manual note/document ingest via `memory_vault_ingest_file`.
- Entity registry and daily summary primitives.

Still future work:

- Automatic entity/relation extraction from raw turns.
- Admitted/dropped lifecycle scoring.
- Source tree rolling buffers and sealing.
- Topic tree routing by entity hotness.
- Global tree digest generation beyond the current simple daily summary.
- Background worker loop that turns raw archive leaves into summaries/entities automatically.

## Recommended Obsidian usage

- Read raw conversation history in `content/sessions/` only when you need provenance.
- Write durable manual notes in `notes/`.
- Ingest important manual notes with `memory_vault_ingest_file` so Hermes can retrieve them.
- Prefer `entities/` and `summaries/` for long-lived knowledge navigation.

## Retrieval defaults

The provider config supports:

```yaml
memory:
  hermes_memory_vault:
    prefetch_preferred_source_kinds:
      - note
      - document
      - summary_daily
      - summary_source
      - summary_topic
      - summary_global
    prefetch_raw_fallback: true
```

With this default, raw session turns remain available but do not crowd out curated notes and summaries when those exist.
