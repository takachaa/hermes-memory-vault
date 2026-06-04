CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    path_scope TEXT DEFAULT 'default',
    source_ref TEXT,
    owner TEXT,
    timestamp_ms INTEGER,
    time_range_start_ms INTEGER,
    time_range_end_ms INTEGER,
    tags_json TEXT DEFAULT '[]',
    preview TEXT,
    token_count INTEGER DEFAULT 0,
    seq_in_source INTEGER DEFAULT 0,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    content_path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_source_seq ON chunks(source_kind, source_id, seq_in_source);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_kind, source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_timestamp ON chunks(timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_chunks_path_scope ON chunks(path_scope);
CREATE INDEX IF NOT EXISTS idx_chunks_sha ON chunks(content_sha256);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    id UNINDEXED,
    title,
    preview,
    body,
    tags
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    display_name TEXT NOT NULL,
    aliases_json TEXT DEFAULT '[]',
    path TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entities_kind ON entities(kind);

CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    id UNINDEXED,
    kind,
    display_name,
    aliases,
    body
);

CREATE TABLE IF NOT EXISTS chunk_entities (
    chunk_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    relation TEXT DEFAULT 'mentions',
    confidence REAL DEFAULT 1.0,
    created_at_ms INTEGER NOT NULL,
    PRIMARY KEY (chunk_id, entity_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_chunk_entities_entity ON chunk_entities(entity_id);

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT NOT NULL,
    signature TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector_json TEXT NOT NULL,
    content_sha256 TEXT DEFAULT '',
    created_at_ms INTEGER NOT NULL,
    PRIMARY KEY (chunk_id, signature)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_signature ON embeddings(signature);
