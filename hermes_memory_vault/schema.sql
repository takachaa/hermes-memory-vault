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
