from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .models import (
    BrainContext,
    BrainDecision,
    BrainManifest,
    CapabilitySpec,
    Goal,
    SpecialistAdvice,
    TargetManifest,
    ToolCall,
    ToolResult,
    WorldSnapshot,
)


class TargetAdapter(Protocol):
    @property
    def manifest(self) -> TargetManifest: ...

    def capabilities(self) -> tuple[CapabilitySpec, ...]: ...

    def observe(self) -> WorldSnapshot: ...

    def execute(self, call: ToolCall) -> ToolResult: ...

    def goal_satisfied(self, goal: Goal, snapshot: WorldSnapshot) -> bool: ...


class TargetEventSource(Protocol):
    """Optional wake-up seam; events trigger observation but never become truth."""

    def subscribe(
        self, wake: Callable[..., None]
    ) -> Callable[[], None] | None: ...


class TargetChangeFilter(Protocol):
    """Optional goal-scoped filter for noisy target snapshots."""

    def goal_relevant_change(
        self,
        goal: Goal,
        previous: WorldSnapshot,
        current: WorldSnapshot,
    ) -> bool: ...


class ExecutiveBrain(Protocol):
    @property
    def manifest(self) -> BrainManifest: ...

    def decide(self, context: BrainContext) -> BrainDecision: ...


class SpecialistBrain(Protocol):
    @property
    def manifest(self) -> BrainManifest: ...

    def advise(self, context: BrainContext) -> SpecialistAdvice: ...


class StructuredDecisionModel(Protocol):
    """Provider-neutral boundary for an actual LLM or other general model."""

    def decide(self, context: dict[str, object]) -> dict[str, object]: ...
