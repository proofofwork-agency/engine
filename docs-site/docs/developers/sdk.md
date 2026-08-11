---
title: SDK reference
description: Public types, protocols, manifest helpers, and conformance in engine-sdk.
sidebar_position: 3
---

# SDK reference

`engine-sdk` is the dependency-light public contract layer. A plugin does not
need to import the Heart, SQLite store, model adapter, or runtime CLI. In this
repository, contract version `engine.plugin/v3` is paired with Engine API 3.x;
v2 remains supported for plugins without generic autonomy.

Use the SDK from the uv workspace; this documentation does not claim that the
packages are already available as public PyPI releases.

## Main groups

| Group | Main exports | Purpose |
| --- | --- | --- |
| world | `EntityV1`, `RelationV1`, `ObservationV1`, `TargetObservationV2`, `WorldSnapshotV2` | Typed state with source, time, coverage, and revision |
| goal | `GoalSpecV2`, `DesiredEffectV1`, `ConditionV1`, `ScopedConditionV1` | Desired effects, constraints, and guards |
| capability | `CapabilitySpecV2`, `ControlLayer`, `InvocationModeV2`, `RiskClass`, `PrivacyClass` | Static operational contract |
| action | `ProposedActionV1`, `ActionRequestV1`, `PolicyDecisionV1`, `AuthorizationV1` | Separation of proposal, exact request, and authority |
| result | `ExecutionReceiptV2`, `ExecutionStateV2`, `EffectDeltaV1`, `EvidenceGrade` | Execution fact and independently observed effect |
| cognition | `BrainDecisionV2`, `SpecialistAdviceV1`, `DecisionKindV2` | Typed, untrusted decision output |
| learning | `PreferenceSpecV1`, `BehaviorSignalV1`, `BehaviorBatchV1`, `LearningCandidateV1` | Bounded preference evidence and promotion |
| routines | `RoutineTemplateSpecV1`, `RoutineSpecV1`, `RoutineCandidateV1`, `AutonomyProfileV1` | Guards, shadow, approval, and exact delegated scope |
| autonomy | `AutonomyModeV1`, `AutonomyStrategySpecV1`, `GoalTemplateSpecV1`, `AutonomyEnrollmentV2`, `AutonomyContextV1`, `AutonomyDecisionV1`, `AutonomyEvaluationV1`, `AutonomyBindingV1`, `DispatchAttemptV1`, `SuggestionV1` | Proposal-only strategy evaluation, exact enrollment, crash-safe dispatch intent, and inert suggestions |
| lifecycle observation | `LifecycleEventV1`, `LifecycleObserver` | Plugin-declared, non-authoritative reaction to durable Engine milestones |
| manifest | `PluginManifestV2`, `PluginManifestV3`, `load_static_manifest`, `validate_manifest`, `compare_manifests` | Static enrollment and drift detection |
| conformance | `check_plugin` (root export) and additional helpers in `engine_sdk.conformance` | Dependency-light structural checks |

All contract values are frozen dataclasses or enums. They are data; possession
of a `ProposedActionV1` does not grant execution rights.

## Public protocols

`engine_sdk` exports the following `typing.Protocol` interfaces:

- `WorldProvider`
- `DomainController`
- `Executor`
- `EffectOracle`
- `ExecutiveBrainV2`
- `SpecialistBrainV2`
- `ExperienceProvider`
- `RoutineCompiler`
- `AutonomyStrategy`
- `GoalTemplateCompiler`
- `LifecycleObserver`
- `WorldPluginV2`
- `WorldPluginV3`

Structural typing keeps plugins independent of a concrete base class. At
registration time, the runtime also checks identities and agreement with the
manifest.

`LifecycleEventV1` identifies a bounded event only after its associated Engine
artifact or transition is durable. A `LifecycleObserver` may use that event for
best-effort outbound presentation, but it cannot turn it into a world fact,
authority, dispatch request, or effect proof. Observer failures are isolated
from the operational lifecycle.

The SDK lifecycle seam is intentionally not a raw telemetry subscription. The
`engine.ntfy` implementation, for example, forwards only GoalSpec creation,
learning/routine candidate creation or promotion, RoutineSpec addition or
activation, and genuine model-backed `ProposedAction` events. It does not
forward raw motion, light, sensor, snapshot, or individual behavior-signal
changes.

## Canonical serialization and hashes

Use the SDK helpers for auditable artifact identity:

```python
from engine_sdk import artifact_sha256, canonical_data, canonical_json

payload = {"limit": 10, "enabled": True}

as_data = canonical_data(payload)
as_json = canonical_json(payload)
fingerprint = artifact_sha256(payload)
```

`canonical_data()` accepts SDK dataclasses, `StrEnum`, mappings, tuples/lists,
and JSON primitives. Mapping keys are sorted. Non-serializable objects raise a
`TypeError`; there is no silent `repr()` fallback.

A `WorldSnapshotV2` has `sha256`, an `ActionRequestV1` has `sha256`, and a
`PluginManifestV2` has `fingerprint`. Authorization binds to the hash of one
exact request.

## Loading and comparing manifests

```python
from engine_sdk import (
    compare_manifests,
    load_static_manifest,
    validate_manifest,
)

static = load_static_manifest(".")  # reads ./engine-plugin.toml
validate_manifest(static)

loaded = load_plugin().manifest
mismatches = compare_manifests(static, loaded)
if mismatches:
    raise RuntimeError(f"manifest drift: {mismatches}")
```

`load_static_manifest()` accepts a manifest file or plugin directory. Contract
errors are `ContractError`, a subtype of `ValueError`.

The validator checks, among other things:

- a stable dotted lowercase plugin ID;
- `engine_api` and the contract version;
- unique capability, preference, routine, autonomy strategy, and goal template IDs;
- plugin ownership of declarations;
- preference and routine binding to a declared capability family;
- the required experience provider and routine compiler;
- provider + controller + executor + oracle for every mutating plugin;
- explicit `[autonomy]`, exact strategy/compiler roles, and `conflict_domain` for v3 mutation;
- a positive store schema version.

The version range is stored as a declaration in this slice; there is no complete
package resolver or marketplace compatibility service.

## Conformance in a plugin test

```python
import unittest

from engine_sdk import check_plugin
from my_world import load_plugin


class PluginContractTest(unittest.TestCase):
    def test_conforms(self) -> None:
        self.assertEqual((), check_plugin(load_plugin()))
```

`check_plugin()` returns all discovered failure messages instead of stopping at
the first one. `engine_sdk.conformance` also contains
`assert_authorization_matches()`, `assert_receipt_terminal()`, and
`observation_fingerprint()`; those three are not re-exported from the SDK root.
The current checks are intentionally small and deterministic. Add tests for
error mapping, stale revisions, idempotency, task recovery, lost
acknowledgements, and the domain-specific oracle.

## From proposal to request

A controller receives only a semantic proposal:

```python
class Controller:
    plugin_id = "example.warehouse"
    supported_families = ("warehouse.transfer-bin",)

    def concretize(self, proposal, snapshot, capability):
        # Choose exact parameters from observed state and capability limits.
        return ActionRequestV1(
            id="request:...",
            proposal_id=proposal.id,
            goal_id=proposal.goal_id,
            plugin_id=self.plugin_id,
            target_id=proposal.target_id,
            entity_id=proposal.entity_id,
            capability_id=capability.id,
            capability_family=capability.family,
            parameters={"from": "incoming", "to": "reserve", "count": 1},
            snapshot_id=snapshot.id,
            world_revision=snapshot.revision,
            target_revision=int(snapshot.target_revisions[proposal.target_id]),
            preconditions=(),
            idempotency_key=proposal.id,
            deadline_at="2026-08-10T12:00:05+00:00",
            invocation_mode=InvocationModeV2.TASK,
        )
```

Use a fresh deadline and a stable idempotency strategy in real code. The Heart
then validates schema, identity, snapshot, target revision, and preconditions
before invoking policy.

## Compatibility and change discipline

Extend contract data additively where possible. Under the project rules, a
change to the lifecycle, authority, adapter/skill contracts, or Engine/world
boundary requires an ADR and explicit approval. A new model provider should
remain behind the same typed output seam.
