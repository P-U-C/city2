CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
  applied_at TEXT NOT NULL
) STRICT;

CREATE TABLE core_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
) STRICT;

CREATE TABLE writer_state (
  writer_id TEXT PRIMARY KEY,
  writer_sequence INTEGER NOT NULL CHECK(writer_sequence >= 0)
) STRICT;

CREATE TABLE command_dedup (
  idempotency_key TEXT PRIMARY KEY,
  command_sha256 TEXT NOT NULL CHECK(length(command_sha256) = 64),
  result_json TEXT NOT NULL,
  committed_at TEXT NOT NULL
) STRICT;

CREATE TABLE events (
  database_sequence INTEGER PRIMARY KEY CHECK(database_sequence >= 1),
  event_id TEXT NOT NULL UNIQUE,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  aggregate_version INTEGER NOT NULL CHECK(aggregate_version >= 1),
  aggregate_sequence INTEGER NOT NULL CHECK(aggregate_sequence >= 1),
  writer_id TEXT NOT NULL,
  writer_sequence INTEGER NOT NULL CHECK(writer_sequence >= 1),
  actor TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  prior_event_sha256 TEXT NOT NULL CHECK(length(prior_event_sha256) = 64),
  payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
  payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
  event_sha256 TEXT NOT NULL CHECK(length(event_sha256) = 64),
  sensitivity TEXT NOT NULL CHECK(sensitivity IN ('public', 'internal', 'confidential', 'restricted')),
  UNIQUE(aggregate_id, aggregate_version),
  UNIQUE(aggregate_id, aggregate_sequence),
  UNIQUE(writer_id, writer_sequence)
) STRICT;

CREATE INDEX events_aggregate_idx ON events(aggregate_id, aggregate_sequence);
CREATE INDEX events_type_idx ON events(aggregate_type, database_sequence);

CREATE TABLE objective_revisions (
  objective_id TEXT NOT NULL,
  objective_revision INTEGER NOT NULL CHECK(objective_revision >= 1),
  objective_sha256 TEXT NOT NULL CHECK(length(objective_sha256) = 64),
  record_json TEXT NOT NULL CHECK(json_valid(record_json)),
  created_at TEXT NOT NULL,
  PRIMARY KEY(objective_id, objective_revision),
  UNIQUE(objective_id, objective_sha256)
) STRICT;

CREATE TABLE objectives (
  objective_id TEXT PRIMARY KEY,
  aggregate_version INTEGER NOT NULL CHECK(aggregate_version >= 1),
  objective_revision INTEGER NOT NULL CHECK(objective_revision >= 1),
  objective_sha256 TEXT NOT NULL CHECK(length(objective_sha256) = 64),
  status TEXT NOT NULL CHECK(status IN ('proposed', 'active', 'paused', 'completed', 'cancelled', 'superseded')),
  record_json TEXT NOT NULL CHECK(json_valid(record_json)),
  last_event_id TEXT NOT NULL,
  last_event_sha256 TEXT NOT NULL CHECK(length(last_event_sha256) = 64),
  event_high_water INTEGER NOT NULL CHECK(event_high_water >= 1),
  updated_at TEXT NOT NULL,
  quarantined INTEGER NOT NULL DEFAULT 0 CHECK(quarantined IN (0, 1)),
  FOREIGN KEY(objective_id, objective_revision)
    REFERENCES objective_revisions(objective_id, objective_revision)
) STRICT;

CREATE TABLE task_revisions (
  task_id TEXT NOT NULL,
  task_revision INTEGER NOT NULL CHECK(task_revision >= 1),
  task_sha256 TEXT NOT NULL CHECK(length(task_sha256) = 64),
  record_json TEXT NOT NULL CHECK(json_valid(record_json)),
  created_at TEXT NOT NULL,
  PRIMARY KEY(task_id, task_revision),
  UNIQUE(task_id, task_sha256)
) STRICT;

CREATE TABLE tasks (
  task_id TEXT PRIMARY KEY,
  aggregate_version INTEGER NOT NULL CHECK(aggregate_version >= 1),
  task_revision INTEGER NOT NULL CHECK(task_revision >= 1),
  task_sha256 TEXT NOT NULL CHECK(length(task_sha256) = 64),
  objective_id TEXT NOT NULL,
  objective_revision INTEGER NOT NULL CHECK(objective_revision >= 1),
  objective_sha256 TEXT NOT NULL CHECK(length(objective_sha256) = 64),
  state TEXT NOT NULL CHECK(state IN (
    'proposed', 'awaiting_approval', 'ready', 'leased', 'running', 'review',
    'changes_requested', 'accepted', 'rejected', 'cancellation_requested',
    'cancelled', 'expired', 'needs_reconciliation', 'failed_terminal'
  )),
  attempt_count INTEGER NOT NULL CHECK(attempt_count >= 0),
  max_attempts INTEGER NOT NULL CHECK(max_attempts >= 1),
  current_run_id TEXT,
  lease_owner TEXT,
  lease_fencing_token TEXT,
  lease_expires_at TEXT,
  last_event_id TEXT NOT NULL,
  last_event_sha256 TEXT NOT NULL CHECK(length(last_event_sha256) = 64),
  event_high_water INTEGER NOT NULL CHECK(event_high_water >= 1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  quarantined INTEGER NOT NULL DEFAULT 0 CHECK(quarantined IN (0, 1)),
  FOREIGN KEY(task_id, task_revision)
    REFERENCES task_revisions(task_id, task_revision),
  FOREIGN KEY(objective_id, objective_revision)
    REFERENCES objective_revisions(objective_id, objective_revision)
) STRICT;

CREATE INDEX tasks_state_idx ON tasks(state, updated_at);
CREATE INDEX tasks_objective_idx ON tasks(objective_id, state);

CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  task_revision INTEGER NOT NULL CHECK(task_revision >= 1),
  attempt_number INTEGER NOT NULL CHECK(attempt_number >= 1),
  status TEXT NOT NULL CHECK(status IN (
    'leased', 'running', 'review', 'completed', 'failed', 'expired',
    'cancelled', 'completed_after_cancel'
  )),
  task_envelope_json TEXT NOT NULL CHECK(json_valid(task_envelope_json)),
  task_envelope_sha256 TEXT NOT NULL CHECK(length(task_envelope_sha256) = 64),
  result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
  result_sha256 TEXT CHECK(result_sha256 IS NULL OR length(result_sha256) = 64),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES tasks(task_id)
) STRICT;

CREATE TABLE actions (
  action_id TEXT PRIMARY KEY,
  aggregate_version INTEGER NOT NULL CHECK(aggregate_version >= 1),
  task_id TEXT NOT NULL,
  task_revision INTEGER NOT NULL CHECK(task_revision >= 1),
  run_id TEXT NOT NULL,
  operation_idempotency_key TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK(state IN ('prepared', 'dispatched', 'confirmed', 'unknown', 'failed', 'compensated')),
  record_json TEXT NOT NULL CHECK(json_valid(record_json)),
  provider_operation_id TEXT,
  provider_evidence_sha256 TEXT CHECK(provider_evidence_sha256 IS NULL OR length(provider_evidence_sha256) = 64),
  last_event_id TEXT NOT NULL,
  last_event_sha256 TEXT NOT NULL CHECK(length(last_event_sha256) = 64),
  event_high_water INTEGER NOT NULL CHECK(event_high_water >= 1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  quarantined INTEGER NOT NULL DEFAULT 0 CHECK(quarantined IN (0, 1)),
  FOREIGN KEY(task_id) REFERENCES tasks(task_id),
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
) STRICT;

CREATE INDEX actions_task_idx ON actions(task_id, state);

PRAGMA user_version = 1;
