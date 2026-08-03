CREATE TABLE memory_records (
  memory_id TEXT PRIMARY KEY,
  aggregate_version INTEGER NOT NULL CHECK(aggregate_version >= 1),
  scope TEXT NOT NULL,
  memory_type TEXT NOT NULL CHECK(memory_type IN (
    'fact', 'decision', 'procedure', 'feedback', 'outcome',
    'hypothesis', 'reference', 'preference'
  )),
  review_state TEXT NOT NULL CHECK(review_state IN (
    'candidate', 'accepted', 'rejected', 'stale', 'superseded', 'quarantined'
  )),
  candidate_sha256 TEXT NOT NULL CHECK(length(candidate_sha256) = 64),
  record_sha256 TEXT NOT NULL CHECK(length(record_sha256) = 64),
  statement TEXT NOT NULL,
  labels_text TEXT NOT NULL,
  source_text TEXT NOT NULL,
  record_json TEXT NOT NULL CHECK(json_valid(record_json)),
  created_by TEXT NOT NULL,
  reviewed_by TEXT,
  accepted_at TEXT,
  stale_reason TEXT,
  revalidate_at TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_until TEXT,
  sensitivity TEXT NOT NULL CHECK(sensitivity IN ('public', 'internal', 'confidential', 'restricted')),
  last_event_id TEXT NOT NULL,
  last_event_sha256 TEXT NOT NULL CHECK(length(last_event_sha256) = 64),
  event_high_water INTEGER NOT NULL CHECK(event_high_water >= 1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  quarantined INTEGER NOT NULL DEFAULT 0 CHECK(quarantined IN (0, 1)),
  UNIQUE(scope, candidate_sha256)
) STRICT;

CREATE INDEX memory_state_scope_idx
  ON memory_records(review_state, scope, revalidate_at, memory_id);
CREATE INDEX memory_type_idx
  ON memory_records(memory_type, review_state, memory_id);

CREATE TABLE memory_reviews (
  review_id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN ('accepted', 'rejected', 'quarantined')),
  reviewer TEXT NOT NULL,
  reviewed_at TEXT NOT NULL,
  source_check_sha256 TEXT NOT NULL CHECK(length(source_check_sha256) = 64),
  independence_json TEXT NOT NULL CHECK(json_valid(independence_json)),
  FOREIGN KEY(memory_id) REFERENCES memory_records(memory_id)
) STRICT;

CREATE TABLE memory_conflicts (
  conflict_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  fact_class TEXT NOT NULL,
  memory_ids_json TEXT NOT NULL CHECK(json_valid(memory_ids_json)),
  state TEXT NOT NULL CHECK(state IN ('open', 'resolved')),
  created_at TEXT NOT NULL,
  resolved_at TEXT
) STRICT;

CREATE VIRTUAL TABLE memory_fts USING fts5(
  memory_id UNINDEXED,
  statement,
  labels,
  source_metadata,
  tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE retrieval_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
) STRICT;

CREATE TABLE context_packs (
  context_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256) = 64),
  manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
  content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
  content_json TEXT NOT NULL CHECK(json_valid(content_json)),
  event_high_water INTEGER NOT NULL CHECK(event_high_water >= 0),
  created_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES tasks(task_id),
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
) STRICT;

CREATE INDEX context_task_idx ON context_packs(task_id, created_at, context_id);

INSERT INTO retrieval_meta(key, value) VALUES
  ('policy_version', 'memory-fts-v1'),
  ('tokenizer', 'unicode61-remove-diacritics-2'),
  ('ranking', 'term-frequency-v1'),
  ('score_precision', '6'),
  ('excerpt_policy', 'unicode-codepoint-char4-v1');

PRAGMA user_version = 2;
