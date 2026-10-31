-- Core records for processes, runs and managed files (Step 2).
-- IDs are UUID text. Timestamps are UTC ISO-8601 text (YYYY-MM-DDTHH:MM:SSZ).

CREATE TABLE process (
    id             TEXT PRIMARY KEY,
    slug           TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    purpose        TEXT NOT NULL DEFAULT '',
    owner          TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE process_version (
    id             TEXT PRIMARY KEY,
    process_id     TEXT NOT NULL REFERENCES process (id),
    version        TEXT NOT NULL,
    manifest_json  TEXT NOT NULL DEFAULT '{}',
    approved       INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1)),
    approved_by    TEXT,
    approved_at    TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (process_id, version)
);
CREATE INDEX idx_process_version_process ON process_version (process_id);

CREATE TABLE stored_file (
    id             TEXT PRIMARY KEY,
    rel_path       TEXT NOT NULL UNIQUE,
    original_name  TEXT NOT NULL,
    size_bytes     INTEGER NOT NULL CHECK (size_bytes >= 0),
    sha256         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_stored_file_sha256 ON stored_file (sha256);

CREATE TABLE run (
    id                 TEXT PRIMARY KEY,
    process_version_id TEXT NOT NULL REFERENCES process_version (id),
    status             TEXT NOT NULL CHECK (status IN (
                           'running', 'completed', 'completed_with_warnings',
                           'partially_completed', 'failed', 'cancelled')),
    started_at         TEXT NOT NULL,
    finished_at        TEXT,
    summary            TEXT NOT NULL DEFAULT '',
    warnings_json      TEXT NOT NULL DEFAULT '[]',
    error              TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    schema_version     INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_run_version ON run (process_version_id);
CREATE INDEX idx_run_started ON run (started_at);

CREATE TABLE run_input (
    id             TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES run (id) ON DELETE CASCADE,
    role           TEXT NOT NULL,
    stored_file_id TEXT NOT NULL REFERENCES stored_file (id),
    original_path  TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL
);
CREATE INDEX idx_run_input_run ON run_input (run_id);

CREATE TABLE output_artifact (
    id             TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES run (id) ON DELETE CASCADE,
    role           TEXT NOT NULL,
    stored_file_id TEXT NOT NULL REFERENCES stored_file (id),
    created_at     TEXT NOT NULL
);
CREATE INDEX idx_output_artifact_run ON output_artifact (run_id);