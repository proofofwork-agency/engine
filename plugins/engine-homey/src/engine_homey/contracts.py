"""Small legacy-target value types kept local so Homey v2 needs only engine-sdk."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Affordance(StrEnum):
    QUERY = "query"
    ACTION = "action"
    EVENT = "event"


class InvocationMode(StrEnum):
    IMMEDIATE = "immediate"
    TASK = "task"
    STREAM = "stream"


class DecisionKind(StrEnum):
    CONSULT_BRAIN = "consult_brain"
    USE_TOOL = "use_tool"
    WAIT = "wait"
    COMPLETE = "complete"
    ABANDON = "abandon"


@dataclass(frozen=True)
class CapabilitySpec:
    id: str
    local_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    version: str = "1.0.0"
    affordance: Affordance = Affordance.ACTION
    invocation_mode: InvocationMode = InvocationMode.IMMEDIATE
    idempotent: bool = False
    default_timeout_ms: int = 30_000

    @property
    def name(self) -> str:
        return self.id


@dataclass(frozen=True)
class TargetManifest:
    id: str
    description: str
    plugin_id: str = "engine.homey"
    adapter_version: str = "0.2.0"
    contract_version: str = "engine.target/v1"


@dataclass(frozen=True)
class ToolCall:
    capability_id: str
    arguments: dict[str, Any]
    target_id: str | None = None

    @property
    def capability(self) -> str:
        return self.capability_id

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ToolCall:
        return cls(
            capability_id=str(value.get("capability_id", value.get("capability"))),
            arguments=dict(value.get("arguments", {})),
            target_id=(
                str(value["target_id"])
                if value.get("target_id") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class ToolResult:
    succeeded: bool
    changed: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    partial: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorldSnapshot:
    target_id: str
    revision: int
    state: dict[str, Any]
    observed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrainManifest:
    name: str
    description: str
    supported_capabilities: tuple[str, ...] = ()
    version: str = "0.1"
    plugin_id: str = "engine.homey"
    contract_version: str = "engine.brain/v1"
    id: str = ""

    @property
    def qualified_id(self) -> str:
        return self.id or f"{self.plugin_id}.{self.name}/v1"

    def to_dict(self) -> dict[str, Any]:
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
class EnginePlugin:
    manifest: PluginManifest
    targets: tuple[Any, ...] = ()
    specialists: tuple[Any, ...] = ()


@dataclass(frozen=True)
class BrainDecision:
    kind: DecisionKind
    name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    based_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["kind"] = self.kind.value
        return value


@dataclass(frozen=True)
class SpecialistAdvice:
    summary: str
    suggested_action: ToolCall | None = None
    complete: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "suggested_action": (
                self.suggested_action.to_dict() if self.suggested_action else None
            ),
            "complete": self.complete,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SpecialistAdvice:
        raw_action = value.get("suggested_action")
        return cls(
            summary=str(value.get("summary", "")),
            suggested_action=(
                ToolCall.from_dict(raw_action)
                if isinstance(raw_action, dict)
                else None
            ),
            complete=bool(value.get("complete", False)),
            metadata=dict(value.get("metadata", {})),
        )
