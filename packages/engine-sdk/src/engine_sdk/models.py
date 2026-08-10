from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Mapping

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, Any]
PLUGIN_CONTRACT_VERSION = "engine.plugin/v2"
ENGINE_API_VERSION = "2.0"


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

    @property
    def sha256(self) -> str:
        return artifact_sha256(self)


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

    def __post_init__(self) -> None:
        _require(self.id, "capability id")
        _require(self.family, "capability family")
        if self.deadline_ms <= 0:
            raise ContractError("capability deadline must be positive")
        if self.opaque and self.control_layer is not ControlLayer.QUERY:
            raise ContractError("opaque capabilities must be query-only")

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

    def to_dict(self) -> JsonObject:
        return canonical_data(self)


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
    experience_providers: tuple[str, ...] = ()
    preference_specs: tuple[PreferenceSpecV1, ...] = ()
    routine_compilers: tuple[str, ...] = ()
    routine_templates: tuple[RoutineTemplateSpecV1, ...] = ()
    network_needs: tuple[str, ...] = ()
    filesystem_needs: tuple[str, ...] = ()
    secret_needs: tuple[str, ...] = ()
    privacy_needs: tuple[str, ...] = ()
    store_identity: str = ""
    store_schema_version: int = 1
    contract_version: str = PLUGIN_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require(self.id, "plugin id")
        _require(self.version, "plugin version")
        if self.contract_version != PLUGIN_CONTRACT_VERSION:
            raise ContractError(
                f"expected {PLUGIN_CONTRACT_VERSION}, got {self.contract_version}"
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

    def to_dict(self) -> JsonObject:
        return canonical_data(self)

    @property
    def fingerprint(self) -> str:
        return artifact_sha256(self)
