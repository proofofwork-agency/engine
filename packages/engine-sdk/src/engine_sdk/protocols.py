from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .models import (
    ActionRequestV1,
    AuthorizationV1,
    BrainDecisionV2,
    CapabilitySpecV2,
    EffectDeltaV1,
    BehaviorBatchV1,
    ExecutionReceiptV2,
    GoalSpecV2,
    LifecycleEventV1,
    PluginManifestV2,
    ProposedActionV1,
    RoutineCandidateV1,
    RoutineSpecV1,
    RoutineTemplateSpecV1,
    SpecialistAdviceV1,
    TargetObservationV2,
    WorldSnapshotV2,
)


class WorldProvider(Protocol):
    @property
    def target_id(self) -> str: ...

    @property
    def plugin_id(self) -> str: ...

    @property
    def poll_interval_seconds(self) -> float: ...

    @property
    def freshness_seconds(self) -> float: ...

    def discover(self) -> tuple[CapabilitySpecV2, ...]: ...

    def observe(self) -> TargetObservationV2: ...

    def subscribe(
        self, wake: Callable[..., None]
    ) -> Callable[[], None] | None: ...


class DomainController(Protocol):
    @property
    def plugin_id(self) -> str: ...

    @property
    def supported_families(self) -> tuple[str, ...]: ...

    def concretize(
        self,
        proposal: ProposedActionV1,
        snapshot: WorldSnapshotV2,
        capability: CapabilitySpecV2,
    ) -> ActionRequestV1: ...


class Executor(Protocol):
    @property
    def plugin_id(self) -> str: ...

    def dispatch(
        self, request: ActionRequestV1, authorization: AuthorizationV1
    ) -> ExecutionReceiptV2: ...

    def poll(self, external_handle: str) -> ExecutionReceiptV2: ...

    def cancel(self, external_handle: str) -> ExecutionReceiptV2: ...


class EffectOracle(Protocol):
    @property
    def plugin_id(self) -> str: ...

    @property
    def supported_families(self) -> tuple[str, ...]: ...

    def reconcile(
        self,
        proposal: ProposedActionV1,
        pre_state: WorldSnapshotV2,
        receipt: ExecutionReceiptV2,
        post_state: WorldSnapshotV2,
    ) -> EffectDeltaV1: ...


class ExecutiveBrainV2(Protocol):
    @property
    def id(self) -> str: ...

    def decide(
        self, goal: GoalSpecV2, context_projection: dict[str, object]
    ) -> BrainDecisionV2: ...


class SpecialistBrainV2(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def supported_families(self) -> tuple[str, ...]: ...

    def advise(
        self,
        goal: GoalSpecV2,
        snapshot: WorldSnapshotV2,
        request: dict[str, object],
    ) -> SpecialistAdviceV1: ...


class ExperienceProvider(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def plugin_id(self) -> str: ...

    def read(self, after_cursor: str | None, limit: int) -> BehaviorBatchV1: ...


class RoutineCompiler(Protocol):
    """Translate plugin-owned pattern semantics; never create authorization."""

    @property
    def id(self) -> str: ...

    @property
    def plugin_id(self) -> str: ...

    @property
    def supported_templates(self) -> tuple[str, ...]: ...

    def compile(
        self,
        template: RoutineTemplateSpecV1,
        candidate: RoutineCandidateV1 | dict[str, object],
    ) -> tuple[RoutineSpecV1, GoalSpecV2]: ...


class LifecycleObserver(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def plugin_id(self) -> str: ...

    def observe(self, events: tuple[LifecycleEventV1, ...]) -> None: ...


class WorldPluginV2(Protocol):
    @property
    def manifest(self) -> PluginManifestV2: ...

    @property
    def providers(self) -> tuple[WorldProvider, ...]: ...

    @property
    def controllers(self) -> tuple[DomainController, ...]: ...

    @property
    def executors(self) -> tuple[Executor, ...]: ...

    @property
    def oracles(self) -> tuple[EffectOracle, ...]: ...

    @property
    def specialists(self) -> tuple[SpecialistBrainV2, ...]: ...

    @property
    def experience_providers(self) -> tuple[ExperienceProvider, ...]: ...

    @property
    def routine_compilers(self) -> tuple[RoutineCompiler, ...]: ...

    @property
    def lifecycle_observers(self) -> tuple[LifecycleObserver, ...]: ...
