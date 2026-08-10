from __future__ import annotations

import re
from pathlib import Path

from .models import ContractError


def scaffold_plugin(destination: str | Path, name: str, template: str) -> Path:
    if template not in {"world", "specialist", "full"}:
        raise ContractError("template must be world, specialist or full")
    package = _package_name(name)
    plugin_id = f"example.{package.replace('_', '-')}"
    root = Path(destination) / name
    if root.exists() and any(root.iterdir()):
        raise ContractError(f"destination is not empty: {root}")
    files = _specialist_files(name, package, plugin_id) if template == "specialist" else _world_files(name, package, plugin_id, template == "full")
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def _package_name(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    if not value or value[0].isdigit():
        raise ContractError("plugin name must contain a leading letter")
    return value


def _world_files(
    name: str, package: str, plugin_id: str, include_specialist: bool
) -> dict[str, str]:
    specialists_toml = f'["{plugin_id}.warehouse-specialist/v1"]' if include_specialist else "[]"
    specialists_python = f'("{plugin_id}.warehouse-specialist/v1",)' if include_specialist else "()"
    specialist_tuple = "(WarehouseSpecialist(),)" if include_specialist else "()"
    specialist_class = '''

class WarehouseSpecialist:
    id = PLUGIN_ID + ".warehouse-specialist/v1"
    supported_families = ("warehouse.transfer-bin",)

    def advise(self, goal, snapshot, request):
        effect_id = str(request.get("effect_id", ""))
        effect = next((item for item in goal.desired_effects if item.id == effect_id), None)
        if effect is None:
            return SpecialistAdviceV1(self.id, False, None, "Unknown desired effect")
        entity_id = next(iter(effect.entity_selector.get("entity_ids", ())), "")
        entity = next((item for item in snapshot.entities if item.id == entity_id), None)
        if entity is None:
            return SpecialistAdviceV1(self.id, False, None, "Reserve bin is not observed")
        preference_id = PLUGIN_ID + ".preference.reserve-target-band/v1"
        minimum = int(goal.preferences.get(preference_id, effect.parameters["minimum_count"]))
        proposal = ProposedActionV1(
            id="proposal:" + uuid4().hex, goal_id=goal.id,
            desired_effect_id=effect.id, capability_family=effect.capability_family,
            target_id=entity.target_id, entity_id=entity.id,
            semantic_parameters={"minimum_count": minimum},
            based_on_snapshot_id=snapshot.id,
            based_on_world_revision=snapshot.revision,
            proposed_by=self.id,
        )
        return SpecialistAdviceV1(
            specialist_id=self.id,
            supported=True,
            proposed_action=proposal,
            summary="The specialist applied the declared warehouse preference.",
        )
''' if include_specialist else ""
    return {
        "pyproject.toml": f'''[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["engine-sdk>=0.2,<0.3"]

[project.entry-points."engine.plugins"]
{package} = "{package}.plugin:load_plugin"

[tool.setuptools]
package-dir = {{"" = "src"}}

[tool.setuptools.packages.find]
where = ["src"]
''',
        "engine-plugin.toml": f'''[plugin]
id = "{plugin_id}"
version = "0.1.0"
engine_api = ">=2.0,<3"
contract_version = "engine.plugin/v2"
description = "Generated non-house warehouse reference world"

[declarations]
world_providers = ["warehouse"]
controllers = ["warehouse-controller"]
executors = ["warehouse-executor"]
effect_oracles = ["warehouse-oracle"]
specialists = {specialists_toml}
entity_types = ["warehouse.grid", "warehouse.cell", "warehouse.bin"]
relation_types = ["contains", "located_in"]
observation_types = ["bin.count", "sensor.blocked"]
experience_providers = ["warehouse-experience"]

[needs]
network = []
filesystem = []
secrets = []
privacy = []

[store]
identity = "{plugin_id}.store"
schema_version = 1

[[capability_families]]
id = "{plugin_id}.transfer-bin/v1"
family = "warehouse.transfer-bin"
version = "1.0.0"
description = "Transfer a bounded number of crates between two bins"
control_layer = "semantic"
invocation_mode = "task"
risk_class = "low"
privacy_class = "local"
idempotent = true
deadline_ms = 5000
effect_measurements = ["bin.count"]
recovery = "poll_task_then_observe"
input_schema = {{type = "object", required = ["from", "to", "count"]}}
effect_schema = {{type = "object", required = ["minimum_count"]}}
limits = {{count = {{min = 1, max = 10}}}}

[[preferences]]
id = "{plugin_id}.preference.reserve-target-band/v1"
capability_family = "warehouse.transfer-bin"
unit = "crate"
promotion_mode = "shadow_low_risk"
description = "Preferred bounded reserve-bin target"
value_schema = {{type = "integer", minimum = 1, maximum = 10}}
''',
        f"src/{package}/__init__.py": "from .plugin import load_plugin\n\n__all__ = [\"load_plugin\"]\n",
        f"src/{package}/plugin.py": f'''from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from engine_sdk import (
    ActionRequestV1, AuthorizationV1, BehaviorBatchV1, BehaviorSignalV1,
    CapabilitySpecV2, ControlLayer,
    EffectDeltaV1, EntityV1, EvidenceGrade, ExecutionReceiptV2,
    ExecutionStateV2, InvocationModeV2, PluginManifestV2, PrivacyClass,
    ProposedActionV1, RelationV1, RiskClass, SpecialistAdviceV1,
    TargetObservationV2, WorldSnapshotV2, artifact_sha256,
)

PLUGIN_ID = "{plugin_id}"
TARGET_ID = PLUGIN_ID + ".warehouse"
CAPABILITY = CapabilitySpecV2(
    id=PLUGIN_ID + ".transfer-bin/v1", plugin_id=PLUGIN_ID,
    family="warehouse.transfer-bin", version="1.0.0",
    description="Transfer a bounded number of crates between two bins",
    input_schema={{"type": "object", "required": ["from", "to", "count"]}},
    effect_schema={{"type": "object", "required": ["minimum_count"]}},
    control_layer=ControlLayer.SEMANTIC, invocation_mode=InvocationModeV2.TASK,
    risk_class=RiskClass.LOW, privacy_class=PrivacyClass.LOCAL,
    idempotent=True, deadline_ms=5000, limits={{"count": {{"min": 1, "max": 10}}}},
    effect_measurements=("bin.count",), recovery="poll_task_then_observe",
)


class WarehouseProvider:
    plugin_id = PLUGIN_ID
    target_id = TARGET_ID
    poll_interval_seconds = 1.0
    freshness_seconds = 5.0

    def __init__(self):
        self.revision = 0
        self.counts = {{"incoming": 6, "reserve": 0}}
        self.behavior = []

    def discover(self):
        return (CAPABILITY,)

    def observe(self):
        self.revision += 1
        now = datetime.now(UTC).isoformat()
        grid = EntityV1("warehouse:grid", TARGET_ID, "warehouse.grid", PLUGIN_ID, "Grid")
        incoming = EntityV1("warehouse:bin:incoming", TARGET_ID, "warehouse.bin", PLUGIN_ID, "Incoming")
        reserve = EntityV1("warehouse:bin:reserve", TARGET_ID, "warehouse.bin", PLUGIN_ID, "Reserve")
        observations = tuple(
            __import__("engine_sdk").ObservationV1(
                id=f"{{entity}}:count:r{{self.revision}}", entity_id=f"warehouse:bin:{{entity}}",
                property="bin.count", value=count, unit="crate", source=PLUGIN_ID,
                observed_at=now, evidence_grade=EvidenceGrade.OBSERVED,
                quality=1.0, coverage="complete",
            )
            for entity, count in sorted(self.counts.items())
        )
        relations = (
            RelationV1("warehouse:contains:incoming", "contains", grid.id, incoming.id, PLUGIN_ID, now, EvidenceGrade.OBSERVED),
            RelationV1("warehouse:contains:reserve", "contains", grid.id, reserve.id, PLUGIN_ID, now, EvidenceGrade.OBSERVED),
        )
        return TargetObservationV2(
            TARGET_ID, self.revision, now, (grid, incoming, reserve), relations,
            observations, {{"entities": "complete", "bin.count": "complete"}}, PLUGIN_ID,
        )

    def subscribe(self, wake):
        del wake
        return None

    def publish_behavior(self, new_value, observed_at, context=None):
        signal = BehaviorSignalV1(
            id="behavior:" + uuid4().hex, plugin_id=PLUGIN_ID,
            target_id=TARGET_ID, entity_id="warehouse:bin:reserve",
            capability_family="warehouse.transfer-bin",
            preference_id=PLUGIN_ID + ".preference.reserve-target-band/v1",
            old_value=self.behavior[-1].new_value if self.behavior else 1,
            new_value=new_value, context=context or {{"shift": "day"}},
            observed_at=observed_at,
            provenance={{"source": "external_operator"}},
            evidence_grade=EvidenceGrade.INFERRED,
        )
        self.behavior.append(signal)
        return signal


class WarehouseExperienceProvider:
    id = "warehouse-experience"
    plugin_id = PLUGIN_ID

    def __init__(self, provider):
        self.provider = provider

    def read(self, after_cursor, limit):
        cursor = int(after_cursor or 0)
        selected = self.provider.behavior[cursor:cursor + limit]
        next_cursor = str(cursor + len(selected))
        return BehaviorBatchV1(
            next_cursor, tuple(selected),
            cursor + len(selected) < len(self.provider.behavior),
        )


class WarehouseController:
    plugin_id = PLUGIN_ID
    supported_families = ("warehouse.transfer-bin",)

    def concretize(self, proposal, snapshot, capability):
        current = next(
            int(item.value) for item in snapshot.observations
            if item.entity_id == proposal.entity_id and item.property == "bin.count"
        )
        wanted = int(proposal.semantic_parameters["minimum_count"])
        count = max(1, min(10, wanted - current))
        return ActionRequestV1(
            id="request:" + uuid4().hex, proposal_id=proposal.id, goal_id=proposal.goal_id,
            plugin_id=PLUGIN_ID, target_id=TARGET_ID, entity_id=proposal.entity_id,
            capability_id=capability.id, capability_family=capability.family,
            parameters={{"from": "incoming", "to": "reserve", "count": count}},
            snapshot_id=snapshot.id, world_revision=snapshot.revision,
            target_revision=int(snapshot.target_revisions[TARGET_ID]), preconditions=(),
            idempotency_key=proposal.id,
            deadline_at=(datetime.now(UTC) + timedelta(seconds=5)).isoformat(),
            invocation_mode=InvocationModeV2.TASK,
        )


class WarehouseExecutor:
    plugin_id = PLUGIN_ID

    def __init__(self, provider):
        self.provider = provider

    def dispatch(self, request, authorization):
        if authorization.request_sha256 != request.sha256:
            raise ValueError("authorization mismatch")
        count = int(request.parameters["count"])
        moved = min(count, self.provider.counts["incoming"])
        self.provider.counts["incoming"] -= moved
        self.provider.counts["reserve"] += moved
        state = ExecutionStateV2.SUCCEEDED if moved == count else ExecutionStateV2.PARTIAL
        return ExecutionReceiptV2(
            "receipt:" + uuid4().hex, request.id, authorization.id, TARGET_ID,
            request.capability_id, state, datetime.now(UTC).isoformat(),
            datetime.now(UTC).isoformat(), True, {{"moved": moved}},
            adapter_version="0.1.0",
        )

    def poll(self, external_handle):
        raise KeyError(external_handle)

    def cancel(self, external_handle):
        raise KeyError(external_handle)


class WarehouseOracle:
    plugin_id = PLUGIN_ID
    supported_families = ("warehouse.transfer-bin",)

    def reconcile(self, proposal, pre_state, receipt, post_state):
        before = _count(pre_state, proposal.entity_id)
        after = _count(post_state, proposal.entity_id)
        wanted = int(proposal.semantic_parameters["minimum_count"])
        achieved = after >= wanted
        return EffectDeltaV1(
            "effect:" + uuid4().hex, proposal.goal_id, proposal.id, receipt.request_id,
            receipt.id, pre_state.id, post_state.id, EvidenceGrade.OBSERVED,
            achieved, {{"before": before, "after": after}},
            tuple(item.id for item in post_state.observations if item.entity_id == proposal.entity_id),
            "fresh bin count reached requested minimum" if achieved else "fresh bin count below requested minimum",
            post_state.observed_at,
        )


def _count(snapshot, entity_id):
    return next(int(item.value) for item in snapshot.observations if item.entity_id == entity_id and item.property == "bin.count")
{specialist_class}

@dataclass(frozen=True)
class WarehousePlugin:
    manifest: PluginManifestV2
    providers: tuple
    controllers: tuple
    executors: tuple
    oracles: tuple
    specialists: tuple
    experience_providers: tuple


def load_plugin():
    provider = WarehouseProvider()
    return WarehousePlugin(
        PluginManifestV2(
            id=PLUGIN_ID, version="0.1.0", engine_api=">=2.0,<3",
            description="Generated non-house warehouse reference world",
            world_providers=("warehouse",), controllers=("warehouse-controller",),
            executors=("warehouse-executor",), effect_oracles=("warehouse-oracle",),
            specialists={specialists_python}, entity_types=("warehouse.grid", "warehouse.cell", "warehouse.bin"),
            relation_types=("contains", "located_in"), observation_types=("bin.count", "sensor.blocked"),
            capabilities=(CAPABILITY,), experience_providers=("warehouse-experience",),
            preference_specs=(__import__("engine_sdk").PreferenceSpecV1(
                id=PLUGIN_ID + ".preference.reserve-target-band/v1",
                plugin_id=PLUGIN_ID, capability_family="warehouse.transfer-bin",
                value_schema={{"type": "integer", "minimum": 1, "maximum": 10}},
                unit="crate",
                promotion_mode=__import__("engine_sdk").PreferencePromotionMode.SHADOW_LOW_RISK,
                description="Preferred bounded reserve-bin target",
            ),), store_identity=PLUGIN_ID + ".store",
        ),
        (provider,), (WarehouseController(),), (WarehouseExecutor(provider),),
        (WarehouseOracle(),), {specialist_tuple}, (WarehouseExperienceProvider(provider),),
    )
''',
        "tests/test_conformance.py": f'''import unittest

from engine_sdk import check_plugin
from {package}.plugin import load_plugin


class GeneratedPluginTest(unittest.TestCase):
    def test_reference_world_conforms(self):
        self.assertEqual(check_plugin(load_plugin()), ())

    def test_fake_transfer_has_observed_effect(self):
        plugin = load_plugin()
        before = plugin.providers[0].observe()
        self.assertEqual(before.observations[-1].value, 0)


if __name__ == "__main__":
    unittest.main()
''',
        "README.md": f'''# {name}

Generated Engine Plugin v2 `{template_name(include_specialist)}` reference.

This deliberately non-house world models warehouse bins and a bounded transfer
task. Import/factory construction is inert; observations and task effects are
provided by the deterministic fake.

Run `engine-plugin validate`, `engine-plugin inspect`, and `engine-plugin test`.
''',
    }


def template_name(include_specialist: bool) -> str:
    return "full" if include_specialist else "world"


def _specialist_files(name: str, package: str, plugin_id: str) -> dict[str, str]:
    return {
        "pyproject.toml": f'''[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["engine-sdk>=0.2,<0.3"]

[project.entry-points."engine.plugins"]
{package} = "{package}.plugin:load_plugin"

[tool.setuptools]
package-dir = {{"" = "src"}}
''',
        "engine-plugin.toml": f'''[plugin]
id = "{plugin_id}"
version = "0.1.0"
engine_api = ">=2.0,<3"
contract_version = "engine.plugin/v2"
description = "Generated specialist-only plugin"

[declarations]
world_providers = []
controllers = []
executors = []
effect_oracles = []
specialists = ["{plugin_id}.specialist/v1"]
entity_types = []
relation_types = []
observation_types = []
experience_providers = []

[needs]
network = []
filesystem = []
secrets = []
privacy = []

[store]
identity = "{plugin_id}.store"
schema_version = 1
''',
        f"src/{package}/__init__.py": "from .plugin import load_plugin\n",
        f"src/{package}/plugin.py": f'''from dataclasses import dataclass
from engine_sdk import PluginManifestV2, SpecialistAdviceV1


class Specialist:
    id = "{plugin_id}.specialist/v1"
    supported_families = ()

    def advise(self, goal, snapshot, request):
        del goal, snapshot, request
        return SpecialistAdviceV1(self.id, False, None, "No supported family")


@dataclass(frozen=True)
class Plugin:
    manifest: PluginManifestV2
    providers: tuple = ()
    controllers: tuple = ()
    executors: tuple = ()
    oracles: tuple = ()
    specialists: tuple = (Specialist(),)
    experience_providers: tuple = ()


def load_plugin():
    return Plugin(PluginManifestV2(
        id="{plugin_id}", version="0.1.0", engine_api=">=2.0,<3",
        description="Generated specialist-only plugin", world_providers=(),
        controllers=(), executors=(), effect_oracles=(),
        specialists=("{plugin_id}.specialist/v1",), entity_types=(),
        relation_types=(), observation_types=(), capabilities=(),
        store_identity="{plugin_id}.store",
    ))
''',
        "tests/test_conformance.py": f'''import unittest
from engine_sdk import check_plugin
from {package}.plugin import load_plugin

class GeneratedPluginTest(unittest.TestCase):
    def test_plugin_conforms(self):
        self.assertEqual(check_plugin(load_plugin()), ())
''',
        "README.md": f"# {name}\n\nGenerated Engine Plugin v2 specialist skeleton.\n",
    }
