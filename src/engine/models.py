from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Mapping


JsonObject = dict[str, Any]


class DecisionKind(StrEnum):
    CONSULT_BRAIN = "consult_brain"
    USE_TOOL = "use_tool"
    WAIT = "wait"
    COMPLETE = "complete"
    ABANDON = "abandon"


class GoalMode(StrEnum):
    """Whether a goal is achieved once or kept true over time."""

    ACHIEVE = "achieve"
    MAINTAIN = "maintain"


class Affordance(StrEnum):
    QUERY = "query"
    ACTION = "action"
    EVENT = "event"


class InvocationMode(StrEnum):
    IMMEDIATE = "immediate"
    TASK = "task"
    STREAM = "stream"


class InvocationState(StrEnum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Goal:
    id: str
    target_id: str
    instruction: str
    success_spec: JsonObject
    priority: int = 0
    max_cycles: int = 80
    status: str = "active"
    cycle: int = 0
    mode: GoalMode = GoalMode.ACHIEVE
    intervention_cycle: int = 0


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    local_name: str
    description: str
    input_schema: JsonObject
    output_schema: JsonObject = field(default_factory=dict)
    version: str = "1.0.0"
    affordance: Affordance = Affordance.ACTION
    invocation_mode: InvocationMode = InvocationMode.IMMEDIATE
    idempotent: bool = False
    default_timeout_ms: int = 30_000

    @property
    def name(self) -> str:
        """Compatibility display name; identity always uses the qualified id."""
        return self.id


@dataclass(frozen=True)
class TargetManifest:
    id: str
    description: str
    plugin_id: str = "engine.builtin"
    adapter_version: str = "0.1"
    contract_version: str = "engine.target/v1"


@dataclass(frozen=True)
class BrainManifest:
    name: str
    description: str
    supported_capabilities: tuple[str, ...] = ()
    version: str = "0.1"
    plugin_id: str = "engine.builtin"
    contract_version: str = "engine.brain/v1"
    id: str = ""

    @property
    def qualified_id(self) -> str:
        if self.id:
            return self.id
        return f"{self.plugin_id}.{self.name}/v1"

    def to_dict(self) -> JsonObject:
        value = asdict(self)
        value["id"] = self.qualified_id
        return value


@dataclass(frozen=True)
class PluginManifest:
    id: str
    description: str
    version: str = "0.1.0"
    contract_version: str = "engine.plugin/v1"


@dataclass(frozen=True)
class WorldSnapshot:
    target_id: str
    revision: int
    state: JsonObject
    observed_at: str

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True)
class ToolCall:
    capability_id: str
    arguments: JsonObject
    target_id: str | None = None

    @property
    def capability(self) -> str:
        """Compatibility alias for early adapters; do not persist it as identity."""
        return self.capability_id

    def to_dict(self) -> JsonObject:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ToolCall:
        return cls(
            capability_id=str(value.get("capability_id", value.get("capability"))),
            arguments=dict(value.get("arguments", {})),
            target_id=(
                str(value["target_id"]) if value.get("target_id") is not None else None
            ),
        )


@dataclass(frozen=True)
class ToolResult:
    succeeded: bool
    changed: bool
    output: JsonObject = field(default_factory=dict)
    error: str | None = None
    partial: bool = False

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True)
class InvocationReceipt:
    id: str
    goal_id: str
    target_id: str
    capability_id: str
    state: InvocationState
    requested_at: str
    snapshot_revision: int
    decision_request_id: str
    based_on: tuple[str, ...] = ()
    result: ToolResult | None = None
    external_handle: str | None = None

    def to_dict(self) -> JsonObject:
        value = asdict(self)
        value["state"] = self.state.value
        return value


@dataclass(frozen=True)
class BrainDecision:
    kind: DecisionKind
    name: str | None = None
    arguments: JsonObject = field(default_factory=dict)
    rationale: str = ""
    based_on: tuple[str, ...] = ()

    def to_dict(self) -> JsonObject:
        value = asdict(self)
        value["kind"] = self.kind.value
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BrainDecision:
        return cls(
            kind=DecisionKind(str(value["kind"])),
            name=str(value["name"]) if value.get("name") is not None else None,
            arguments=dict(value.get("arguments", {})),
            rationale=str(value.get("rationale", "")),
            based_on=tuple(str(item) for item in value.get("based_on", ())),
        )


@dataclass(frozen=True)
class BrainRequest:
    id: str
    goal_id: str
    brain_id: str
    brain_version: str
    purpose: str
    snapshot_revision: int
    input_sha256: str
    input_projection: JsonObject
    parent_request_id: str | None = None

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True)
class BrainResult:
    request_id: str
    brain_id: str
    status: str
    output_sha256: str
    latency_ms: float
    output: JsonObject
    usage: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True)
class SpecialistAdvice:
    summary: str
    suggested_action: ToolCall | None = None
    complete: bool = False
    metadata: JsonObject = field(default_factory=dict)

    def to_dict(self) -> JsonObject:
        return {
            "summary": self.summary,
            "suggested_action": (
                self.suggested_action.to_dict() if self.suggested_action else None
            ),
            "complete": self.complete,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SpecialistAdvice:
        raw_action = value.get("suggested_action")
        return cls(
            summary=str(value.get("summary", "")),
            suggested_action=(
                ToolCall.from_dict(raw_action) if isinstance(raw_action, Mapping) else None
            ),
            complete=bool(value.get("complete", False)),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True)
class ExperienceEvent:
    id: int
    goal_id: str
    cycle: int
    kind: str
    source: str
    payload: JsonObject
    created_at: str


@dataclass(frozen=True)
class BrainContext:
    goal: Goal
    snapshot: WorldSnapshot
    capabilities: tuple[CapabilitySpec, ...]
    specialists: tuple[BrainManifest, ...]
    recent_experience: tuple[ExperienceEvent, ...]
    working_memory: JsonObject
    specialist_performance: JsonObject = field(default_factory=dict)
    catalog_generation: int = 0
    catalog_fingerprint: str = ""
    specialist_query: JsonObject = field(default_factory=dict)
    cognitive_phase: str = "needs_specialist"
    pending_advice: tuple[JsonObject, ...] = ()

    def to_payload(self) -> JsonObject:
        return {
            "goal": asdict(self.goal),
            "snapshot": self.snapshot.to_dict(),
            "capabilities": [asdict(item) for item in self.capabilities],
            "specialists": [item.to_dict() for item in self.specialists],
            "recent_experience": [
                self._experience_projection(item) for item in self.recent_experience
            ],
            "working_memory": self.working_memory,
            "specialist_performance": self.specialist_performance,
            "catalog_generation": self.catalog_generation,
            "catalog_fingerprint": self.catalog_fingerprint,
            "specialist_query": self.specialist_query,
            "cognitive_phase": self.cognitive_phase,
            "pending_advice": list(self.pending_advice),
        }

    @staticmethod
    def _experience_projection(event: ExperienceEvent) -> JsonObject:
        payload = dict(event.payload)
        # A brain request stores the exact context it received for audit/replay.
        # Re-injecting that context into later contexts would recurse and grow
        # exponentially, so cognition receives its identity/hash, not the nested copy.
        if event.kind == "brain_request":
            payload.pop("input_projection", None)
        elif event.kind == "brain_result":
            # The semantic decision/advice is booked in executive_decision or
            # specialist_result. Keep provenance and measured usage here without
            # injecting the same output twice.
            payload.pop("output", None)
        elif event.kind == "observation":
            state = payload.pop("state", {})
            payload["state_sha256"] = hashlib.sha256(
                json.dumps(state, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest()
        elif event.kind == "catalog_selection":
            payload["shortlist"] = [
                {
                    "capability_id": item.get("capability_id"),
                    "score": item.get("score"),
                    "reason": item.get("reason"),
                }
                for item in payload.get("shortlist", [])
            ]
        elif event.kind == "invocation":
            result = payload.get("result")
            if isinstance(result, dict):
                payload["result"] = {
                    "succeeded": result.get("succeeded"),
                    "changed": result.get("changed"),
                    "partial": result.get("partial"),
                    "error": result.get("error"),
                }
        return {
            "id": event.id,
            "goal_id": event.goal_id,
            "cycle": event.cycle,
            "kind": event.kind,
            "source": event.source,
            "payload": payload,
            "created_at": event.created_at,
        }
