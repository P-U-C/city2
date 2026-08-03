CREATE TABLE interface_messages (
  interface TEXT NOT NULL,
  message_id TEXT NOT NULL,
  author_id TEXT NOT NULL,
  channel_id TEXT NOT NULL,
  thread_id TEXT,
  message_sha256 TEXT NOT NULL CHECK(length(message_sha256) = 64),
  task_id TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  PRIMARY KEY(interface, message_id),
  FOREIGN KEY(task_id) REFERENCES tasks(task_id)
) STRICT;

CREATE TABLE runner_dispatches (
  dispatch_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL UNIQUE,
  runner_id TEXT NOT NULL,
  capability_manifest_sha256 TEXT NOT NULL CHECK(length(capability_manifest_sha256) = 64),
  task_envelope_sha256 TEXT NOT NULL CHECK(length(task_envelope_sha256) = 64),
  context_manifest_sha256 TEXT NOT NULL CHECK(length(context_manifest_sha256) = 64),
  state TEXT NOT NULL CHECK(state IN ('prepared', 'running', 'completed', 'cancelled', 'failed')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
) STRICT;

PRAGMA user_version = 3;
