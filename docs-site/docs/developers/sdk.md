---
title: SDK-referentie
description: Publieke types, protocollen, manifesthelpers en conformance in engine-sdk.
sidebar_position: 3
---

# SDK-referentie

`engine-sdk` is de dependency-light publieke contractlaag. Een plugin hoeft de
Heart, SQLite-store, modeladapter of runtime-CLI niet te importeren. In deze
repository is contractversie `engine.plugin/v2` gekoppeld aan Engine API 2.x.

Gebruik de SDK vanuit de uv-workspace; deze documentatie doet geen claim dat de
packages al als publieke PyPI-release beschikbaar zijn.

## Hoofdgroepen

| Groep | Belangrijkste exports | Doel |
| --- | --- | --- |
| wereld | `EntityV1`, `RelationV1`, `ObservationV1`, `TargetObservationV2`, `WorldSnapshotV2` | Typed state met bron, tijd, dekking en revision |
| doel | `GoalSpecV2`, `DesiredEffectV1`, `ConditionV1`, `ScopedConditionV1` | Gewenste effecten, constraints en guards |
| capability | `CapabilitySpecV2`, `ControlLayer`, `InvocationModeV2`, `RiskClass`, `PrivacyClass` | Statisch operationeel contract |
| actie | `ProposedActionV1`, `ActionRequestV1`, `PolicyDecisionV1`, `AuthorizationV1` | Scheiding tussen voorstel, exact request en authority |
| resultaat | `ExecutionReceiptV2`, `ExecutionStateV2`, `EffectDeltaV1`, `EvidenceGrade` | Uitvoeringsfeit en onafhankelijk waargenomen effect |
| cognition | `BrainDecisionV2`, `SpecialistAdviceV1`, `DecisionKindV2` | Typed, onbetrouwbare beslisoutput |
| learning | `PreferenceSpecV1`, `BehaviorSignalV1`, `BehaviorBatchV1`, `LearningCandidateV1` | Begrensde preference-evidence en promotie |
| routines | `RoutineTemplateSpecV1`, `RoutineSpecV1`, `RoutineCandidateV1`, `AutonomyProfileV1` | Guards, shadow, approval en exact gedelegeerde scope |
| manifest | `PluginManifestV2`, `load_static_manifest`, `validate_manifest`, `compare_manifests` | Statische enrollment en driftcontrole |
| conformance | `check_plugin` (root-export) en aanvullende helpers in `engine_sdk.conformance` | Dependency-light structurele checks |

Alle contractwaarden zijn frozen dataclasses of enums. Ze zijn data; het bezit
van een `ProposedActionV1` geeft geen uitvoeringsrecht.

## Publieke protocollen

`engine_sdk` exporteert de volgende `typing.Protocol`-interfaces:

- `WorldProvider`
- `DomainController`
- `Executor`
- `EffectOracle`
- `ExecutiveBrainV2`
- `SpecialistBrainV2`
- `ExperienceProvider`
- `RoutineCompiler`
- `WorldPluginV2`

Structurele typing houdt plugins los van een concrete basisklasse. De runtime
controleert daarnaast identiteiten en manifestovereenkomst tijdens registratie.

## Canonieke serialisatie en hashes

Gebruik de SDK-helpers voor auditable artefactidentiteit:

```python
from engine_sdk import artifact_sha256, canonical_data, canonical_json

payload = {"limit": 10, "enabled": True}

as_data = canonical_data(payload)
as_json = canonical_json(payload)
fingerprint = artifact_sha256(payload)
```

`canonical_data()` accepteert SDK-dataclasses, `StrEnum`, mappings, tuples/lijsten
en JSON-primitieven. Mappings worden op sleutel gesorteerd. Niet-serialiseerbare
objecten geven een `TypeError`; er is geen stille `repr()`-fallback.

Een `WorldSnapshotV2` heeft `sha256`, een `ActionRequestV1` heeft `sha256` en een
`PluginManifestV2` heeft `fingerprint`. Authorization bindt aan de hash van één
exact request.

## Manifest laden en vergelijken

```python
from engine_sdk import (
    compare_manifests,
    load_static_manifest,
    validate_manifest,
)

static = load_static_manifest(".")  # leest ./engine-plugin.toml
validate_manifest(static)

loaded = load_plugin().manifest
mismatches = compare_manifests(static, loaded)
if mismatches:
    raise RuntimeError(f"manifest drift: {mismatches}")
```

`load_static_manifest()` accepteert een manifestbestand of pluginmap.
Contractfouten zijn `ContractError`, een subtype van `ValueError`.

De validator controleert onder andere:

- stabiele dotted lowercase plugin-ID;
- `engine_api` en contractversie;
- unieke capability-, preference- en routine-ID's;
- pluginownership van declarations;
- preference/routinebinding aan een gedeclareerde capabilityfamily;
- benodigde experience provider en routinecompiler;
- provider + controller + executor + oracle voor iedere muterende plugin;
- positieve store schema version.

Versiebereikcompatibiliteit wordt in deze slice als declaration bewaard; een
volledige package-resolver of marketplace-compatibiliteitsservice is er niet.

## Conformance in een plugintest

```python
import unittest

from engine_sdk import check_plugin
from mijn_wereld import load_plugin


class PluginContractTest(unittest.TestCase):
    def test_conforms(self) -> None:
        self.assertEqual((), check_plugin(load_plugin()))
```

`check_plugin()` retourneert alle gevonden foutteksten in plaats van bij de
eerste te stoppen. `engine_sdk.conformance` bevat daarnaast
`assert_authorization_matches()`, `assert_receipt_terminal()` en
`observation_fingerprint()`; die drie worden niet vanuit de SDK-root
gere-exporteerd. De huidige checks zijn bewust klein en deterministisch. Voeg
daarnaast tests toe voor foutmapping, stale revisions, idempotency, taskherstel,
lost acknowledgements en de domeinspecifieke oracle.

## Van proposal naar request

Een controller ontvangt alleen een semantisch proposal:

```python
class Controller:
    plugin_id = "example.warehouse"
    supported_families = ("warehouse.transfer-bin",)

    def concretize(self, proposal, snapshot, capability):
        # Kies exacte parameters uit observed state en capability limits.
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

Gebruik in echte code een verse deadline en een stabiele idempotencystrategie.
Heart valideert daarna schema, identiteit, snapshot, targetrevision en
preconditions voordat policy wordt aangeroepen.

## Compatibiliteit en wijzigingsdiscipline

Breid contractdata additief uit waar mogelijk. Een wijziging aan de lifecycle,
authority, adapter-/skillcontracten of Engine/wereldgrens vereist volgens de
projectregels een ADR en expliciete goedkeuring. Een nieuwe modelprovider hoort
achter dezelfde typed outputseam te blijven.
