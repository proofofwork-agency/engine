from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, Any]
PLUGIN_CONTRACT_VERSION = "engine.plugin/v3"
SUPPORTED_PLUGIN_CONTRACT_VERSIONS = ("engine.plugin/v2", PLUGIN_CONTRACT_VERSION)
ENGINE_API_VERSION = "3.0"


class ContractError(ValueError):
    """A public contract value is malformed or internally inconsistent."""


class GoalModeV2(StrEnum):
    ACHIEVE = "achieve"
    MAINTAIN = "maintain"


class EvidenceGrade(StrEnum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"
    STALE = "STALE"


class ControlLayer(StrEnum):
    QUERY = "query"
    SEMANTIC = "semantic"
    ACTUATOR = "actuator"


class InvocationModeV2(StrEnum):
    IMMEDIATE = "immediate"
    TASK = "task"
    STREAM = "stream"


class RiskClass(StrEnum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PrivacyClass(StrEnum):
    PUBLIC = "public"
    LOCAL = "local"
    SENSITIVE = "sensitive"
    CAMERA = "camera"


class DecisionKindV2(StrEnum):
    QUERY_WORLD = "query_world"
    CONSULT_SPECIALIST = "consult_specialist"
    PROPOSE_EFFECT = "propose_effect"
    WAIT = "wait"
    COMPLETE = "complete"
    ABANDON = "abandon"


class PolicyOutcome(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DEFER = "DEFER"


class ExecutionStateV2(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class LearningStatus(StrEnum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class PreferencePromotionMode(StrEnum):
    EXPLICIT_ONLY = "explicit_only"
    SHADOW_LOW_RISK = "shadow_low_risk"


class RoutineStatus(StrEnum):
    SHADOW = "shadow"
    READY_FOR_APPROVAL = "ready_for_approval"
    ACTIVE = "active"
    DORMANT = "dormant"
    GUARD_UNCERTAIN = "guard_uncertain"
    CONFLICTED = "conflicted"
    SUSPENDED = "suspended"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class RoutineCandidateStatus(StrEnum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    READY_FOR_APPROVAL = "ready_for_approval"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class AutonomyModeV1(StrEnum):
    OBSERVE = "observe"
    SUPERVISED = "supervised"
    DELEGATED = "delegated"
    PAUSED = "paused"


class CognitionRouteV1(StrEnum):
    DETERMINISTIC = "deterministic"
    EXECUTIVE = "executive"
    SPECIALIST = "specialist"
    HYBRID = "hybrid"


class AutonomyDecisionKindV1(StrEnum):
    NOOP = "NOOP"
    DEFER = "DEFER"
    PROPOSE_EFFECT = "PROPOSE_EFFECT"
    PROPOSE_GOAL_CANDIDATE = "PROPOSE_GOAL_CANDIDATE"
    REQUEST_EXECUTIVE = "REQUEST_EXECUTIVE"
    REQUEST_SPECIALIST = "REQUEST_SPECIALIST"


class AutonomyBindingStatusV1(StrEnum):
    SHADOW = "shadow"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISPATCHED = "dispatched"
    DEFERRED = "deferred"
    SUPERSEDED = "superseded"


class DispatchAttemptStateV1(StrEnum):
    PREPARED = "prepared"
    ABORTED_BEFORE_IO = "aborted_before_io"
    RECEIPT_RECORDED = "receipt_recorded"
    EFFECT_RECONCILED = "effect_reconciled"
    RECOVERY_REQUIRED = "recovery_required"
    CLOSED_UNKNOWN = "closed_unknown"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_data(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return canonical_data(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): canonical_data(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [canonical_data(item) for item in value]
    if value is None or type(value) in {bool, int, float, str}:
        return value
    raise TypeError(f"value is not canonically serializable: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(canonical_data(value), sort_keys=True, separators=(",", ":"))


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _require(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ContractError(f"{name} must be non-empty")


def _has_wildcard(value: str) -> bool:
    return any(marker in value for marker in ("*", "?", "["))


@dataclass(frozen=True)
class ConditionV1:
    """Declarative condition AST; paths address observation/entity projections."""

    op: str
    path: str | None = None
    value: Any = None
    unit: str | None = None
    children: tuple["ConditionV1", ...] = ()
    window_seconds: float | None = None
    duration_seconds: float | None = None
    count: int | None = None

    def __post_init__(self) -> None:
        allowed = {
            "eq", "ne", "lt", "lte", "gt", "gte", "exists", "changed",
            "all", "any", "not", "count", "duration", "within",
        }
        if self.op not in allowed:
            raise ContractError(f"unsupported condition op: {self.op}")
        if self.op in {"all", "any", "not"} and not self.children:
            raise ContractError(f"{self.op} requires child conditions")
        if self.op not in {"all", "any", "not"} and not self.path:
            raise ContractError(f"{self.op} requires a path")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ConditionV1":
        return cls(
            op=str(value["op"]),
            path=str(value["path"]) if value.get("path") is not None else None,
            value=value.get("value"),
            unit=str(value["unit"]) if value.get("unit") is not None else None,
            children=tuple(cls.from_dict(item) for item in value.get("children", ())),
            window_seconds=(
                float(value["window_seconds"])
                if value.get("window_seconds") is not None else None
            ),
            duration_seconds=(
                float(value["duration_seconds"])
                if value.get("duration_seconds") is not None else None
            ),
            count=int(value["count"]) if value.get("count") is not None else None,
        )


@dataclass(frozen=True)
class ScopedConditionV1:
    """Condition AST whose leaves carry their own entity selector.

    Unlike ``ConditionV1`` this contract can safely combine facts from
    unrelated targets, for example local time and one Homey zone. Boolean
    nodes carry children; every comparison/time leaf carries a selector.
    """

    op: str
    entity_selector: JsonObject | None = None
    path: str | None = None
    value: Any = None
    unit: str | None = None
    children: tuple["ScopedConditionV1", ...] = ()
    window_seconds: float | None = None
    duration_seconds: float | None = None
    count: int | None = None

    def __post_init__(self) -> None:
        allowed = {
            "eq", "ne", "lt", "lte", "gt", "gte", "exists", "changed",
            "all", "any", "not", "count", "duration", "within",
        }
        if self.op not in allowed:
            raise ContractError(f"unsupported scoped condition op: {self.op}")
        if self.op in {"all", "any", "not"}:
            if not self.children:
                raise ContractError(f"{self.op} requires child conditions")
            if self.op == "not" and len(self.children) != 1:
                raise ContractError("not requires exactly one child condition")
            if self.entity_selector is not None or self.path is not None:
                raise ContractError("boolean scoped conditions cannot carry a leaf selector/path")
        else:
            if not self.path:
                raise ContractError(f"{self.op} requires a path")
            if self.entity_selector is None:
                raise ContractError("every scoped condition leaf requires entity_selector")
            canonical_data(self.entity_selector)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    def as_condition(self) -> ConditionV1:
        if self.op in {"all", "any", "not"}:
            raise ContractError("boolean scoped nodes are not standalone ConditionV1 leaves")
        return ConditionV1(
            op=self.op,
            path=self.path,
            value=self.value,
            unit=self.unit,
            window_seconds=self.window_seconds,
            duration_seconds=self.duration_seconds,
            count=self.count,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ScopedConditionV1":
        selector = value.get("entity_selector")
        return cls(
            op=str(value["op"]),
            entity_selector=(dict(selector) if isinstance(selector, Mapping) else None),
            path=str(value["path"]) if value.get("path") is not None else None,
            value=value.get("value"),
            unit=str(value["unit"]) if value.get("unit") is not None else None,
            children=tuple(cls.from_dict(item) for item in value.get("children", ())),
            window_seconds=(
                float(value["window_seconds"])
                if value.get("window_seconds") is not None else None
            ),
            duration_seconds=(
                float(value["duration_seconds"])
                if value.get("duration_seconds") is not None else None
            ),
            count=int(value["count"]) if value.get("count") is not None else None,
        )


@dataclass(frozen=True)
class DesiredEffectV1:
    id: str
    capability_family: str
    entity_selector: JsonObject
    condition: ConditionV1
    parameters: JsonObject = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        _require(self.id, "effect id")
        _require(self.capability_family, "capability_family")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DesiredEffectV1":
        return cls(
            id=str(value["id"]),
            capability_family=str(value["capability_family"]),
            entity_selector=dict(value.get("entity_selector", {})),
            condition=ConditionV1.from_dict(value["condition"]),
            parameters=dict(value.get("parameters", {})),
            description=str(value.get("description", "")),
        )


@dataclass(frozen=True)
class GoalSpecV2:
    id: str
    source_intent: str
    mode: GoalModeV2
    entity_scope: JsonObject
    desired_effects: tuple[DesiredEffectV1, ...]
    preferences: JsonObject = field(default_factory=dict)
    constraints: tuple[ConditionV1, ...] = ()
    budgets: JsonObject = field(default_factory=dict)
    stop_conditions: tuple[ConditionV1, ...] = ()
    mandate_id: str | None = None
    version: int = 1
    status: str = "active"
    priority: int = 0
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require(self.id, "goal id")
        _require(self.source_intent, "source_intent")
        if not self.desired_effects:
            raise ContractError("GoalSpecV2 requires at least one desired effect")
        if self.version < 1:
            raise ContractError("goal version must be positive")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GoalSpecV2":
        return cls(
            id=str(value["id"]),
            source_intent=str(value["source_intent"]),
            mode=GoalModeV2(str(value["mode"])),
            entity_scope=dict(value.get("entity_scope", {})),
            desired_effects=tuple(
                DesiredEffectV1.from_dict(item)
                for item in value.get("desired_effects", ())
            ),
            preferences=dict(value.get("preferences", {})),
            constraints=tuple(
                ConditionV1.from_dict(item) for item in value.get("constraints", ())
            ),
            budgets=dict(value.get("budgets", {})),
            stop_conditions=tuple(
                ConditionV1.from_dict(item)
                for item in value.get("stop_conditions", ())
            ),
            mandate_id=(
                str(value["mandate_id"]) if value.get("mandate_id") is not None else None
            ),
            version=int(value.get("version", 1)),
            status=str(value.get("status", "active")),
            priority=int(value.get("priority", 0)),
            created_at=str(value.get("created_at", utc_now())),
        )


@dataclass(frozen=True)
class RoutineTemplateSpecV1:
    """Static plugin declaration for one deterministically promotable routine."""

    id: str
    plugin_id: str
    capability_family: str
    pattern_schema: JsonObject
    guard_schema: JsonObject
    goal_schema: JsonObject
    priority: int
    shadow_days: int = 7
    minimum_shadow_opportunities: int = 3
    minimum_shadow_agreement: float = 0.80
    trigger_window_seconds: int = 1800
    description: str = ""

    def __post_init__(self) -> None:
        _require(self.id, "routine template id")
        _require(self.plugin_id, "routine template plugin_id")
        _require(self.capability_family, "routine template capability_family")
        if self.shadow_days < 7:
            raise ContractError("routine shadow must last at least seven days")
        if self.minimum_shadow_opportunities < 3:
            raise ContractError("routine shadow requires at least three opportunities")
        if not 0.80 <= self.minimum_shadow_agreement <= 1.0:
            raise ContractError("routine shadow agreement must be between 0.80 and 1.0")
        if self.trigger_window_seconds <= 0:
            raise ContractError("routine trigger window must be positive")
        canonical_data(self.pattern_schema)
        canonical_data(self.guard_schema)
        canonical_data(self.goal_schema)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RoutineTemplateSpecV1":
        return cls(
            id=str(value["id"]),
            plugin_id=str(value["plugin_id"]),
            capability_family=str(value["capability_family"]),
            pattern_schema=dict(value.get("pattern_schema", {})),
            guard_schema=dict(value.get("guard_schema", {})),
            goal_schema=dict(value.get("goal_schema", {})),
            priority=int(value.get("priority", 0)),
            shadow_days=int(value.get("shadow_days", 7)),
            minimum_shadow_opportunities=int(
                value.get("minimum_shadow_opportunities", 3)
            ),
            minimum_shadow_agreement=float(
                value.get("minimum_shadow_agreement", 0.80)
            ),
            trigger_window_seconds=int(value.get("trigger_window_seconds", 1800)),
            description=str(value.get("description", "")),
        )


@dataclass(frozen=True)
class RoutineSpecV1:
    id: str
    template_id: str
    plugin_id: str
    target_id: str
    entity_ids: tuple[str, ...]
    activation_guard: ScopedConditionV1
    goal_id: str
    recurrence: JsonObject
    cooldown_seconds: int
    priority: int
    status: RoutineStatus = RoutineStatus.SHADOW
    conflict_key: str = ""
    desired_state: JsonObject = field(default_factory=dict)
    profile_id: str | None = None
    manifest_fingerprint: str = ""
    last_triggered_at: str | None = None
    active_occurrence_key: str | None = None
    override_until: str | None = None
    conflict_timestamps: tuple[str, ...] = ()
    status_reason: str = ""
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "routine id"),
            (self.template_id, "routine template id"),
            (self.plugin_id, "routine plugin_id"),
            (self.target_id, "routine target_id"),
            (self.goal_id, "routine goal_id"),
        ):
            _require(value, name)
        if not self.entity_ids:
            raise ContractError("routine requires exact entity ids")
        if any("*" in item or "?" in item or "[" in item for item in self.entity_ids):
            raise ContractError("routine entity ids cannot contain wildcards")
        if self.cooldown_seconds < 0:
            raise ContractError("routine cooldown cannot be negative")
        canonical_data(self.recurrence)
        canonical_data(self.desired_state)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RoutineSpecV1":
        return cls(
            id=str(value["id"]),
            template_id=str(value["template_id"]),
            plugin_id=str(value["plugin_id"]),
            target_id=str(value["target_id"]),
            entity_ids=tuple(str(item) for item in value.get("entity_ids", ())),
            activation_guard=ScopedConditionV1.from_dict(value["activation_guard"]),
            goal_id=str(value["goal_id"]),
            recurrence=dict(value.get("recurrence", {})),
            cooldown_seconds=int(value.get("cooldown_seconds", 0)),
            priority=int(value.get("priority", 0)),
            status=RoutineStatus(str(value.get("status", RoutineStatus.SHADOW.value))),
            conflict_key=str(value.get("conflict_key", "")),
            desired_state=dict(value.get("desired_state", {})),
            profile_id=(str(value["profile_id"]) if value.get("profile_id") is not None else None),
            manifest_fingerprint=str(value.get("manifest_fingerprint", "")),
            last_triggered_at=(str(value["last_triggered_at"]) if value.get("last_triggered_at") is not None else None),
            active_occurrence_key=(str(value["active_occurrence_key"]) if value.get("active_occurrence_key") is not None else None),
            override_until=(str(value["override_until"]) if value.get("override_until") is not None else None),
            conflict_timestamps=tuple(str(item) for item in value.get("conflict_timestamps", ())),
            status_reason=str(value.get("status_reason", "")),
            created_at=str(value.get("created_at", utc_now())),
        )


@dataclass(frozen=True)
class RoutineCandidateV1:
    id: str
    template_id: str
    plugin_id: str
    target_id: str
    entity_ids: tuple[str, ...]
    pattern_value: Any
    context: JsonObject
    evidence_ids: tuple[str, ...]
    example_count: int
    local_days: tuple[str, ...]
    consistency: float
    status: RoutineCandidateStatus
    routine: RoutineSpecV1
    goal: GoalSpecV2
    shadow_started_at: str | None = None
    shadow_ends_at: str | None = None
    explicit_conflict: bool = False
    rollback_patch: JsonObject = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require(self.id, "routine candidate id")
        if self.example_count != len(self.evidence_ids):
            raise ContractError("routine candidate example count must match evidence")
        if not 0 <= self.consistency <= 1:
            raise ContractError("routine candidate consistency must be between 0 and 1")
        canonical_data(self.pattern_value)
        canonical_data(self.context)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RoutineCandidateV1":
        return cls(
            id=str(value["id"]),
            template_id=str(value["template_id"]),
            plugin_id=str(value["plugin_id"]),
            target_id=str(value["target_id"]),
            entity_ids=tuple(str(item) for item in value.get("entity_ids", ())),
            pattern_value=value.get("pattern_value"),
            context=dict(value.get("context", {})),
            evidence_ids=tuple(str(item) for item in value.get("evidence_ids", ())),
            example_count=int(value.get("example_count", 0)),
            local_days=tuple(str(item) for item in value.get("local_days", ())),
            consistency=float(value.get("consistency", 0)),
            status=RoutineCandidateStatus(str(value["status"])),
            routine=RoutineSpecV1.from_dict(value["routine"]),
            goal=GoalSpecV2.from_dict(value["goal"]),
            shadow_started_at=(str(value["shadow_started_at"]) if value.get("shadow_started_at") is not None else None),
            shadow_ends_at=(str(value["shadow_ends_at"]) if value.get("shadow_ends_at") is not None else None),
            explicit_conflict=bool(value.get("explicit_conflict", False)),
            rollback_patch=dict(value.get("rollback_patch", {})),
            created_at=str(value.get("created_at", utc_now())),
        )


@dataclass(frozen=True)
class RoutineShadowEventV1:
    id: str
    candidate_id: str
    opportunity_key: str
    triggered_at: str
    window_ends_at: str
    agreement: bool | None = None
    desired_effect_observed_at: str | None = None
    evidence_ids: tuple[str, ...] = ()
    dispatch_count: int = 0

    def __post_init__(self) -> None:
        _require(self.id, "routine shadow event id")
        _require(self.opportunity_key, "routine shadow opportunity key")
        if self.dispatch_count != 0:
            raise ContractError("routine shadow events cannot record dispatches")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RoutineShadowEventV1":
        return cls(
            id=str(value["id"]),
            candidate_id=str(value["candidate_id"]),
            opportunity_key=str(value["opportunity_key"]),
            triggered_at=str(value["triggered_at"]),
            window_ends_at=str(value["window_ends_at"]),
            agreement=value.get("agreement"),
            desired_effect_observed_at=(str(value["desired_effect_observed_at"]) if value.get("desired_effect_observed_at") is not None else None),
            evidence_ids=tuple(str(item) for item in value.get("evidence_ids", ())),
            dispatch_count=int(value.get("dispatch_count", 0)),
        )


@dataclass(frozen=True)
class AutonomyShadowOutcomeV1:
    """Plugin-neutral scored shadow opportunity. Never records a dispatch."""

    id: str
    enrollment_id: str
    opportunity_key: str
    triggered_at: str
    window_ends_at: str
    trigger_snapshot_id: str
    entity_id: str
    canonical_parameters: JsonObject
    evaluation_id: str
    desired_effect_ids: tuple[str, ...] = ()
    close_snapshot_id: str | None = None
    agreement: bool | None = None
    strict_disagreement: bool = False
    desired_effect_observed_at: str | None = None
    evidence_ids: tuple[str, ...] = ()
    dispatch_count: int = 0

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "autonomy shadow outcome id"),
            (self.enrollment_id, "autonomy shadow enrollment_id"),
            (self.opportunity_key, "autonomy shadow opportunity_key"),
            (self.trigger_snapshot_id, "autonomy shadow trigger_snapshot_id"),
            (self.entity_id, "autonomy shadow entity_id"),
            (self.evaluation_id, "autonomy shadow evaluation_id"),
        ):
            _require(value, name)
        if self.dispatch_count != 0:
            raise ContractError("autonomy shadow outcomes cannot record dispatches")
        if self.strict_disagreement and self.agreement is not False:
            raise ContractError("strict disagreement requires agreement=false")
        canonical_data(self.canonical_parameters)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AutonomyShadowOutcomeV1":
        return cls(
            id=str(value["id"]),
            enrollment_id=str(value["enrollment_id"]),
            opportunity_key=str(value["opportunity_key"]),
            triggered_at=str(value["triggered_at"]),
            window_ends_at=str(value["window_ends_at"]),
            trigger_snapshot_id=str(value["trigger_snapshot_id"]),
            entity_id=str(value["entity_id"]),
            canonical_parameters=dict(value.get("canonical_parameters", {})),
            evaluation_id=str(value["evaluation_id"]),
            desired_effect_ids=tuple(
                str(item) for item in value.get("desired_effect_ids", ())
            ),
            close_snapshot_id=(
                str(value["close_snapshot_id"])
                if value.get("close_snapshot_id") is not None
                else None
            ),
            agreement=value.get("agreement"),
            strict_disagreement=bool(value.get("strict_disagreement", False)),
            desired_effect_observed_at=(
                str(value["desired_effect_observed_at"])
                if value.get("desired_effect_observed_at") is not None
                else None
            ),
            evidence_ids=tuple(str(item) for item in value.get("evidence_ids", ())),
            dispatch_count=int(value.get("dispatch_count", 0)),
        )


@dataclass(frozen=True)
class AutonomyStrategySpecV1:
    """Static declaration for a single-pass, proposal-only strategy."""

    id: str
    plugin_id: str
    version: str
    cognition_route: CognitionRouteV1
    capability_families: tuple[str, ...] = ()
    goal_template_ids: tuple[str, ...] = ()
    context_plugin_ids: tuple[str, ...] = ()
    privacy_classes: tuple[PrivacyClass, ...] = ()
    specialist_id: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "autonomy strategy id"),
            (self.plugin_id, "autonomy strategy plugin_id"),
            (self.version, "autonomy strategy version"),
        ):
            _require(value, name)
        if self.cognition_route is CognitionRouteV1.SPECIALIST and not self.specialist_id:
            raise ContractError("specialist cognition route requires specialist_id")
        scoped = (
            *self.capability_families,
            *self.goal_template_ids,
            *self.context_plugin_ids,
        )
        if any(_has_wildcard(item) for item in scoped):
            raise ContractError("autonomy strategy scope cannot contain wildcards")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AutonomyStrategySpecV1":
        return cls(
            id=str(value["id"]),
            plugin_id=str(value["plugin_id"]),
            version=str(value.get("version", "1.0.0")),
            cognition_route=CognitionRouteV1(
                str(value.get("cognition_route", CognitionRouteV1.DETERMINISTIC.value))
            ),
            capability_families=tuple(
                str(item) for item in value.get("capability_families", ())
            ),
            goal_template_ids=tuple(
                str(item) for item in value.get("goal_template_ids", ())
            ),
            context_plugin_ids=tuple(
                str(item) for item in value.get("context_plugin_ids", ())
            ),
            privacy_classes=tuple(
                PrivacyClass(str(item)) for item in value.get("privacy_classes", ())
            ),
            specialist_id=(
                str(value["specialist_id"])
                if value.get("specialist_id") is not None
                else None
            ),
            description=str(value.get("description", "")),
        )

    @property
    def fingerprint(self) -> str:
        return artifact_sha256(self)


@dataclass(frozen=True)
class GoalTemplateSpecV1:
    """Owner-reviewable schema for creating an executable GoalSpecV2."""

    id: str
    plugin_id: str
    version: str
    mode: GoalModeV2
    capability_families: tuple[str, ...]
    parameter_schema: JsonObject
    goal_schema: JsonObject
    risk_class: RiskClass = RiskClass.LOW
    description: str = ""

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "goal template id"),
            (self.plugin_id, "goal template plugin_id"),
            (self.version, "goal template version"),
        ):
            _require(value, name)
        if not self.capability_families:
            raise ContractError("goal template requires capability families")
        if any(_has_wildcard(item) for item in self.capability_families):
            raise ContractError("goal template capability scope cannot contain wildcards")
        if self.risk_class not in {RiskClass.READ_ONLY, RiskClass.LOW}:
            raise ContractError("v1 goal templates cannot exceed low risk")
        canonical_data(self.parameter_schema)
        canonical_data(self.goal_schema)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GoalTemplateSpecV1":
        return cls(
            id=str(value["id"]),
            plugin_id=str(value["plugin_id"]),
            version=str(value.get("version", "1.0.0")),
            mode=GoalModeV2(str(value.get("mode", GoalModeV2.ACHIEVE.value))),
            capability_families=tuple(
                str(item) for item in value.get("capability_families", ())
            ),
            parameter_schema=dict(value.get("parameter_schema", {})),
            goal_schema=dict(value.get("goal_schema", {})),
            risk_class=RiskClass(str(value.get("risk_class", RiskClass.LOW.value))),
            description=str(value.get("description", "")),
        )

    @property
    def fingerprint(self) -> str:
        return artifact_sha256(self)


@dataclass(frozen=True)
class GoalCandidateV1:
    """Inert request to instantiate one declared goal template."""

    id: str
    plugin_id: str
    template_id: str
    target_id: str
    entity_ids: tuple[str, ...]
    parameters: JsonObject
    based_on_snapshot_id: str
    based_on_world_revision: int
    proposed_by: str
    rationale: str = ""
    evidence_ids: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "goal candidate id"),
            (self.plugin_id, "goal candidate plugin_id"),
            (self.template_id, "goal candidate template_id"),
            (self.target_id, "goal candidate target_id"),
            (self.proposed_by, "goal candidate proposed_by"),
        ):
            _require(value, name)
        if not self.entity_ids or any(_has_wildcard(item) for item in self.entity_ids):
            raise ContractError("goal candidate requires exact entity ids")
        if self.based_on_world_revision < 1:
            raise ContractError("goal candidate world revision must be positive")
        canonical_data(self.parameters)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GoalCandidateV1":
        return cls(
            id=str(value["id"]),
            plugin_id=str(value["plugin_id"]),
            template_id=str(value["template_id"]),
            target_id=str(value["target_id"]),
            entity_ids=tuple(str(item) for item in value.get("entity_ids", ())),
            parameters=dict(value.get("parameters", {})),
            based_on_snapshot_id=str(value["based_on_snapshot_id"]),
            based_on_world_revision=int(value["based_on_world_revision"]),
            proposed_by=str(value["proposed_by"]),
            rationale=str(value.get("rationale", "")),
            evidence_ids=tuple(str(item) for item in value.get("evidence_ids", ())),
            created_at=str(value.get("created_at", utc_now())),
        )


@dataclass(frozen=True)
class AutonomyEnrollmentV2:
    """Immutable, revisioned owner grant; it never authorizes by itself."""

    id: str
    revision: int
    plugin_id: str
    strategy_id: str
    goal_template_ids: tuple[str, ...]
    target_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]
    capability_families: tuple[str, ...]
    context_plugin_ids: tuple[str, ...]
    privacy_grants: tuple[PrivacyClass, ...]
    cognition_route: CognitionRouteV1
    risk_ceiling: RiskClass
    limits: JsonObject
    budget: JsonObject
    expires_at: str
    manifest_fingerprint: str
    strategy_fingerprint: str
    goal_template_fingerprints: JsonObject
    enrolled_at: str
    enrolled_by: str
    control_existing_goals: bool = False
    instantiate_goal_templates: bool = False
    promote_proven_routines: bool = False
    enabled: bool = True
    revoked_at: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "autonomy enrollment id"),
            (self.plugin_id, "autonomy enrollment plugin_id"),
            (self.strategy_id, "autonomy enrollment strategy_id"),
            (self.manifest_fingerprint, "autonomy manifest fingerprint"),
            (self.strategy_fingerprint, "autonomy strategy fingerprint"),
            (self.enrolled_by, "autonomy enrolled_by"),
        ):
            _require(value, name)
        if self.revision < 1:
            raise ContractError("autonomy enrollment revision must be positive")
        if not self.target_ids or not self.entity_ids or not self.capability_families:
            raise ContractError("autonomy enrollment mutation scope cannot be empty")
        scoped = (
            *self.target_ids,
            *self.entity_ids,
            *self.capability_families,
            *self.goal_template_ids,
        )
        if any(_has_wildcard(item) for item in scoped):
            raise ContractError("autonomy enrollment scope cannot contain wildcards")
        if self.risk_ceiling not in {RiskClass.READ_ONLY, RiskClass.LOW}:
            raise ContractError("delegated v1 risk ceiling cannot exceed low")
        if self.instantiate_goal_templates and not self.goal_template_ids:
            raise ContractError("goal-template privilege requires exact templates")
        if self.cognition_route is CognitionRouteV1.SPECIALIST and not self.strategy_id:
            raise ContractError("specialist enrollment requires a strategy")
        canonical_data(self.limits)
        canonical_data(self.budget)
        canonical_data(self.goal_template_fingerprints)
        if set(self.goal_template_fingerprints) != set(self.goal_template_ids):
            raise ContractError(
                "goal template fingerprints must exactly match enrolled templates"
            )
        for values, name in (
            (self.goal_template_ids, "goal template ids"),
            (self.target_ids, "target ids"),
            (self.entity_ids, "entity ids"),
            (self.capability_families, "capability families"),
            (self.context_plugin_ids, "context plugin ids"),
            (self.privacy_grants, "privacy grants"),
        ):
            if len(values) != len(set(values)):
                raise ContractError(f"autonomy enrollment {name} must be unique")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AutonomyEnrollmentV2":
        return cls(
            id=str(value["id"]),
            revision=int(value.get("revision", 1)),
            plugin_id=str(value["plugin_id"]),
            strategy_id=str(value["strategy_id"]),
            goal_template_ids=tuple(str(item) for item in value.get("goal_template_ids", ())),
            target_ids=tuple(str(item) for item in value.get("target_ids", ())),
            entity_ids=tuple(str(item) for item in value.get("entity_ids", ())),
            capability_families=tuple(str(item) for item in value.get("capability_families", ())),
            context_plugin_ids=tuple(str(item) for item in value.get("context_plugin_ids", ())),
            privacy_grants=tuple(PrivacyClass(str(item)) for item in value.get("privacy_grants", ())),
            cognition_route=CognitionRouteV1(str(value.get("cognition_route", "deterministic"))),
            risk_ceiling=RiskClass(str(value.get("risk_ceiling", RiskClass.LOW.value))),
            limits=dict(value.get("limits", {})),
            budget=dict(value.get("budget", {})),
            expires_at=str(value["expires_at"]),
            manifest_fingerprint=str(value["manifest_fingerprint"]),
            strategy_fingerprint=str(value["strategy_fingerprint"]),
            goal_template_fingerprints=dict(value.get("goal_template_fingerprints", {})),
            enrolled_at=str(value["enrolled_at"]),
            enrolled_by=str(value["enrolled_by"]),
            control_existing_goals=bool(value.get("control_existing_goals", False)),
            instantiate_goal_templates=bool(value.get("instantiate_goal_templates", False)),
            promote_proven_routines=bool(value.get("promote_proven_routines", False)),
            enabled=bool(value.get("enabled", True)),
            revoked_at=(str(value["revoked_at"]) if value.get("revoked_at") is not None else None),
        )


@dataclass(frozen=True)
class AutonomyProfileV1:
    id: str
    plugin_id: str
    target_id: str
    entity_ids: tuple[str, ...]
    routine_template_ids: tuple[str, ...]
    capability_families: tuple[str, ...]
    risk_ceiling: RiskClass
    manifest_fingerprint: str
    limits: JsonObject
    activated_at: str
    activated_by: str
    enabled: bool = True
    revoked_at: str | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "autonomy profile id"),
            (self.plugin_id, "autonomy profile plugin_id"),
            (self.target_id, "autonomy profile target_id"),
            (self.manifest_fingerprint, "autonomy manifest fingerprint"),
            (self.activated_by, "autonomy activated_by"),
        ):
            _require(value, name)
        if not self.entity_ids or not self.routine_template_ids or not self.capability_families:
            raise ContractError("autonomy profile scope cannot be empty")
        scoped = (*self.entity_ids, *self.routine_template_ids, *self.capability_families)
        if any("*" in item or "?" in item or "[" in item for item in scoped):
            raise ContractError("autonomy profile scope cannot contain wildcards")
        if self.risk_ceiling not in {RiskClass.READ_ONLY, RiskClass.LOW}:
            raise ContractError("autonomy profile risk ceiling cannot exceed low")
        canonical_data(self.limits)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AutonomyProfileV1":
        return cls(
            id=str(value["id"]),
            plugin_id=str(value["plugin_id"]),
            target_id=str(value["target_id"]),
            entity_ids=tuple(str(item) for item in value.get("entity_ids", ())),
            routine_template_ids=tuple(str(item) for item in value.get("routine_template_ids", ())),
            capability_families=tuple(str(item) for item in value.get("capability_families", ())),
            risk_ceiling=RiskClass(str(value.get("risk_ceiling", RiskClass.LOW.value))),
            manifest_fingerprint=str(value["manifest_fingerprint"]),
            limits=dict(value.get("limits", {})),
            activated_at=str(value["activated_at"]),
            activated_by=str(value["activated_by"]),
            enabled=bool(value.get("enabled", True)),
            revoked_at=(str(value["revoked_at"]) if value.get("revoked_at") is not None else None),
        )


@dataclass(frozen=True)
class StandingMandateV1:
    id: str
    plugin_ids: tuple[str, ...]
    target_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]
    capability_families: tuple[str, ...]
    limits: JsonObject
    privacy_permissions: tuple[str, ...]
    learning_permissions: tuple[str, ...]
    valid_from: str
    valid_until: str
    manifest_versions: JsonObject
    activated_by: str
    revoked: bool = False

    def __post_init__(self) -> None:
        _require(self.id, "mandate id")
        _require(self.activated_by, "activated_by")
        if not self.capability_families:
            raise ContractError("mandate requires at least one capability family")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StandingMandateV1":
        return cls(
            id=str(value["id"]),
            plugin_ids=tuple(str(item) for item in value.get("plugin_ids", ())),
            target_ids=tuple(str(item) for item in value.get("target_ids", ())),
            entity_ids=tuple(str(item) for item in value.get("entity_ids", ())),
            capability_families=tuple(
                str(item) for item in value.get("capability_families", ())
            ),
            limits=dict(value.get("limits", {})),
            privacy_permissions=tuple(
                str(item) for item in value.get("privacy_permissions", ())
            ),
            learning_permissions=tuple(
                str(item) for item in value.get("learning_permissions", ())
            ),
            valid_from=str(value["valid_from"]),
            valid_until=str(value["valid_until"]),
            manifest_versions=dict(value.get("manifest_versions", {})),
            activated_by=str(value["activated_by"]),
            revoked=bool(value.get("revoked", False)),
        )


@dataclass(frozen=True)
class EntityV1:
    id: str
    target_id: str
    entity_type: str
    source: str
    name: str | None = None
    attributes: JsonObject = field(default_factory=dict)
    artifact_identity: str | None = None

    def __post_init__(self) -> None:
        _require(self.id, "entity id")
        _require(self.target_id, "entity target_id")
        _require(self.entity_type, "entity_type")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


@dataclass(frozen=True)
class RelationV1:
    id: str
    relation_type: str
    source_entity_id: str
    target_entity_id: str
    source: str
    observed_at: str
    evidence_grade: EvidenceGrade
    confidence: float | None = None
    attributes: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require(self.id, "relation id")
        if self.source_entity_id == self.target_entity_id:
            raise ContractError("relation endpoints must differ")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ContractError("relation confidence must be between 0 and 1")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


@dataclass(frozen=True)
class ObservationV1:
    id: str
    entity_id: str
    property: str
    value: Any
    source: str
    observed_at: str
    evidence_grade: EvidenceGrade
    unit: str | None = None
    quality: float | None = None
    coverage: str = "point"
    artifact_identity: str | None = None

    def __post_init__(self) -> None:
        _require(self.id, "observation id")
        _require(self.entity_id, "observation entity_id")
        _require(self.property, "observation property")
        if self.quality is not None and not 0 <= self.quality <= 1:
            raise ContractError("observation quality must be between 0 and 1")
        canonical_data(self.value)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


@dataclass(frozen=True)
class TargetObservationV2:
    target_id: str
    revision: int
    observed_at: str
    entities: tuple[EntityV1, ...]
    relations: tuple[RelationV1, ...]
    observations: tuple[ObservationV1, ...]
    coverage: JsonObject
    source: str
    available: bool | None = True
    errors: tuple[str, ...] = ()
    confirmed_at: str | None = None

    def __post_init__(self) -> None:
        _require(self.target_id, "target observation target_id")
        if self.revision < 0:
            raise ContractError("target revision must be non-negative")
        entity_ids = {item.id for item in self.entities}
        if len(entity_ids) != len(self.entities):
            raise ContractError("target observation contains duplicate entity ids")
        if any(item.entity_id not in entity_ids for item in self.observations):
            raise ContractError("observation references an unknown entity")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    def semantic_fingerprint(self) -> str:
        return artifact_sha256(
            {
                "content": _world_content_semantic_data(
                    self.entities, self.relations, self.observations
                ),
                "coverage": self.coverage,
                "source": self.source,
                "available": self.available,
                "errors": self.errors,
            }
        )


@dataclass(frozen=True)
class WorldSnapshotV2:
    id: str
    revision: int
    observed_at: str
    target_revisions: JsonObject
    entities: tuple[EntityV1, ...]
    relations: tuple[RelationV1, ...]
    observations: tuple[ObservationV1, ...]
    coverage: JsonObject

    def __post_init__(self) -> None:
        _require(self.id, "world snapshot id")
        if self.revision < 1:
            raise ContractError("world revision must be positive")
        entity_ids = {item.id for item in self.entities}
        if len(entity_ids) != len(self.entities):
            raise ContractError("world snapshot contains duplicate entity ids")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    def semantic_fingerprint(self) -> str:
        return artifact_sha256(
            _world_content_semantic_data(
                self.entities, self.relations, self.observations
            )
        )

    @property
    def sha256(self) -> str:
        return artifact_sha256(self)


_VOLATILE_METERING_EXACT = frozenset(
    {
        "current",
        "energy_kwh",
        "frequency",
        "house_power_w",
        "measure_current",
        "measure_gas",
        "measure_power",
        "measure_voltage",
        "measure_water",
        "meter_gas",
        "meter_power",
        "meter_water",
        "net_load_phase1_pct",
        "power_w",
        "rssi",
        "voltage",
        "wifi_quality",
    }
)
_VOLATILE_METERING_PREFIXES = (
    "current.",
    "measure_current.",
    "measure_current_",
    "measure_gas.",
    "measure_power.",
    "measure_power_",
    "measure_voltage.",
    "measure_voltage_",
    "measure_water.",
    "meter_gas.",
    "meter_gas_",
    "meter_power.",
    "meter_power_",
    "meter_water.",
    "meter_water_",
    "net_load",
    "power.",
    "voltage.",
    "voltage_",
)


def is_volatile_metering_signal(name: str, value: Any = None) -> bool:
    """True when a watt/kWh/water/gas/rssi tick must not mint house identity."""
    key = name.casefold().strip()
    if key in _VOLATILE_METERING_EXACT:
        return True
    if key.startswith(_VOLATILE_METERING_PREFIXES):
        return True
    if key in {"water", "gas"} and isinstance(value, (int, float)) and type(value) is not bool:
        return True
    return False


def _world_content_semantic_data(
    entities: tuple[EntityV1, ...],
    relations: tuple[RelationV1, ...],
    observations: tuple[ObservationV1, ...],
) -> JsonObject:
    return {
        "entities": [item.to_dict() for item in entities],
        "relations": [
            {
                "id": item.id,
                "relation_type": item.relation_type,
                "source_entity_id": item.source_entity_id,
                "target_entity_id": item.target_entity_id,
                "source": item.source,
                "evidence_grade": item.evidence_grade.value,
                "confidence": item.confidence,
                "attributes": item.attributes,
            }
            for item in relations
        ],
        "observations": [
            {
                "entity_id": item.entity_id,
                "property": item.property,
                "value": item.value,
                "source": item.source,
                "evidence_grade": item.evidence_grade.value,
                "quality": item.quality,
                "coverage": item.coverage,
                "unit": item.unit,
                "artifact_identity": item.artifact_identity,
            }
            for item in observations
            if not is_volatile_metering_signal(item.property, item.value)
        ],
    }


@dataclass(frozen=True)
class CapabilitySpecV2:
    id: str
    plugin_id: str
    family: str
    version: str
    description: str
    input_schema: JsonObject
    effect_schema: JsonObject
    control_layer: ControlLayer
    invocation_mode: InvocationModeV2
    risk_class: RiskClass
    privacy_class: PrivacyClass
    idempotent: bool
    deadline_ms: int
    units: JsonObject = field(default_factory=dict)
    limits: JsonObject = field(default_factory=dict)
    preconditions: tuple[ConditionV1, ...] = ()
    effect_measurements: tuple[str, ...] = ()
    recovery: str = "observe_and_defer"
    opaque: bool = False
    conflict_domain: str = ""

    def __post_init__(self) -> None:
        _require(self.id, "capability id")
        _require(self.family, "capability family")
        if self.deadline_ms <= 0:
            raise ContractError("capability deadline must be positive")
        if self.opaque and self.control_layer is not ControlLayer.QUERY:
            raise ContractError("opaque capabilities must be query-only")
        if self.conflict_domain and _has_wildcard(self.conflict_domain):
            raise ContractError("capability conflict_domain must be an exact identity")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


@dataclass(frozen=True)
class ProposedActionV1:
    id: str
    goal_id: str
    desired_effect_id: str
    capability_family: str
    target_id: str
    entity_id: str
    semantic_parameters: JsonObject
    based_on_snapshot_id: str
    based_on_world_revision: int
    proposed_by: str
    rationale: str = ""
    evidence_ids: tuple[str, ...] = ()
    created_at: str = field(default_factory=utc_now)
    autonomy_binding: AutonomyBindingV1 | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "proposal id"), (self.goal_id, "goal id"),
            (self.capability_family, "capability family"),
            (self.target_id, "target id"), (self.entity_id, "entity id"),
        ):
            _require(value, name)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProposedActionV1":
        return cls(
            id=str(value["id"]),
            goal_id=str(value["goal_id"]),
            desired_effect_id=str(value["desired_effect_id"]),
            capability_family=str(value["capability_family"]),
            target_id=str(value["target_id"]),
            entity_id=str(value["entity_id"]),
            semantic_parameters=dict(value.get("semantic_parameters", {})),
            based_on_snapshot_id=str(value["based_on_snapshot_id"]),
            based_on_world_revision=int(value["based_on_world_revision"]),
            proposed_by=str(value["proposed_by"]),
            rationale=str(value.get("rationale", "")),
            evidence_ids=tuple(str(item) for item in value.get("evidence_ids", ())),
            created_at=str(value.get("created_at", utc_now())),
            autonomy_binding=(
                AutonomyBindingV1.from_dict(value["autonomy_binding"])
                if isinstance(value.get("autonomy_binding"), Mapping)
                else None
            ),
        )


@dataclass(frozen=True)
class ActionRequestV1:
    id: str
    proposal_id: str
    goal_id: str
    plugin_id: str
    target_id: str
    entity_id: str
    capability_id: str
    capability_family: str
    parameters: JsonObject
    snapshot_id: str
    world_revision: int
    target_revision: int
    preconditions: tuple[ConditionV1, ...]
    idempotency_key: str | None
    deadline_at: str
    invocation_mode: InvocationModeV2 = InvocationModeV2.IMMEDIATE
    autonomy_binding: AutonomyBindingV1 | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "request id"), (self.proposal_id, "proposal id"),
            (self.target_id, "target id"), (self.entity_id, "entity id"),
            (self.capability_id, "capability id"),
        ):
            _require(value, name)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ActionRequestV1":
        return cls(
            id=str(value["id"]),
            proposal_id=str(value["proposal_id"]),
            goal_id=str(value["goal_id"]),
            plugin_id=str(value["plugin_id"]),
            target_id=str(value["target_id"]),
            entity_id=str(value["entity_id"]),
            capability_id=str(value["capability_id"]),
            capability_family=str(value["capability_family"]),
            parameters=dict(value.get("parameters", {})),
            snapshot_id=str(value["snapshot_id"]),
            world_revision=int(value["world_revision"]),
            target_revision=int(value["target_revision"]),
            preconditions=tuple(
                ConditionV1.from_dict(item) for item in value.get("preconditions", ())
            ),
            idempotency_key=(
                str(value["idempotency_key"])
                if value.get("idempotency_key") is not None
                else None
            ),
            deadline_at=str(value["deadline_at"]),
            invocation_mode=InvocationModeV2(
                str(value.get("invocation_mode", InvocationModeV2.IMMEDIATE.value))
            ),
            autonomy_binding=(
                AutonomyBindingV1.from_dict(value["autonomy_binding"])
                if isinstance(value.get("autonomy_binding"), Mapping)
                else None
            ),
        )

    @property
    def sha256(self) -> str:
        return artifact_sha256(self)


@dataclass(frozen=True)
class PolicyDecisionV1:
    id: str
    request_id: str
    outcome: PolicyOutcome
    reasons: tuple[str, ...]
    policy_version: str
    mandate_id: str | None
    decided_at: str = field(default_factory=utc_now)
    autonomy_binding: AutonomyBindingV1 | None = None

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PolicyDecisionV1":
        return cls(
            id=str(value["id"]),
            request_id=str(value["request_id"]),
            outcome=PolicyOutcome(str(value["outcome"])),
            reasons=tuple(str(item) for item in value.get("reasons", ())),
            policy_version=str(value["policy_version"]),
            mandate_id=(str(value["mandate_id"]) if value.get("mandate_id") is not None else None),
            decided_at=str(value.get("decided_at", utc_now())),
            autonomy_binding=(
                AutonomyBindingV1.from_dict(value["autonomy_binding"])
                if isinstance(value.get("autonomy_binding"), Mapping)
                else None
            ),
        )


@dataclass(frozen=True)
class AuthorizationV1:
    id: str
    request_id: str
    request_sha256: str
    policy_decision_id: str
    mandate_id: str
    target_id: str
    entity_id: str
    capability_id: str
    parameter_limits: JsonObject
    snapshot_id: str
    issued_at: str
    expires_at: str
    issued_by: str = "engine.policy/v2"
    autonomy_binding: AutonomyBindingV1 | None = None

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AuthorizationV1":
        return cls(
            id=str(value["id"]),
            request_id=str(value["request_id"]),
            request_sha256=str(value["request_sha256"]),
            policy_decision_id=str(value["policy_decision_id"]),
            mandate_id=str(value["mandate_id"]),
            target_id=str(value["target_id"]),
            entity_id=str(value["entity_id"]),
            capability_id=str(value["capability_id"]),
            parameter_limits=dict(value.get("parameter_limits", {})),
            snapshot_id=str(value["snapshot_id"]),
            issued_at=str(value["issued_at"]),
            expires_at=str(value["expires_at"]),
            issued_by=str(value.get("issued_by", "engine.policy/v2")),
            autonomy_binding=(
                AutonomyBindingV1.from_dict(value["autonomy_binding"])
                if isinstance(value.get("autonomy_binding"), Mapping)
                else None
            ),
        )


@dataclass(frozen=True)
class ExecutionReceiptV2:
    id: str
    request_id: str
    authorization_id: str
    target_id: str
    capability_id: str
    state: ExecutionStateV2
    requested_at: str
    completed_at: str | None
    acknowledged: bool | None
    result: JsonObject = field(default_factory=dict)
    error: str | None = None
    external_handle: str | None = None
    adapter_version: str = ""

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExecutionReceiptV2":
        return cls(
            id=str(value["id"]),
            request_id=str(value["request_id"]),
            authorization_id=str(value["authorization_id"]),
            target_id=str(value["target_id"]),
            capability_id=str(value["capability_id"]),
            state=ExecutionStateV2(str(value["state"])),
            requested_at=str(value["requested_at"]),
            completed_at=(
                str(value["completed_at"])
                if value.get("completed_at") is not None
                else None
            ),
            acknowledged=value.get("acknowledged"),
            result=dict(value.get("result", {})),
            error=str(value["error"]) if value.get("error") is not None else None,
            external_handle=(
                str(value["external_handle"])
                if value.get("external_handle") is not None
                else None
            ),
            adapter_version=str(value.get("adapter_version", "")),
        )


@dataclass(frozen=True)
class EffectDeltaV1:
    id: str
    goal_id: str
    proposal_id: str
    request_id: str
    receipt_id: str
    pre_snapshot_id: str
    post_snapshot_id: str
    evidence_grade: EvidenceGrade
    achieved: bool | None
    changes: JsonObject
    measurement_observation_ids: tuple[str, ...]
    reason: str
    observed_at: str

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


@dataclass(frozen=True)
class RelationHypothesisV1:
    id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    proposed_by: str
    based_on_observation_ids: tuple[str, ...]
    confidence: float
    created_at: str = field(default_factory=utc_now)
    evidence_grade: EvidenceGrade = EvidenceGrade.INFERRED

    def __post_init__(self) -> None:
        if self.evidence_grade is not EvidenceGrade.INFERRED:
            raise ContractError("relation hypotheses must remain INFERRED")
        if not 0 <= self.confidence <= 1:
            raise ContractError("hypothesis confidence must be between 0 and 1")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


@dataclass(frozen=True)
class BrainDecisionV2:
    kind: DecisionKindV2
    proposed_action: ProposedActionV1 | None = None
    specialist_id: str | None = None
    query: JsonObject = field(default_factory=dict)
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.kind is DecisionKindV2.PROPOSE_EFFECT and self.proposed_action is None:
            raise ContractError("PROPOSE_EFFECT requires a proposed action")
        if self.kind is DecisionKindV2.CONSULT_SPECIALIST and not self.specialist_id:
            raise ContractError("CONSULT_SPECIALIST requires specialist_id")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


@dataclass(frozen=True)
class SpecialistAdviceV1:
    specialist_id: str
    supported: bool
    proposed_action: ProposedActionV1 | None
    summary: str
    metadata: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


@dataclass(frozen=True)
class CognitionRequestV1:
    route: CognitionRouteV1
    goal_id: str
    query: JsonObject = field(default_factory=dict)
    specialist_id: str | None = None
    purpose: str = "autonomy_evaluation"

    def __post_init__(self) -> None:
        _require(self.goal_id, "cognition request goal_id")
        if self.route not in {CognitionRouteV1.EXECUTIVE, CognitionRouteV1.SPECIALIST}:
            raise ContractError("cognition request must select executive or specialist")
        if self.route is CognitionRouteV1.SPECIALIST and not self.specialist_id:
            raise ContractError("specialist cognition request requires specialist_id")
        canonical_data(self.query)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CognitionRequestV1":
        return cls(
            route=CognitionRouteV1(str(value["route"])),
            goal_id=str(value["goal_id"]),
            query=dict(value.get("query", {})),
            specialist_id=(str(value["specialist_id"]) if value.get("specialist_id") is not None else None),
            purpose=str(value.get("purpose", "autonomy_evaluation")),
        )


@dataclass(frozen=True)
class AutonomyDecisionV1:
    kind: AutonomyDecisionKindV1
    proposed_action: ProposedActionV1 | None = None
    goal_candidate: GoalCandidateV1 | None = None
    cognition_request: CognitionRequestV1 | None = None
    rationale: str = ""
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        payload_count = sum(
            item is not None
            for item in (self.proposed_action, self.goal_candidate, self.cognition_request)
        )
        if self.kind is AutonomyDecisionKindV1.PROPOSE_EFFECT:
            if self.proposed_action is None or payload_count != 1:
                raise ContractError("PROPOSE_EFFECT requires only proposed_action")
        elif self.kind is AutonomyDecisionKindV1.PROPOSE_GOAL_CANDIDATE:
            if self.goal_candidate is None or payload_count != 1:
                raise ContractError("PROPOSE_GOAL_CANDIDATE requires only goal_candidate")
        elif self.kind in {
            AutonomyDecisionKindV1.REQUEST_EXECUTIVE,
            AutonomyDecisionKindV1.REQUEST_SPECIALIST,
        }:
            if self.cognition_request is None or payload_count != 1:
                raise ContractError(f"{self.kind.value} requires only cognition_request")
            expected = (
                CognitionRouteV1.EXECUTIVE
                if self.kind is AutonomyDecisionKindV1.REQUEST_EXECUTIVE
                else CognitionRouteV1.SPECIALIST
            )
            if self.cognition_request.route is not expected:
                raise ContractError("cognition request route differs from decision kind")
        elif payload_count:
            raise ContractError(f"{self.kind.value} cannot carry an operational payload")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AutonomyDecisionV1":
        return cls(
            kind=AutonomyDecisionKindV1(str(value["kind"])),
            proposed_action=(
                ProposedActionV1.from_dict(value["proposed_action"])
                if isinstance(value.get("proposed_action"), Mapping)
                else None
            ),
            goal_candidate=(
                GoalCandidateV1.from_dict(value["goal_candidate"])
                if isinstance(value.get("goal_candidate"), Mapping)
                else None
            ),
            cognition_request=(
                CognitionRequestV1.from_dict(value["cognition_request"])
                if isinstance(value.get("cognition_request"), Mapping)
                else None
            ),
            rationale=str(value.get("rationale", "")),
            evidence_ids=tuple(str(item) for item in value.get("evidence_ids", ())),
        )


@dataclass(frozen=True)
class AutonomyContextV1:
    enrollment_id: str
    enrollment_revision: int
    mode: AutonomyModeV1
    mode_epoch: int
    previous_snapshot_id: str | None
    current_snapshot_id: str
    current_world_revision: int
    projection: JsonObject
    projection_sha256: str
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require(self.enrollment_id, "autonomy context enrollment_id")
        _require(self.current_snapshot_id, "autonomy context snapshot_id")
        _require(self.projection_sha256, "autonomy context projection fingerprint")
        if self.enrollment_revision < 1 or self.mode_epoch < 1:
            raise ContractError("autonomy context revisions must be positive")
        if artifact_sha256(self.projection) != self.projection_sha256:
            raise ContractError("autonomy context projection fingerprint mismatch")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AutonomyContextV1":
        return cls(
            enrollment_id=str(value["enrollment_id"]),
            enrollment_revision=int(value["enrollment_revision"]),
            mode=AutonomyModeV1(str(value["mode"])),
            mode_epoch=int(value["mode_epoch"]),
            previous_snapshot_id=(str(value["previous_snapshot_id"]) if value.get("previous_snapshot_id") is not None else None),
            current_snapshot_id=str(value["current_snapshot_id"]),
            current_world_revision=int(value["current_world_revision"]),
            projection=dict(value.get("projection", {})),
            projection_sha256=str(value["projection_sha256"]),
            created_at=str(value.get("created_at", utc_now())),
        )


@dataclass(frozen=True)
class AutonomyEvaluationV1:
    id: str
    enrollment_id: str
    enrollment_revision: int
    strategy_id: str
    mode: AutonomyModeV1
    mode_epoch: int
    context: AutonomyContextV1
    decision: AutonomyDecisionV1
    strategy_fingerprint: str
    manifest_fingerprint: str
    cognition_calls: int = 0
    status: str = "evaluated"
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "autonomy evaluation id"),
            (self.enrollment_id, "autonomy evaluation enrollment_id"),
            (self.strategy_id, "autonomy evaluation strategy_id"),
            (self.strategy_fingerprint, "autonomy evaluation strategy fingerprint"),
            (self.manifest_fingerprint, "autonomy evaluation manifest fingerprint"),
        ):
            _require(value, name)
        if self.cognition_calls not in {0, 1}:
            raise ContractError("autonomy evaluation permits at most one cognition call")
        if self.context.enrollment_id != self.enrollment_id:
            raise ContractError("autonomy evaluation context enrollment mismatch")
        if self.context.mode_epoch != self.mode_epoch:
            raise ContractError("autonomy evaluation context mode epoch mismatch")
        if self.context.mode is not self.mode:
            raise ContractError("autonomy evaluation context mode mismatch")
        if self.context.enrollment_revision != self.enrollment_revision:
            raise ContractError("autonomy evaluation context revision mismatch")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AutonomyEvaluationV1":
        return cls(
            id=str(value["id"]),
            enrollment_id=str(value["enrollment_id"]),
            enrollment_revision=int(value["enrollment_revision"]),
            strategy_id=str(value["strategy_id"]),
            mode=AutonomyModeV1(str(value["mode"])),
            mode_epoch=int(value["mode_epoch"]),
            context=AutonomyContextV1.from_dict(value["context"]),
            decision=AutonomyDecisionV1.from_dict(value["decision"]),
            strategy_fingerprint=str(value["strategy_fingerprint"]),
            manifest_fingerprint=str(value["manifest_fingerprint"]),
            cognition_calls=int(value.get("cognition_calls", 0)),
            status=str(value.get("status", "evaluated")),
            created_at=str(value.get("created_at", utc_now())),
        )


@dataclass(frozen=True)
class EvidenceRefV1:
    evidence_id: str
    entity_id: str
    property: str
    source: str
    observed_at: str
    evidence_grade: EvidenceGrade
    snapshot_id: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.evidence_id, "evidence ref id"),
            (self.entity_id, "evidence ref entity_id"),
            (self.property, "evidence ref property"),
            (self.source, "evidence ref source"),
            (self.snapshot_id, "evidence ref snapshot_id"),
        ):
            _require(value, name)
        if self.evidence_grade not in {EvidenceGrade.OBSERVED, EvidenceGrade.DERIVED}:
            raise ContractError("evidence refs must be OBSERVED or DERIVED")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceRefV1":
        return cls(
            evidence_id=str(value["evidence_id"]),
            entity_id=str(value["entity_id"]),
            property=str(value["property"]),
            source=str(value["source"]),
            observed_at=str(value["observed_at"]),
            evidence_grade=EvidenceGrade(str(value["evidence_grade"])),
            snapshot_id=str(value["snapshot_id"]),
        )


@dataclass(frozen=True)
class AutonomyBindingV1:
    enrollment_id: str
    enrollment_revision: int
    evaluation_id: str
    mode: AutonomyModeV1
    mode_epoch: int
    manifest_fingerprint: str
    strategy_fingerprint: str
    context_fingerprint: str
    evidence_refs: tuple[EvidenceRefV1, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.enrollment_id, "autonomy binding enrollment_id"),
            (self.evaluation_id, "autonomy binding evaluation_id"),
            (self.manifest_fingerprint, "autonomy binding manifest fingerprint"),
            (self.strategy_fingerprint, "autonomy binding strategy fingerprint"),
            (self.context_fingerprint, "autonomy binding context fingerprint"),
        ):
            _require(value, name)
        if self.enrollment_revision < 1 or self.mode_epoch < 1:
            raise ContractError("autonomy binding revisions must be positive")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AutonomyBindingV1":
        return cls(
            enrollment_id=str(value["enrollment_id"]),
            enrollment_revision=int(value["enrollment_revision"]),
            evaluation_id=str(value["evaluation_id"]),
            mode=AutonomyModeV1(str(value["mode"])),
            mode_epoch=int(value["mode_epoch"]),
            manifest_fingerprint=str(value["manifest_fingerprint"]),
            strategy_fingerprint=str(value["strategy_fingerprint"]),
            context_fingerprint=str(value["context_fingerprint"]),
            evidence_refs=tuple(
                EvidenceRefV1.from_dict(item)
                for item in value.get("evidence_refs", ())
            ),
        )


@dataclass(frozen=True)
class SuggestionV1:
    """Non-operational model suggestion; no GoalSpec or mandate is implied."""

    id: str
    source: str
    text: str
    based_on_snapshot_id: str
    metadata: JsonObject = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require(self.id, "suggestion id")
        _require(self.source, "suggestion source")
        _require(self.text, "suggestion text")
        _require(self.based_on_snapshot_id, "suggestion snapshot_id")
        canonical_data(self.metadata)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SuggestionV1":
        return cls(
            id=str(value["id"]), source=str(value["source"]), text=str(value["text"]),
            based_on_snapshot_id=str(value["based_on_snapshot_id"]),
            metadata=dict(value.get("metadata", {})),
            created_at=str(value.get("created_at", utc_now())),
        )


@dataclass(frozen=True)
class DispatchAttemptV1:
    id: str
    operation_key: str
    request_id: str
    authorization_id: str
    target_id: str
    entity_id: str
    conflict_domain: str
    state: DispatchAttemptStateV1
    prepared_at: str
    autonomy_binding: AutonomyBindingV1 | None = None
    lease_fencing_token: str = "embedded"
    receipt_id: str | None = None
    effect_id: str | None = None
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "dispatch attempt id"),
            (self.operation_key, "dispatch operation key"),
            (self.request_id, "dispatch request id"),
            (self.authorization_id, "dispatch authorization id"),
            (self.target_id, "dispatch target id"),
            (self.entity_id, "dispatch entity id"),
            (self.conflict_domain, "dispatch conflict domain"),
            (self.lease_fencing_token, "dispatch lease fencing token"),
        ):
            _require(value, name)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DispatchAttemptV1":
        return cls(
            id=str(value["id"]), operation_key=str(value["operation_key"]),
            request_id=str(value["request_id"]), authorization_id=str(value["authorization_id"]),
            target_id=str(value["target_id"]), entity_id=str(value["entity_id"]),
            conflict_domain=str(value["conflict_domain"]),
            state=DispatchAttemptStateV1(str(value["state"])),
            prepared_at=str(value["prepared_at"]),
            autonomy_binding=(AutonomyBindingV1.from_dict(value["autonomy_binding"]) if isinstance(value.get("autonomy_binding"), Mapping) else None),
            lease_fencing_token=str(value.get("lease_fencing_token", "embedded")),
            receipt_id=(str(value["receipt_id"]) if value.get("receipt_id") is not None else None),
            effect_id=(str(value["effect_id"]) if value.get("effect_id") is not None else None),
            updated_at=str(value.get("updated_at", utc_now())),
        )


@dataclass(frozen=True)
class PreferenceEvidenceV1:
    id: str
    goal_id: str
    grade: EvidenceGrade
    source: str
    field_path: str
    old_value: Any
    new_value: Any
    context: JsonObject
    observed_at: str
    explicit_conflict: bool = False
    signal_id: str | None = None
    plugin_id: str | None = None
    target_id: str | None = None
    entity_id: str | None = None
    capability_family: str | None = None
    preference_id: str | None = None

    def __post_init__(self) -> None:
        if self.grade not in {EvidenceGrade.OBSERVED, EvidenceGrade.INFERRED}:
            raise ContractError("preference evidence must be OBSERVED or INFERRED")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


@dataclass(frozen=True)
class LearningCandidateV1:
    id: str
    goal_id: str
    field_path: str
    old_value: Any
    new_value: Any
    evidence_ids: tuple[str, ...]
    status: LearningStatus
    shadow_started_at: str | None = None
    shadow_ends_at: str | None = None
    shadow_outcomes: tuple[JsonObject, ...] = ()
    rollback_patch: JsonObject = field(default_factory=dict)
    preference_id: str | None = None
    plugin_id: str | None = None
    target_id: str | None = None
    entity_id: str | None = None
    capability_family: str | None = None
    promoted_goal_version: int | None = None

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LearningCandidateV1":
        return cls(
            id=str(value["id"]),
            goal_id=str(value["goal_id"]),
            field_path=str(value["field_path"]),
            old_value=value.get("old_value"),
            new_value=value.get("new_value"),
            evidence_ids=tuple(str(item) for item in value.get("evidence_ids", ())),
            status=LearningStatus(str(value["status"])),
            shadow_started_at=(
                str(value["shadow_started_at"])
                if value.get("shadow_started_at") is not None else None
            ),
            shadow_ends_at=(
                str(value["shadow_ends_at"])
                if value.get("shadow_ends_at") is not None else None
            ),
            shadow_outcomes=tuple(dict(item) for item in value.get("shadow_outcomes", ())),
            rollback_patch=dict(value.get("rollback_patch", {})),
            preference_id=(
                str(value["preference_id"])
                if value.get("preference_id") is not None else None
            ),
            plugin_id=(str(value["plugin_id"]) if value.get("plugin_id") is not None else None),
            target_id=(str(value["target_id"]) if value.get("target_id") is not None else None),
            entity_id=(str(value["entity_id"]) if value.get("entity_id") is not None else None),
            capability_family=(
                str(value["capability_family"])
                if value.get("capability_family") is not None else None
            ),
            promoted_goal_version=(
                int(value["promoted_goal_version"])
                if value.get("promoted_goal_version") is not None else None
            ),
        )


@dataclass(frozen=True)
class PreferenceSpecV1:
    id: str
    plugin_id: str
    capability_family: str
    value_schema: JsonObject
    unit: str | None = None
    promotion_mode: PreferencePromotionMode = PreferencePromotionMode.EXPLICIT_ONLY
    description: str = ""

    def __post_init__(self) -> None:
        _require(self.id, "preference id")
        _require(self.plugin_id, "preference plugin_id")
        _require(self.capability_family, "preference capability_family")
        if not self.id.startswith(self.plugin_id + ".preference."):
            raise ContractError("preference id must be namespaced below plugin_id.preference")
        canonical_data(self.value_schema)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PreferenceSpecV1":
        return cls(
            id=str(value["id"]),
            plugin_id=str(value["plugin_id"]),
            capability_family=str(value["capability_family"]),
            value_schema=dict(value.get("value_schema", {})),
            unit=str(value["unit"]) if value.get("unit") is not None else None,
            promotion_mode=PreferencePromotionMode(
                str(value.get("promotion_mode", PreferencePromotionMode.EXPLICIT_ONLY.value))
            ),
            description=str(value.get("description", "")),
        )


@dataclass(frozen=True)
class BehaviorSignalV1:
    id: str
    plugin_id: str
    target_id: str
    entity_id: str
    capability_family: str
    preference_id: str
    old_value: Any
    new_value: Any
    context: JsonObject
    observed_at: str
    provenance: JsonObject
    evidence_grade: EvidenceGrade = EvidenceGrade.INFERRED
    routine_template_id: str | None = None
    pattern_value: Any = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.id, "behavior signal id"),
            (self.plugin_id, "behavior signal plugin_id"),
            (self.target_id, "behavior signal target_id"),
            (self.entity_id, "behavior signal entity_id"),
            (self.capability_family, "behavior signal capability_family"),
            (self.preference_id, "behavior signal preference_id"),
            (self.observed_at, "behavior signal observed_at"),
        ):
            _require(value, name)
        if self.evidence_grade not in {EvidenceGrade.OBSERVED, EvidenceGrade.INFERRED}:
            raise ContractError("behavior signals must be OBSERVED or INFERRED")
        canonical_data(self.old_value)
        canonical_data(self.new_value)
        canonical_data(self.context)
        canonical_data(self.provenance)
        canonical_data(self.pattern_value)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BehaviorSignalV1":
        return cls(
            id=str(value["id"]),
            plugin_id=str(value["plugin_id"]),
            target_id=str(value["target_id"]),
            entity_id=str(value["entity_id"]),
            capability_family=str(value["capability_family"]),
            preference_id=str(value["preference_id"]),
            old_value=value.get("old_value"),
            new_value=value.get("new_value"),
            context=dict(value.get("context", {})),
            observed_at=str(value["observed_at"]),
            provenance=dict(value.get("provenance", {})),
            evidence_grade=EvidenceGrade(str(value.get("evidence_grade", "INFERRED"))),
            routine_template_id=(
                str(value["routine_template_id"])
                if value.get("routine_template_id") is not None else None
            ),
            pattern_value=value.get("pattern_value"),
        )


@dataclass(frozen=True)
class BehaviorBatchV1:
    cursor: str
    signals: tuple[BehaviorSignalV1, ...]
    has_more: bool = False

    def __post_init__(self) -> None:
        _require(self.cursor, "behavior batch cursor")
        ids = [item.id for item in self.signals]
        if len(ids) != len(set(ids)):
            raise ContractError("behavior batch contains duplicate signal ids")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BehaviorBatchV1":
        return cls(
            cursor=str(value["cursor"]),
            signals=tuple(
                BehaviorSignalV1.from_dict(item) for item in value.get("signals", ())
            ),
            has_more=bool(value.get("has_more", False)),
        )


@dataclass(frozen=True)
class LifecycleEventV1:
    sequence: int
    kind: str
    source: str
    payload: JsonObject
    created_at: str
    goal_id: str | None = None

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ContractError("lifecycle event sequence must be positive")
        _require(self.kind, "lifecycle event kind")
        _require(self.source, "lifecycle event source")
        _require(self.created_at, "lifecycle event created_at")
        canonical_data(self.payload)

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LifecycleEventV1":
        return cls(
            sequence=int(value["sequence"]),
            kind=str(value["kind"]),
            source=str(value["source"]),
            payload=dict(value.get("payload", {})),
            created_at=str(value["created_at"]),
            goal_id=(
                str(value["goal_id"]) if value.get("goal_id") is not None else None
            ),
        )


@dataclass(frozen=True)
class PluginManifestV2:
    id: str
    version: str
    engine_api: str
    description: str
    world_providers: tuple[str, ...]
    controllers: tuple[str, ...]
    executors: tuple[str, ...]
    effect_oracles: tuple[str, ...]
    specialists: tuple[str, ...]
    entity_types: tuple[str, ...]
    relation_types: tuple[str, ...]
    observation_types: tuple[str, ...]
    capabilities: tuple[CapabilitySpecV2, ...]
    lifecycle_observers: tuple[str, ...] = ()
    experience_providers: tuple[str, ...] = ()
    preference_specs: tuple[PreferenceSpecV1, ...] = ()
    routine_compilers: tuple[str, ...] = ()
    routine_templates: tuple[RoutineTemplateSpecV1, ...] = ()
    autonomy_strategies: tuple[AutonomyStrategySpecV1, ...] = ()
    goal_template_compilers: tuple[str, ...] = ()
    goal_templates: tuple[GoalTemplateSpecV1, ...] = ()
    network_needs: tuple[str, ...] = ()
    filesystem_needs: tuple[str, ...] = ()
    secret_needs: tuple[str, ...] = ()
    privacy_needs: tuple[str, ...] = ()
    store_identity: str = ""
    store_schema_version: int = 1
    contract_version: str = "engine.plugin/v2"
    observation_privacy: tuple["ObservationPrivacyRuleV1", ...] = ()

    def __post_init__(self) -> None:
        _require(self.id, "plugin id")
        _require(self.version, "plugin version")
        if self.contract_version not in SUPPORTED_PLUGIN_CONTRACT_VERSIONS:
            raise ContractError(
                "expected one of "
                f"{', '.join(SUPPORTED_PLUGIN_CONTRACT_VERSIONS)}, got {self.contract_version}"
            )
        families = [item.family for item in self.capabilities]
        if len(families) != len(set(families)):
            raise ContractError("capability families must be unique per plugin")
        preference_ids = [item.id for item in self.preference_specs]
        if len(preference_ids) != len(set(preference_ids)):
            raise ContractError("preference ids must be unique per plugin")
        routine_ids = [item.id for item in self.routine_templates]
        if len(routine_ids) != len(set(routine_ids)):
            raise ContractError("routine template ids must be unique per plugin")
        strategy_ids = [item.id for item in self.autonomy_strategies]
        if len(strategy_ids) != len(set(strategy_ids)):
            raise ContractError("autonomy strategy ids must be unique per plugin")
        goal_template_ids = [item.id for item in self.goal_templates]
        if len(goal_template_ids) != len(set(goal_template_ids)):
            raise ContractError("goal template ids must be unique per plugin")

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @property
    def fingerprint(self) -> str:
        return artifact_sha256(self)


@dataclass(frozen=True)
class ObservationPrivacyRuleV1:
    property: str
    privacy_class: PrivacyClass

    def __post_init__(self) -> None:
        _require(self.property, "observation privacy property")

    def matches(self, property_name: str) -> bool:
        if self.property.endswith(".*"):
            return property_name.startswith(self.property[:-1])
        return self.property == property_name

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ObservationPrivacyRuleV1":
        return cls(
            property=str(value["property"]),
            privacy_class=PrivacyClass(str(value["privacy_class"])),
        )


@dataclass(frozen=True)
class PluginManifestV3(PluginManifestV2):
    """Current manifest constructor; PluginManifestV2 retains its v2 default."""

    contract_version: str = PLUGIN_CONTRACT_VERSION
