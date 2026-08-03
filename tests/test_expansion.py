from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from city2core.expansion import (  # noqa: E402
    ExpansionAdmissionError,
    validate_expansion_admission,
)
from city2core.model import digest_profile  # noqa: E402


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def rehash(record: dict) -> dict:
    record["decision_sha256"] = digest_profile(
        record, {"aggregate_version", "decision_sha256"}
    )
    return record


class ExpansionAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.valid = load("fixtures/contracts/v1/valid/expansion-admission.json")

    def test_admitted_role_passes(self):
        validate_expansion_admission(self.valid)

    def test_current_defer_is_valid_and_inactive(self):
        current = load("config/expansion-admission.m7.json")
        validate_expansion_admission(current)
        self.assertEqual(current["decision"], "defer")
        self.assertEqual(current["candidate"]["activation_state"], "disabled")

    def test_tampered_decision_digest_fails(self):
        tampered = copy.deepcopy(self.valid)
        tampered["measurement"]["baseline_value"] += 1
        with self.assertRaisesRegex(ExpansionAdmissionError, "digest mismatch"):
            validate_expansion_admission(tampered)

    def test_admission_below_threshold_fails(self):
        below = copy.deepcopy(self.valid)
        below["measurement"]["baseline_value"] = 2
        rehash(below)
        with self.assertRaisesRegex(ExpansionAdmissionError, "threshold"):
            validate_expansion_admission(below)

    def test_role_cannot_smuggle_authority(self):
        elevated = copy.deepcopy(self.valid)
        elevated["candidate"]["target_authority"] = "A1"
        elevated["incident_boundary"]["authority_ceiling"] = "A1"
        rehash(elevated)
        with self.assertRaisesRegex(ExpansionAdmissionError, "cannot also"):
            validate_expansion_admission(elevated)

    def test_write_authority_allows_exactly_one_class(self):
        elevated = copy.deepcopy(self.valid)
        elevated["candidate"]["kind"] = "write-authority"
        elevated["candidate"]["target_authority"] = "A1"
        elevated["incident_boundary"]["authority_ceiling"] = "A1"
        rehash(elevated)
        validate_expansion_admission(elevated)

    def test_write_authority_cannot_skip_a_class(self):
        elevated = copy.deepcopy(self.valid)
        elevated["candidate"]["kind"] = "write-authority"
        elevated["candidate"]["target_authority"] = "A2"
        elevated["incident_boundary"]["authority_ceiling"] = "A2"
        rehash(elevated)
        with self.assertRaisesRegex(ExpansionAdmissionError, "exactly one"):
            validate_expansion_admission(elevated)

    def test_nanosecond_timestamps_remain_orderable(self):
        precise = copy.deepcopy(self.valid)
        precise["created_at"] = "2026-08-01T00:00:00.000000001Z"
        precise["accountable_approver"][
            "reviewed_at"
        ] = "2026-08-01T00:00:00.000000002Z"
        rehash(precise)
        validate_expansion_admission(precise)

    def test_explicit_threshold_passes(self):
        explicit = copy.deepcopy(self.valid)
        explicit["measurement"].update(
            threshold_mode="explicit",
            baseline_value="multi-host-writes-required",
            admission_threshold="multi-host-writes-required",
            target_value="multi-host-writes-supported",
            direction="match",
        )
        rehash(explicit)
        validate_expansion_admission(explicit)

    def test_stale_accountable_approval_fails(self):
        stale = copy.deepcopy(self.valid)
        stale["accountable_approver"][
            "reviewed_at"
        ] = "2025-01-01T00:00:00Z"
        rehash(stale)
        with self.assertRaisesRegex(ExpansionAdmissionError, "review window"):
            validate_expansion_admission(stale)

    def test_accountable_approval_must_follow_latest_evidence(self):
        tied = copy.deepcopy(self.valid)
        tied["accountable_approver"]["reviewed_at"] = max(
            tied["created_at"],
            tied["measurement"]["window_end"],
            *(reference["observed_at"] for reference in tied["measurement"]["evidence_refs"]),
            *(
                reference["observed_at"]
                for criterion in tied["evaluation"]["criteria"]
                for reference in criterion["evidence_refs"]
            ),
        )
        rehash(tied)
        with self.assertRaisesRegex(ExpansionAdmissionError, "review window"):
            validate_expansion_admission(tied)

    def test_admission_requires_human_accountable_approver(self):
        self_approved = copy.deepcopy(self.valid)
        self_approved["accountable_approver"]["actor"] = "agent:self"
        rehash(self_approved)
        with self.assertRaisesRegex(ExpansionAdmissionError, "human"):
            validate_expansion_admission(self_approved)

    def test_measurement_evidence_must_be_inside_window(self):
        stale = copy.deepcopy(self.valid)
        stale["measurement"]["evidence_refs"][0][
            "observed_at"
        ] = "2026-06-30T23:59:59Z"
        rehash(stale)
        with self.assertRaisesRegex(ExpansionAdmissionError, "declared window"):
            validate_expansion_admission(stale)


if __name__ == "__main__":
    unittest.main()
