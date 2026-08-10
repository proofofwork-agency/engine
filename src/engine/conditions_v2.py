from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from engine_sdk import (
    ConditionV1,
    EntityV1,
    EvidenceGrade,
    ObservationV1,
    ScopedConditionV1,
    WorldSnapshotV2,
)


@dataclass(frozen=True)
class ConditionResult:
    value: bool | None
    grade: EvidenceGrade
    evidence_ids: tuple[str, ...]
    reason: str


def select_entities(
    snapshot: WorldSnapshotV2, selector: dict[str, Any]
) -> tuple[EntityV1, ...]:
    entity_ids = {str(item) for item in selector.get("entity_ids", ())}
    target_ids = {str(item) for item in selector.get("target_ids", ())}
    entity_type = selector.get("entity_type")
    attributes = selector.get("attributes", {})
    if not isinstance(attributes, dict):
        return ()
    result = []
    for entity in snapshot.entities:
        if entity_ids and entity.id not in entity_ids:
            continue
        if target_ids and entity.target_id not in target_ids:
            continue
        if entity_type is not None and entity.entity_type != str(entity_type):
            continue
        if any(entity.attributes.get(key) != value for key, value in attributes.items()):
            continue
        result.append(entity)
    return tuple(result)


def evaluate_condition(
    condition: ConditionV1,
    snapshot: WorldSnapshotV2,
    *,
    selector: dict[str, Any] | None = None,
    previous: WorldSnapshotV2 | None = None,
    now: datetime | None = None,
) -> ConditionResult:
    if condition.op in {"all", "any", "not"}:
        children = tuple(
            evaluate_condition(
                item,
                snapshot,
                selector=selector,
                previous=previous,
                now=now,
            )
            for item in condition.children
        )
        evidence = tuple(dict.fromkeys(value for item in children for value in item.evidence_ids))
        if condition.op == "not":
            child = children[0]
            return ConditionResult(
                None if child.value is None else not child.value,
                child.grade,
                evidence,
                f"not ({child.reason})",
            )
        known = [item.value for item in children if item.value is not None]
        if condition.op == "all":
            value = False if False in known else (True if len(known) == len(children) else None)
        else:
            value = True if True in known else (False if len(known) == len(children) else None)
        return ConditionResult(
            value,
            _combined_grade(children),
            evidence,
            f"{condition.op}({', '.join(item.reason for item in children)})",
        )

    observations, raw_values = _resolve(condition.path or "", snapshot, selector or {})
    evidence = tuple(item.id for item in observations)
    if condition.unit is not None:
        units = {item.unit for item in observations}
        if units and units != {condition.unit}:
            return ConditionResult(
                None,
                EvidenceGrade.CONFLICTING,
                evidence,
                f"unit mismatch: expected {condition.unit}, observed {sorted(str(item) for item in units)}",
            )
    if any(item.evidence_grade is EvidenceGrade.CONFLICTING for item in observations):
        return ConditionResult(None, EvidenceGrade.CONFLICTING, evidence, "required evidence is conflicting")
    if any(item.evidence_grade is EvidenceGrade.STALE for item in observations):
        return ConditionResult(None, EvidenceGrade.STALE, evidence, "required evidence is stale")
    if any(item.evidence_grade is EvidenceGrade.UNKNOWN for item in observations):
        return ConditionResult(None, EvidenceGrade.UNKNOWN, evidence, "required evidence is unknown")
    if not raw_values and condition.op != "exists":
        return ConditionResult(None, EvidenceGrade.UNKNOWN, evidence, "path has no covered value")
    if condition.op == "exists":
        return ConditionResult(bool(raw_values), EvidenceGrade.DERIVED, evidence, "path coverage checked")
    if condition.op == "changed":
        if previous is None:
            return ConditionResult(None, EvidenceGrade.UNKNOWN, evidence, "no previous snapshot")
        _, old_values = _resolve(condition.path or "", previous, selector or {})
        return ConditionResult(raw_values != old_values, EvidenceGrade.DERIVED, evidence, "change compared across snapshots")
    if condition.op == "count":
        wanted = condition.count if condition.count is not None else condition.value
        return ConditionResult(len(raw_values) == int(wanted), EvidenceGrade.DERIVED, evidence, "covered value count compared")
    if condition.op in {"within", "duration"}:
        return _evaluate_time(condition, observations, raw_values, evidence, now)
    try:
        results = tuple(_compare(condition.op, value, condition.value) for value in raw_values)
    except (TypeError, ValueError) as exc:
        return ConditionResult(None, EvidenceGrade.CONFLICTING, evidence, f"incomparable values: {exc}")
    # A desired effect over a selector applies to every selected covered entity.
    return ConditionResult(
        all(results),
        EvidenceGrade.DERIVED,
        evidence,
        f"{condition.path} {condition.op} {condition.value!r} over {len(results)} value(s)",
    )


def evaluate_scoped_condition(
    condition: ScopedConditionV1,
    snapshot: WorldSnapshotV2,
    *,
    previous: WorldSnapshotV2 | None = None,
    now: datetime | None = None,
) -> ConditionResult:
    """Evaluate a cross-target routine guard without inheriting one selector."""
    if condition.op in {"all", "any", "not"}:
        children = tuple(
            evaluate_scoped_condition(
                item, snapshot, previous=previous, now=now
            )
            for item in condition.children
        )
        evidence = tuple(
            dict.fromkeys(value for item in children for value in item.evidence_ids)
        )
        if condition.op == "not":
            child = children[0]
            return ConditionResult(
                None if child.value is None else not child.value,
                child.grade,
                evidence,
                f"not ({child.reason})",
            )
        known = [item.value for item in children if item.value is not None]
        if condition.op == "all":
            value = False if False in known else (
                True if len(known) == len(children) else None
            )
        else:
            value = True if True in known else (
                False if len(known) == len(children) else None
            )
        return ConditionResult(
            value,
            _combined_grade(children),
            evidence,
            f"{condition.op}({', '.join(item.reason for item in children)})",
        )
    return evaluate_condition(
        condition.as_condition(),
        snapshot,
        selector=dict(condition.entity_selector or {}),
        previous=previous,
        now=now,
    )


def evaluate_effects(
    goal: Any,
    snapshot: WorldSnapshotV2,
    *,
    previous: WorldSnapshotV2 | None = None,
) -> dict[str, ConditionResult]:
    return {
        effect.id: evaluate_condition(
            effect.condition,
            snapshot,
            selector=effect.entity_selector,
            previous=previous,
        )
        for effect in goal.desired_effects
    }


def _resolve(
    path: str,
    snapshot: WorldSnapshotV2,
    selector: dict[str, Any],
) -> tuple[tuple[ObservationV1, ...], tuple[Any, ...]]:
    entities = select_entities(snapshot, selector)
    entity_ids = {item.id for item in entities}
    if path.startswith("observation:"):
        property_name = path.removeprefix("observation:")
        observations = tuple(
            item
            for item in snapshot.observations
            if item.entity_id in entity_ids and item.property == property_name
        )
        return observations, tuple(item.value for item in observations)
    if path.startswith("entity:"):
        attribute = path.removeprefix("entity:")
        values = tuple(
            item.attributes[attribute]
            for item in entities
            if attribute in item.attributes
        )
        return (), values
    if path == "world:entity_count":
        return (), (len(entities),)
    if path.startswith("target_revision:"):
        target_id = path.removeprefix("target_revision:")
        value = snapshot.target_revisions.get(target_id)
        return (), (() if value is None else (value,))
    return (), ()


def _evaluate_time(
    condition: ConditionV1,
    observations: tuple[ObservationV1, ...],
    values: tuple[Any, ...],
    evidence: tuple[str, ...],
    now: datetime | None,
) -> ConditionResult:
    boundary = now or datetime.now(UTC)
    seconds = condition.window_seconds if condition.op == "within" else condition.duration_seconds
    if seconds is None or not observations:
        return ConditionResult(None, EvidenceGrade.UNKNOWN, evidence, "time condition lacks window or timestamps")
    parsed: list[datetime] = []
    for item in observations:
        try:
            stamp = datetime.fromisoformat(item.observed_at)
        except ValueError:
            return ConditionResult(None, EvidenceGrade.UNKNOWN, evidence, "invalid observation timestamp")
        parsed.append(stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC))
    ages = [(boundary - item.astimezone(UTC)).total_seconds() for item in parsed]
    if condition.op == "within":
        value = all(age <= seconds for age in ages)
        return ConditionResult(value, EvidenceGrade.DERIVED, evidence, f"all evidence within {seconds}s")
    # Duration means the covered boolean condition has stayed equal to value for
    # at least the requested age. A full history provider can expose multiple rows.
    expected = condition.value
    matching = [age for age, value in zip(ages, values, strict=True) if value == expected]
    value = bool(matching) and max(matching) >= seconds
    return ConditionResult(value, EvidenceGrade.DERIVED, evidence, f"value duration >= {seconds}s")


def _compare(op: str, actual: Any, expected: Any) -> bool:
    return {
        "eq": lambda: actual == expected,
        "ne": lambda: actual != expected,
        "lt": lambda: actual < expected,
        "lte": lambda: actual <= expected,
        "gt": lambda: actual > expected,
        "gte": lambda: actual >= expected,
    }[op]()


def _combined_grade(results: tuple[ConditionResult, ...]) -> EvidenceGrade:
    grades = {item.grade for item in results}
    for value in (
        EvidenceGrade.CONFLICTING,
        EvidenceGrade.UNKNOWN,
        EvidenceGrade.STALE,
        EvidenceGrade.INFERRED,
        EvidenceGrade.DERIVED,
        EvidenceGrade.OBSERVED,
    ):
        if value in grades:
            return value
    return EvidenceGrade.UNKNOWN
