"""Fail-closed M7 measured-expansion admission checks."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .model import digest_profile


AUTHORITY_ORDER = ("A0", "A1", "A2", "A3", "A4")


class ExpansionAdmissionError(ValueError):
    """The candidate is not a valid measured one-unit expansion decision."""


def _timestamp(value: str) -> tuple[datetime, Decimal]:
    """Parse arbitrary-precision UTC timestamps without losing ordering."""

    try:
        whole, separator, fraction = value.removesuffix("Z").partition(".")
        moment = datetime.strptime(whole, "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        subsecond = Decimal(f"0.{fraction}") if separator else Decimal(0)
    except (ValueError, ArithmeticError) as error:
        raise ExpansionAdmissionError("expansion: invalid timestamp") from error
    return moment, subsecond


def validate_expansion_admission(record: dict[str, Any]) -> None:
    """Enforce semantic gates that JSON Schema alone cannot express."""

    expected_hash = digest_profile(
        record, {"aggregate_version", "decision_sha256"}
    )
    if record["decision_sha256"] != expected_hash:
        raise ExpansionAdmissionError("expansion: decision digest mismatch")

    measurement = record["measurement"]
    if _timestamp(measurement["window_end"]) < _timestamp(
        measurement["window_start"]
    ):
        raise ExpansionAdmissionError("expansion: measurement window is reversed")
    window_start = _timestamp(measurement["window_start"])
    window_end = _timestamp(measurement["window_end"])
    measurement_evidence_times = [
        _timestamp(reference["observed_at"])
        for reference in measurement["evidence_refs"]
    ]
    if any(
        observed_at < window_start or observed_at > window_end
        for observed_at in measurement_evidence_times
    ):
        raise ExpansionAdmissionError(
            "expansion: measurement evidence is outside the declared window"
        )
    if _timestamp(record["review_at"]) <= _timestamp(record["created_at"]):
        raise ExpansionAdmissionError("expansion: review must follow creation")

    candidate = record["candidate"]
    current = AUTHORITY_ORDER.index(candidate["current_authority"])
    target = AUTHORITY_ORDER.index(candidate["target_authority"])
    if candidate["kind"] == "role" and target != current:
        raise ExpansionAdmissionError(
            "expansion: a role addition cannot also expand authority"
        )
    if candidate["kind"] == "write-authority" and target != current + 1:
        raise ExpansionAdmissionError(
            "expansion: write authority must increase by exactly one class"
        )
    if record["incident_boundary"]["authority_ceiling"] != candidate[
        "target_authority"
    ]:
        raise ExpansionAdmissionError(
            "expansion: incident authority ceiling must match the candidate"
        )

    outward = record["incident_boundary"]["outward_actions"]
    required_outward = (
        "denied"
        if target < AUTHORITY_ORDER.index("A3")
        else "human-at-action-time"
        if target == AUTHORITY_ORDER.index("A3")
        else "hardened-operator"
    )
    if outward != required_outward:
        raise ExpansionAdmissionError(
            "expansion: outward-action boundary does not match authority"
        )

    criteria = record["evaluation"]["criteria"]
    criterion_names = [item["criterion"] for item in criteria]
    if len(criterion_names) != len(set(criterion_names)):
        raise ExpansionAdmissionError(
            "expansion: evaluation criteria must be unique"
        )
    if any(item["state"] == "pass" and not item["evidence_refs"] for item in criteria):
        raise ExpansionAdmissionError(
            "expansion: passing criteria require evidence"
        )

    values = (
        measurement["baseline_value"],
        measurement["admission_threshold"],
        measurement["target_value"],
    )
    if measurement["threshold_mode"] == "numeric":
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in values
        ):
            raise ExpansionAdmissionError(
                "expansion: numeric threshold requires numeric values"
            )
        if measurement["direction"] not in {"increase", "decrease"}:
            raise ExpansionAdmissionError(
                "expansion: numeric threshold requires a numeric direction"
            )
    else:
        if not all(isinstance(value, str) for value in values):
            raise ExpansionAdmissionError(
                "expansion: explicit threshold requires explicit values"
            )
        if measurement["direction"] != "match":
            raise ExpansionAdmissionError(
                "expansion: explicit threshold requires match direction"
            )

    if record["decision"] != "admit":
        return

    if record["accountable_approver"]["status"] != "approved" or not record[
        "accountable_approver"
    ].get("reviewed_at"):
        raise ExpansionAdmissionError(
            "expansion: admission requires accountable approval"
        )
    if not record["accountable_approver"]["actor"].startswith("human:"):
        raise ExpansionAdmissionError(
            "expansion: admission requires a human accountable approver"
        )
    approval_time = _timestamp(record["accountable_approver"]["reviewed_at"])
    evidence_times = list(measurement_evidence_times)
    for criterion in criteria:
        evidence_times.extend(
            _timestamp(reference["observed_at"])
            for reference in criterion["evidence_refs"]
        )
    approval_floor = max(
        _timestamp(record["created_at"]),
        _timestamp(measurement["window_end"]),
        *evidence_times,
    )
    if approval_time <= approval_floor or approval_time > _timestamp(
        record["review_at"]
    ):
        raise ExpansionAdmissionError(
            "expansion: accountable approval is outside the evidence review window"
        )
    if record["evaluation"]["status"] != "pass" or any(
        item["state"] != "pass" for item in criteria
    ):
        raise ExpansionAdmissionError(
            "expansion: admission requires every evaluation criterion to pass"
        )
    if measurement["sample_count"] < 1 or not measurement["evidence_refs"]:
        raise ExpansionAdmissionError(
            "expansion: admission requires measured samples and evidence"
        )

    baseline = measurement["baseline_value"]
    threshold = measurement["admission_threshold"]
    target_value = measurement["target_value"]
    if measurement["threshold_mode"] == "explicit":
        threshold_met = baseline == threshold
        improvement_is_directional = target_value != baseline
    elif measurement["direction"] == "increase":
        threshold_met = baseline >= threshold
        improvement_is_directional = target_value > baseline
    else:
        threshold_met = baseline <= threshold
        improvement_is_directional = target_value < baseline
    if not threshold_met:
        raise ExpansionAdmissionError(
            "expansion: measured baseline does not meet admission threshold"
        )
    if not improvement_is_directional:
        raise ExpansionAdmissionError(
            "expansion: target does not improve in the declared direction"
        )
