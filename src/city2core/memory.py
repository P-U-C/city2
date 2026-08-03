"""Evidence-backed memory lifecycle, retrieval and context assembly for M2."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import re
from typing import Any
from urllib.parse import urlsplit
import uuid

from .core import CoreError
from .model import (
    canonical_json,
    digest_profile,
    new_id,
    normalize_text,
    parse_time,
    sha256_bytes,
    sha256_json,
    utc_now,
)
from .schema import ValidationError, validate_named
from .store import IntegrityError, Store, WriteTransaction


SENSITIVITY = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
TYPE_PRIORITY = {
    "decision": 10,
    "preference": 20,
    "feedback": 30,
    "procedure": 40,
    "fact": 50,
    "reference": 60,
    "outcome": 70,
    "hypothesis": 80,
}
SECTION_ORDER = (
    "constitution",
    "task_envelope",
    "role_authority",
    "project_decisions",
    "procedures",
    "knowledge",
    "task_working",
)
CRITICAL_FACT_CLASSES = {
    "credential_state",
    "production_state",
    "security_control",
    "service_health",
}
SECRET_CONTENT = re.compile(
    r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:api[_-]?key|access[_-]?token|password|private[_-]?key|mnemonic|recovery[_-]?phrase|seed[_-]?phrase)\s*[:=])"
)
SECRET_KEY = re.compile(
    r"(?i)(^|[._-])(api[_-]?key|access[_-]?token|password|private[_-]?key|recovery[_-]?phrase|secret|seed|mnemonic)([._-]|$)"
)
INDEPENDENCE_DIMENSIONS = {
    "different_model",
    "different_provider",
    "no_maker_private_memory",
    "no_shared_write_credential",
    "separate_identity",
    "separate_session",
}
WORD = re.compile(r"[^\W_]+", re.UNICODE)


def token_count(value: str) -> int:
    return (len(value) + 3) // 4


def _reject_secret_metadata(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY.search(key):
                raise CoreError(f"secret-shaped memory metadata denied at {path}.{key}")
            _reject_secret_metadata(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secret_metadata(item, f"{path}[{index}]")


def _source_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for source in record["evidence_refs"]:
        parts.extend(
            str(source.get(key, ""))
            for key in ("authoritative_owner", "uri", "path", "source_revision")
        )
    return normalize_text(" ".join(parts))


def _candidate_profile(record: dict[str, Any]) -> dict[str, Any]:
    excluded = {"aggregate_version", "created_at", "memory_id", "review_state"}
    return {key: value for key, value in record.items() if key not in excluded}


def _max_observed(record: dict[str, Any]) -> str:
    return max(
        (str(source["observed_at"]) for source in record["evidence_refs"]),
        default=record["created_at"],
    )


@dataclass(frozen=True)
class RetrievalResult:
    normalized_query: str
    candidate_memory_ids: list[str]
    ranked_candidates: list[dict[str, Any]]
    records: list[dict[str, Any]]
    excluded: list[dict[str, str]]
    filters: list[str]


class MemoryService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def _validate(self, record: dict[str, Any]) -> None:
        try:
            validate_named(record, "memory.schema.json", self.store.schemas)
        except ValidationError as error:
            raise CoreError(f"memory.schema.json: {error}") from error
        if record["type"] != "hypothesis" and not record["evidence_refs"]:
            raise CoreError("non-hypothesis memory requires evidence")
        for source in record["evidence_refs"]:
            if source["relationship"] == "derived_from" and not {
                "derivation_method",
                "derivation_version",
            }.issubset(source):
                raise CoreError("derived evidence requires method and version")
        if SECRET_CONTENT.search(record["statement"]):
            raise CoreError("secret-shaped content is prohibited from memory")
        _reject_secret_metadata(record)
        for source in record["evidence_refs"]:
            parsed = urlsplit(source["uri"])
            if parsed.username is not None or parsed.password is not None:
                raise CoreError("evidence URI must not contain user information")
        if parse_time(record["revalidate_at"]) < parse_time(record["valid_from"]):
            raise CoreError("memory revalidation cannot precede validity")
        if record["fact_class"] in CRITICAL_FACT_CLASSES:
            baseline = max(
                [parse_time(record["valid_from"])]
                + [
                    parse_time(source["revocation_checked_at"])
                    for source in record["evidence_refs"]
                ]
            )
            delta = parse_time(record["revalidate_at"]) - baseline
            if delta.total_seconds() > 86_400:
                raise CoreError("critical memory revalidation SLO exceeds 24 hours")

    def create_candidate(
        self,
        fields: dict[str, Any],
        *,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        required = {
            "scope",
            "type",
            "statement",
            "evidence_refs",
            "asserted_by",
            "owner",
            "valid_from",
            "fact_class",
            "revalidation_policy",
            "revalidate_at",
            "confidence",
            "sensitivity",
            "labels",
        }
        missing = sorted(required - set(fields))
        if missing:
            raise CoreError(f"memory candidate missing fields: {missing}")
        command = {
            "command": "create_memory_candidate",
            "fields": fields,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            now = utc_now()
            record = {
                "schema_version": "city2.memory/v1",
                "memory_id": new_id("memory"),
                "aggregate_version": 1,
                "scope": fields["scope"],
                "type": fields["type"],
                "statement": fields["statement"],
                "evidence_refs": fields["evidence_refs"],
                "asserted_by": fields["asserted_by"],
                "owner": fields["owner"],
                "created_by": actor,
                "created_at": fields.get("created_at", now),
                "valid_from": fields["valid_from"],
                "fact_class": fields["fact_class"],
                "revalidation_policy": fields["revalidation_policy"],
                "revalidate_at": fields["revalidate_at"],
                "confidence": fields["confidence"],
                "sensitivity": fields["sensitivity"],
                "review_state": "candidate",
                "supersedes": fields.get("supersedes", []),
                "labels": fields["labels"],
            }
            if "valid_until" in fields:
                record["valid_until"] = fields["valid_until"]
            self._validate(record)
            candidate_sha = sha256_json(_candidate_profile(record))
            existing = self.store.conn.execute(
                """SELECT record_json FROM memory_records
                   WHERE scope = ? AND candidate_sha256 = ?""",
                (record["scope"], candidate_sha),
            ).fetchone()
            if existing is not None:
                return json.loads(existing["record_json"])
            marker = tx.append_event(
                aggregate_type="memory",
                aggregate_id=record["memory_id"],
                event_type="memory.created",
                aggregate_version=1,
                actor=actor,
                payload={
                    "candidate_sha256": candidate_sha,
                    "record_sha256": sha256_json(record),
                    "scope": record["scope"],
                    "type": record["type"],
                },
                sensitivity=record["sensitivity"],
            )
            self._insert_projection(record, candidate_sha, marker, now)
            tx.projection_updated()
            return record

        return self.store.command(idempotency_key, command, operation)[0]

    def review_candidate(
        self,
        memory_id: str,
        decision: str,
        *,
        expected_version: int,
        reviewer: str,
        source_checks: list[dict[str, str]],
        independence: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        if decision not in {"accepted", "rejected", "quarantined"}:
            raise CoreError(f"invalid memory review decision: {decision}")
        if set(independence) - INDEPENDENCE_DIMENSIONS or any(
            not isinstance(value, bool) for value in independence.values()
        ):
            raise CoreError("memory review independence dimensions are invalid")
        command = {
            "command": "review_memory",
            "memory_id": memory_id,
            "decision": decision,
            "expected_version": expected_version,
            "reviewer": reviewer,
            "source_checks": source_checks,
            "independence": independence,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version(
                "memory_records", "memory_id", memory_id, expected_version
            )
            row = self._row(memory_id)
            if row["review_state"] != "candidate":
                raise CoreError("only candidate memory may be reviewed")
            record = json.loads(row["record_json"])
            if (
                record["created_by"].startswith("agent:")
                and record["created_by"] == reviewer
            ):
                raise CoreError("an agent cannot approve its own memory candidate")
            if (
                record["scope"] == "company"
                and decision == "accepted"
                and reviewer != "human:chad"
            ):
                raise CoreError("company memory acceptance requires human:chad")
            if decision == "accepted":
                self._verify_source_checks(record, source_checks)
                if record["type"] == "feedback" and (
                    not record["asserted_by"].startswith("human:")
                    or not any(
                        source["relationship"] == "asserted_by"
                        for source in record["evidence_refs"]
                    )
                ):
                    raise CoreError("feedback requires an attributable human source")
                conflict = self._find_conflict(record)
                if conflict is not None:
                    decision_state = "quarantined"
                    conflict_id = "cnf_" + str(uuid.uuid4())
                    self.store.conn.execute(
                        """INSERT INTO memory_conflicts
                           (conflict_id, scope, fact_class, memory_ids_json, state, created_at)
                           VALUES (?, ?, ?, ?, 'open', ?)""",
                        (
                            conflict_id,
                            record["scope"],
                            record["fact_class"],
                            canonical_json(sorted([memory_id, conflict["memory_id"]])),
                            utc_now(),
                        ),
                    )
                else:
                    decision_state = "accepted"
            else:
                decision_state = decision
            next_record = {
                **record,
                "aggregate_version": expected_version + 1,
                "review_state": decision_state,
            }
            self._validate(next_record)
            now = utc_now()
            marker = tx.append_event(
                aggregate_type="memory",
                aggregate_id=memory_id,
                event_type=f"memory.{decision_state}",
                aggregate_version=expected_version + 1,
                actor=reviewer,
                payload={
                    "record_sha256": sha256_json(next_record),
                    "review_state": decision_state,
                    "source_check_sha256": sha256_json(source_checks),
                },
                sensitivity=record["sensitivity"],
            )
            self._update_projection(
                next_record,
                marker,
                now,
                reviewed_by=reviewer,
                accepted_at=now if decision_state == "accepted" else None,
            )
            review_id = new_id("review")
            self.store.conn.execute(
                """INSERT INTO memory_reviews
                   (review_id, memory_id, decision, reviewer, reviewed_at,
                    source_check_sha256, independence_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    review_id,
                    memory_id,
                    decision_state,
                    reviewer,
                    now,
                    sha256_json(source_checks),
                    canonical_json(independence),
                ),
            )
            if decision_state == "accepted":
                self._index_record(next_record)
                self._supersede_in_tx(tx, next_record, reviewer, now)
            tx.projection_updated()
            return {
                "memory": next_record,
                "review_id": review_id,
                "conflict": decision_state == "quarantined" and decision == "accepted",
            }

        return self.store.command(idempotency_key, command, operation)[0]

    def mark_stale(
        self,
        memory_id: str,
        reason: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        command = {
            "command": "mark_memory_stale",
            "memory_id": memory_id,
            "reason": reason,
            "expected_version": expected_version,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version(
                "memory_records", "memory_id", memory_id, expected_version
            )
            row = self._row(memory_id)
            if row["review_state"] != "accepted":
                raise CoreError("only accepted memory may become stale")
            record = json.loads(row["record_json"])
            record.update(aggregate_version=expected_version + 1, review_state="stale")
            marker = tx.append_event(
                aggregate_type="memory",
                aggregate_id=memory_id,
                event_type="memory.stale",
                aggregate_version=expected_version + 1,
                actor=actor,
                payload={"reason": reason, "record_sha256": sha256_json(record)},
                sensitivity=record["sensitivity"],
            )
            self._update_projection(record, marker, utc_now(), stale_reason=reason)
            self.store.conn.execute(
                "DELETE FROM memory_fts WHERE memory_id = ?", (memory_id,)
            )
            tx.projection_updated()
            return record

        return self.store.command(idempotency_key, command, operation)[0]

    def revalidate(
        self,
        memory_id: str,
        evidence_refs: list[dict[str, Any]],
        revalidate_at: str,
        *,
        expected_version: int,
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        command = {
            "command": "revalidate_memory",
            "memory_id": memory_id,
            "evidence_refs": evidence_refs,
            "revalidate_at": revalidate_at,
            "expected_version": expected_version,
            "actor": actor,
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            tx.expect_version(
                "memory_records", "memory_id", memory_id, expected_version
            )
            row = self._row(memory_id)
            if row["review_state"] != "stale":
                raise CoreError("only stale memory may be revalidated")
            record = json.loads(row["record_json"])
            old_sources = sorted(
                (source["uri"], source["content_sha256"])
                for source in record["evidence_refs"]
            )
            new_sources = sorted(
                (source["uri"], source["content_sha256"]) for source in evidence_refs
            )
            if old_sources != new_sources or any(
                source["validity_status"] != "current" for source in evidence_refs
            ):
                raise CoreError(
                    "changed or non-current evidence requires a new candidate"
                )
            record.update(
                aggregate_version=expected_version + 1,
                evidence_refs=evidence_refs,
                revalidate_at=revalidate_at,
                review_state="accepted",
            )
            self._validate(record)
            marker = tx.append_event(
                aggregate_type="memory",
                aggregate_id=memory_id,
                event_type="memory.accepted",
                aggregate_version=expected_version + 1,
                actor=actor,
                payload={"reason": "revalidated", "record_sha256": sha256_json(record)},
                sensitivity=record["sensitivity"],
            )
            self._update_projection(record, marker, utc_now(), stale_reason=None)
            self._index_record(record)
            tx.projection_updated()
            return record

        return self.store.command(idempotency_key, command, operation)[0]

    def sweep_stale(
        self, *, now: str, actor: str = "service:memory-sweeper"
    ) -> list[str]:
        parse_time(now)
        stale: list[str] = []
        rows = self.store.conn.execute(
            "SELECT memory_id, aggregate_version, record_json FROM memory_records WHERE review_state = 'accepted'"
        ).fetchall()
        for row in rows:
            record = json.loads(row["record_json"])
            reason = self._stale_reason(record, now)
            if reason:
                self.mark_stale(
                    row["memory_id"],
                    reason,
                    expected_version=int(row["aggregate_version"]),
                    actor=actor,
                    idempotency_key=f"memory:sweep:{now}:{row['memory_id']}",
                )
                stale.append(str(row["memory_id"]))
        return stale

    def mark_source_changed(
        self,
        uri: str,
        content_sha256: str,
        *,
        observed_at: str,
        actor: str = "service:source-monitor",
    ) -> list[str]:
        parse_time(observed_at)
        changed: list[str] = []
        for row in self.store.conn.execute(
            "SELECT memory_id, aggregate_version, record_json FROM memory_records WHERE review_state = 'accepted'"
        ):
            record = json.loads(row["record_json"])
            if any(
                source["uri"] == uri and source["content_sha256"] != content_sha256
                for source in record["evidence_refs"]
            ):
                self.mark_stale(
                    row["memory_id"],
                    "source_revision_changed",
                    expected_version=int(row["aggregate_version"]),
                    actor=actor,
                    idempotency_key=f"memory:source-change:{sha256_json([uri, content_sha256])}:{row['memory_id']}",
                )
                changed.append(str(row["memory_id"]))
        return changed

    def retrieve(
        self,
        query: str,
        *,
        allowed_scopes: list[str],
        clearance: str,
        now: str | None = None,
    ) -> RetrievalResult:
        if clearance not in SENSITIVITY:
            raise CoreError(f"unknown sensitivity clearance: {clearance}")
        if not allowed_scopes:
            return RetrievalResult(
                normalize_text(query), [], [], [], [], ["scope_allowlist"]
            )
        current_time = now or utc_now()
        parse_time(current_time)
        normalized = normalize_text(query)
        terms = sorted(set(WORD.findall(normalized)))
        placeholders = ",".join("?" for _ in allowed_scopes)
        rows = self.store.conn.execute(
            f"SELECT * FROM memory_records WHERE scope IN ({placeholders}) ORDER BY memory_id",
            allowed_scopes,
        ).fetchall()
        fts_matches: set[str]
        if terms:
            match_query = " OR ".join(
                '"' + term.replace('"', '""') + '"' for term in terms
            )
            fts_matches = {
                str(row[0])
                for row in self.store.conn.execute(
                    "SELECT memory_id FROM memory_fts WHERE memory_fts MATCH ?",
                    (match_query,),
                )
            }
        else:
            fts_matches = {
                str(row["memory_id"])
                for row in rows
                if row["review_state"] == "accepted"
            }

        ranked: list[tuple[int, int, str, str, dict[str, Any]]] = []
        excluded: list[dict[str, str]] = []
        candidate_ids: list[str] = []
        for row in rows:
            memory_id = str(row["memory_id"])
            record = json.loads(row["record_json"])
            reason: str | None = None
            if row["review_state"] != "accepted":
                reason = str(row["review_state"])
            elif SENSITIVITY[str(row["sensitivity"])] > SENSITIVITY[clearance]:
                reason = "sensitivity_denied"
            else:
                reason = self._stale_reason(record, current_time)
            if reason is None and memory_id not in fts_matches:
                reason = "query_miss"
            if reason:
                excluded.append({"memory_id": memory_id, "reason": reason})
                continue
            candidate_ids.append(memory_id)
            haystack = normalize_text(
                " ".join([record["statement"], *record["labels"], _source_text(record)])
            )
            occurrences = sum(haystack.count(term) for term in terms) if terms else 1
            word_count = max(1, len(WORD.findall(haystack)))
            score_units = (occurrences * 1_000_000) // word_count
            ranked.append(
                (
                    TYPE_PRIORITY[record["type"]],
                    -score_units,
                    _invert_timestamp(_max_observed(record)),
                    memory_id,
                    record,
                )
            )
        ranked.sort(key=lambda item: item[:4])
        ranked_candidates = [
            {
                "memory_id": item[3],
                "score": _format_score(-item[1]),
                "rank": rank,
            }
            for rank, item in enumerate(ranked, 1)
        ]
        return RetrievalResult(
            normalized_query=normalized,
            candidate_memory_ids=candidate_ids,
            ranked_candidates=ranked_candidates,
            records=[item[4] for item in ranked],
            excluded=excluded,
            filters=[
                "scope_allowlist",
                "accepted_only",
                "sensitivity_clearance",
                "validity_window",
                "source_current",
                "fts_match",
            ],
        )

    def assemble_context(
        self,
        task_id: str,
        query: str,
        *,
        allowed_scopes: list[str],
        clearance: str,
        section_budgets: dict[str, int],
        actor: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        run = self.store.conn.execute(
            "SELECT * FROM runs WHERE task_id = ? ORDER BY attempt_number DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if run is None:
            raise CoreError("context assembly requires a leased task run")
        envelope = json.loads(run["task_envelope_json"])
        permitted_scopes = set(envelope["memory_scopes"]) | {f"task:{task_id}"}
        if not set(allowed_scopes).issubset(permitted_scopes):
            raise CoreError("context scope request exceeds the task envelope")
        assembly_now = utc_now()
        self.sweep_stale(now=assembly_now)
        retrieval = self.retrieve(
            query, allowed_scopes=allowed_scopes, clearance=clearance
        )
        command = {
            "command": "assemble_context",
            "task_id": task_id,
            "run_id": run["run_id"],
            "query": query,
            "allowed_scopes": allowed_scopes,
            "clearance": clearance,
            "section_budgets": section_budgets,
            "task_envelope_sha256": run["task_envelope_sha256"],
        }

        def operation(tx: WriteTransaction) -> dict[str, Any]:
            ordered_sections = [
                name for name in SECTION_ORDER if name in section_budgets
            ]
            unknown_sections = sorted(set(section_budgets) - set(SECTION_ORDER))
            if unknown_sections:
                raise CoreError(f"unknown context sections: {unknown_sections}")
            if any(int(value) < 0 for value in section_budgets.values()):
                raise CoreError("context section budgets must be non-negative")
            selected: list[dict[str, Any]] = []
            excluded = list(retrieval.excluded)
            used = {name: 0 for name in ordered_sections}
            truncated = {name: False for name in ordered_sections}
            for record in retrieval.records:
                section = _section(record)
                budget = int(section_budgets.get(section, 0))
                remaining = budget - used.get(section, 0)
                if remaining <= 0:
                    excluded.append(
                        {"memory_id": record["memory_id"], "reason": "section_budget"}
                    )
                    truncated[section] = True
                    continue
                excerpt = record["statement"]
                count = token_count(excerpt)
                if count > remaining:
                    excerpt = excerpt[: remaining * 4].rstrip()
                    if not excerpt:
                        excluded.append(
                            {
                                "memory_id": record["memory_id"],
                                "reason": "section_budget",
                            }
                        )
                        truncated[section] = True
                        continue
                    count = token_count(excerpt)
                    truncated[section] = True
                selected.append(
                    {
                        "memory_id": record["memory_id"],
                        "excerpt": excerpt,
                        "excerpt_sha256": sha256_bytes(excerpt.encode("utf-8")),
                        "section": section,
                        "token_count": count,
                    }
                )
                used[section] = used.get(section, 0) + count
            snapshot_high_water = int(self.store.meta("global_sequence"))
            projection = [
                json.loads(row[0])
                for row in self.store.conn.execute(
                    "SELECT record_json FROM memory_records ORDER BY memory_id"
                )
            ]
            now = utc_now()
            context_id = new_id("context")
            manifest = {
                "schema_version": "city2.context-pack/v1",
                "context_id": context_id,
                "task_id": task_id,
                "task_envelope_sha256": run["task_envelope_sha256"],
                "assembler": {"id": "city2-context", "version": "1"},
                "retrieval_policy": {"id": "memory-fts", "version": "1"},
                "tokenizer": {"id": "unicode-codepoint-char4", "version": "1"},
                "normalized_query": retrieval.normalized_query,
                "source_snapshot": {
                    "event_high_water": snapshot_high_water,
                    "memory_projection_sha256": sha256_json(projection),
                },
                "candidate_memory_ids": retrieval.candidate_memory_ids,
                "filters": retrieval.filters,
                "ranked_candidates": retrieval.ranked_candidates,
                "selected": selected,
                "excluded": sorted(
                    excluded, key=lambda item: (item["memory_id"], item["reason"])
                ),
                "tie_break": [
                    "policy_priority_asc",
                    "relevance_desc",
                    "evidence_observed_desc",
                    "memory_id_asc",
                ],
                "sections": [
                    {
                        "name": name,
                        "token_budget": int(budget),
                        "token_count": used.get(name, 0),
                        "truncated": truncated.get(name, False),
                    }
                    for name in ordered_sections
                    for budget in (section_budgets[name],)
                ],
                "total_tokens": sum(item["token_count"] for item in selected),
                "pack_sha256": "",
                "sensitivity": _max_sensitivity(selected, retrieval.records),
                "created_at": now,
            }
            manifest["pack_sha256"] = digest_profile(manifest, {"pack_sha256"})
            try:
                validate_named(manifest, "context-pack.schema.json", self.store.schemas)
            except ValidationError as error:
                raise CoreError(f"context-pack.schema.json: {error}") from error
            content = {
                "task": {
                    "task_id": task_id,
                    "task_revision": envelope["task_revision"],
                    "intent": envelope["intent"],
                    "acceptance_criteria": envelope["acceptance_criteria"],
                    "constraints": envelope["constraints"],
                },
                "memory": selected,
            }
            run_version = (
                int(
                    self.store.conn.execute(
                        "SELECT COALESCE(MAX(aggregate_version), 0) FROM events WHERE aggregate_id = ?",
                        (run["run_id"],),
                    ).fetchone()[0]
                )
                + 1
            )
            tx.append_event(
                aggregate_type="run",
                aggregate_id=run["run_id"],
                event_type="run.context_assembled",
                aggregate_version=run_version,
                actor=actor,
                payload={
                    "context_id": context_id,
                    "manifest_sha256": sha256_json(manifest),
                    "content_sha256": sha256_json(content),
                    "source_event_high_water": snapshot_high_water,
                },
                sensitivity=manifest["sensitivity"],
            )
            self.store.conn.execute(
                """INSERT INTO context_packs
                   (context_id, task_id, run_id, manifest_sha256, manifest_json,
                    content_sha256, content_json, event_high_water, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    context_id,
                    task_id,
                    run["run_id"],
                    sha256_json(manifest),
                    canonical_json(manifest),
                    sha256_json(content),
                    canonical_json(content),
                    snapshot_high_water,
                    now,
                ),
            )
            tx.projection_updated()
            return {"manifest": manifest, "content": content}

        return self.store.command(idempotency_key, command, operation)[0]

    def rebuild_index(self) -> int:
        self.store.conn.execute("BEGIN IMMEDIATE")
        try:
            self.store.conn.execute("DELETE FROM memory_fts")
            rows = self.store.conn.execute(
                "SELECT record_json FROM memory_records WHERE review_state = 'accepted' ORDER BY memory_id"
            ).fetchall()
            for row in rows:
                self._index_record(json.loads(row["record_json"]))
            self.store.conn.commit()
        except BaseException:
            self.store.conn.rollback()
            raise
        self.store.verify_integrity()
        return len(rows)

    def export_memories(self) -> dict[str, Any]:
        high_water = int(self.store.meta("global_sequence"))
        event_rows = self.store.conn.execute(
            "SELECT * FROM events WHERE aggregate_type = 'memory' ORDER BY database_sequence"
        ).fetchall()
        events = []
        for row in event_rows:
            event = self.store._event_from_row(row)
            event["event_sha256"] = row["event_sha256"]
            events.append(event)
        records = [
            json.loads(row[0])
            for row in self.store.conn.execute(
                """SELECT record_json FROM memory_records
                   WHERE review_state = 'accepted' ORDER BY memory_id"""
            )
        ]
        export = {
            "schema_version": "city2.memory-export/v1",
            "source_database_id": self.store.meta("database_id"),
            "source_writer_id": self.store.writer_id,
            "source_event_high_water": high_water,
            "memory_events": events,
            "accepted_memories": records,
        }
        return {"export": export, "sha256": sha256_json(export)}

    def import_export(
        self,
        export: dict[str, Any],
        *,
        actor: str,
        import_key: str,
    ) -> dict[str, Any]:
        if export.get("schema_version") != "city2.memory-export/v1":
            raise CoreError("unsupported memory export")
        event_ids: set[str] = set()
        for event in export.get("memory_events", []):
            event_sha = event.get("event_sha256")
            envelope = {
                key: value for key, value in event.items() if key != "event_sha256"
            }
            if event_sha != sha256_json(envelope) or event["event_id"] in event_ids:
                raise IntegrityError("corrupt or duplicate exported event")
            event_ids.add(event["event_id"])
            local = self.store.conn.execute(
                "SELECT event_sha256 FROM events WHERE event_id = ?",
                (event["event_id"],),
            ).fetchone()
            if local is not None and local["event_sha256"] != event_sha:
                raise IntegrityError("event identity collision during memory import")
        records = export.get("accepted_memories", [])
        for record in records:
            self._validate(record)
            if record["review_state"] != "accepted":
                raise IntegrityError("memory export contains non-accepted record")
        imported: list[str] = []
        for record in records:
            fields = {
                key: record[key]
                for key in (
                    "scope",
                    "type",
                    "statement",
                    "evidence_refs",
                    "asserted_by",
                    "owner",
                    "valid_from",
                    "fact_class",
                    "revalidation_policy",
                    "revalidate_at",
                    "confidence",
                    "sensitivity",
                    "labels",
                )
            }
            if "valid_until" in record:
                fields["valid_until"] = record["valid_until"]
            candidate = self.create_candidate(
                fields,
                actor=actor,
                idempotency_key=f"memory:import:{import_key}:{record['memory_id']}",
            )
            imported.append(candidate["memory_id"])
        return {"imported_memory_ids": imported, "export_sha256": sha256_json(export)}

    def get(self, memory_id: str) -> dict[str, Any]:
        return json.loads(self._row(memory_id)["record_json"])

    def _insert_projection(
        self, record: dict[str, Any], candidate_sha: str, marker: Any, now: str
    ) -> None:
        self.store.conn.execute(
            """INSERT INTO memory_records
               (memory_id, aggregate_version, scope, memory_type, review_state,
                candidate_sha256, record_sha256, statement, labels_text, source_text,
                record_json, created_by, revalidate_at, valid_from, valid_until,
                sensitivity, last_event_id, last_event_sha256, event_high_water,
                created_at, updated_at)
               VALUES (?, 1, ?, ?, 'candidate', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["memory_id"],
                record["scope"],
                record["type"],
                candidate_sha,
                sha256_json(record),
                record["statement"],
                normalize_text(" ".join(record["labels"])),
                _source_text(record),
                canonical_json(record),
                record["created_by"],
                record["revalidate_at"],
                record["valid_from"],
                record.get("valid_until"),
                record["sensitivity"],
                marker.event_id,
                marker.event_sha256,
                marker.database_sequence,
                record["created_at"],
                now,
            ),
        )

    def _update_projection(
        self,
        record: dict[str, Any],
        marker: Any,
        now: str,
        *,
        reviewed_by: str | None = None,
        accepted_at: str | None = None,
        stale_reason: str | None = None,
    ) -> None:
        self.store.conn.execute(
            """UPDATE memory_records SET aggregate_version = ?, review_state = ?,
               record_sha256 = ?, record_json = ?, reviewed_by = COALESCE(?, reviewed_by),
               accepted_at = COALESCE(?, accepted_at), stale_reason = ?,
               revalidate_at = ?, valid_until = ?, last_event_id = ?,
               last_event_sha256 = ?, event_high_water = ?, updated_at = ?
               WHERE memory_id = ?""",
            (
                record["aggregate_version"],
                record["review_state"],
                sha256_json(record),
                canonical_json(record),
                reviewed_by,
                accepted_at,
                stale_reason,
                record["revalidate_at"],
                record.get("valid_until"),
                marker.event_id,
                marker.event_sha256,
                marker.database_sequence,
                now,
                record["memory_id"],
            ),
        )

    def _index_record(self, record: dict[str, Any]) -> None:
        self.store.conn.execute(
            "DELETE FROM memory_fts WHERE memory_id = ?", (record["memory_id"],)
        )
        self.store.conn.execute(
            "INSERT INTO memory_fts(memory_id, statement, labels, source_metadata) VALUES (?, ?, ?, ?)",
            (
                record["memory_id"],
                normalize_text(record["statement"]),
                normalize_text(" ".join(record["labels"])),
                _source_text(record),
            ),
        )

    def _supersede_in_tx(
        self, tx: WriteTransaction, record: dict[str, Any], actor: str, now: str
    ) -> None:
        for old_id in record["supersedes"]:
            old = self._row(old_id)
            if old["review_state"] != "accepted" or old["scope"] != record["scope"]:
                raise CoreError("superseded memory must be accepted in the same scope")
            old_record = json.loads(old["record_json"])
            old_record.update(
                aggregate_version=int(old["aggregate_version"]) + 1,
                review_state="superseded",
            )
            marker = tx.append_event(
                aggregate_type="memory",
                aggregate_id=old_id,
                event_type="memory.superseded",
                aggregate_version=old_record["aggregate_version"],
                actor=actor,
                payload={
                    "superseded_by": record["memory_id"],
                    "record_sha256": sha256_json(old_record),
                },
                sensitivity=old_record["sensitivity"],
            )
            self._update_projection(old_record, marker, now)
            self.store.conn.execute(
                "DELETE FROM memory_fts WHERE memory_id = ?", (old_id,)
            )

    def _verify_source_checks(
        self, record: dict[str, Any], checks: list[dict[str, str]]
    ) -> None:
        expected = sorted(
            (source["uri"], source["content_sha256"], source["validity_status"])
            for source in record["evidence_refs"]
        )
        actual = sorted(
            (check["uri"], check["content_sha256"], check["validity_status"])
            for check in checks
        )
        if actual != expected or any(status != "current" for _, _, status in actual):
            raise CoreError(
                "source checks do not prove every evidence reference current"
            )

    def _find_conflict(self, record: dict[str, Any]) -> Any | None:
        if record["type"] != "fact":
            return None
        labels = set(record["labels"])
        for row in self.store.conn.execute(
            """SELECT memory_id, record_json FROM memory_records
               WHERE scope = ? AND memory_type = 'fact' AND review_state = 'accepted'""",
            (record["scope"],),
        ):
            other = json.loads(row["record_json"])
            if (
                other["fact_class"] == record["fact_class"]
                and labels.intersection(other["labels"])
                and row["memory_id"] not in record["supersedes"]
                and normalize_text(other["statement"])
                != normalize_text(record["statement"])
            ):
                return row
        return None

    def _stale_reason(self, record: dict[str, Any], now: str) -> str | None:
        current = parse_time(now)
        if parse_time(record["revalidate_at"]) <= current:
            return "revalidation_due"
        if "valid_until" in record and parse_time(record["valid_until"]) <= current:
            return "validity_expired"
        if any(
            source["validity_status"] != "current" for source in record["evidence_refs"]
        ):
            return "source_not_current"
        return None

    def _row(self, memory_id: str) -> Any:
        row = self.store.conn.execute(
            "SELECT * FROM memory_records WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            raise CoreError(f"unknown memory: {memory_id}")
        return row


def _format_score(units: int) -> str:
    return format(Decimal(units) / Decimal(1_000_000), ".6f")


def _invert_timestamp(value: str) -> str:
    parsed = parse_time(value)
    micros = int(parsed.timestamp() * 1_000_000)
    return f"{9_999_999_999_999_999 - micros:016d}"


def _section(record: dict[str, Any]) -> str:
    if record["scope"] == "company" and set(record["labels"]).intersection(
        {"constitution", "hard_policy"}
    ):
        return "constitution"
    return {
        "decision": "project_decisions",
        "preference": "project_decisions",
        "feedback": "role_authority",
        "procedure": "procedures",
        "fact": "knowledge",
        "reference": "knowledge",
        "outcome": "knowledge",
        "hypothesis": "knowledge",
    }[record["type"]]


def _max_sensitivity(
    selected: list[dict[str, Any]], records: list[dict[str, Any]]
) -> str:
    selected_ids = {item["memory_id"] for item in selected}
    values = [
        record["sensitivity"]
        for record in records
        if record["memory_id"] in selected_ids
    ]
    return max(values, key=lambda value: SENSITIVITY[value], default="public")
