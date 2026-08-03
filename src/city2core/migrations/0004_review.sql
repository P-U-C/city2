CREATE TABLE agent_manifests (
  agent_id TEXT NOT NULL,
  manifest_version INTEGER NOT NULL CHECK(manifest_version >= 1),
  manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256) = 64),
  manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
  registered_at TEXT NOT NULL,
  PRIMARY KEY(agent_id, manifest_version),
  UNIQUE(agent_id, manifest_sha256)
) STRICT;

CREATE TABLE task_reviews (
  review_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  maker_agent_id TEXT NOT NULL,
  reviewer_agent_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN ('accepted','rejected','changes_requested')),
  deterministic_checks_sha256 TEXT NOT NULL CHECK(length(deterministic_checks_sha256) = 64),
  findings_json TEXT NOT NULL CHECK(json_valid(findings_json)),
  independence_json TEXT NOT NULL CHECK(json_valid(independence_json)),
  reviewed_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES tasks(task_id),
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
) STRICT;

PRAGMA user_version = 4;
