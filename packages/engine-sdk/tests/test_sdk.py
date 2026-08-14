from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

from engine_sdk import (
    AutonomyProfileV1,
    AutonomyShadowOutcomeV1,
    BehaviorBatchV1,
    BehaviorSignalV1,
    ConditionV1,
    ContractError,
    EvidenceGrade,
    EvidenceRefV1,
    LifecycleEventV1,
    PreferencePromotionMode,
    RelationHypothesisV1,
    RiskClass,
    RoutineShadowEventV1,
    ScopedConditionV1,
    artifact_sha256,
    check_plugin,
    compare_manifests,
    load_static_manifest,
)
from engine_sdk.scaffold import scaffold_plugin


class EngineSDKTests(unittest.TestCase):
    def test_lifecycle_event_round_trip_preserves_sequence_and_provenance(self) -> None:
        event = LifecycleEventV1(
            sequence=7,
            kind="goal_created",
            source="heart.v2",
            payload={"goal_id": "goal:comfort"},
            created_at="2026-08-10T12:00:00+00:00",
            goal_id="goal:comfort",
        )
        self.assertEqual(event, LifecycleEventV1.from_dict(event.to_dict()))
        with self.assertRaisesRegex(ContractError, "sequence must be positive"):
            LifecycleEventV1(
                sequence=0,
                kind="goal_created",
                source="heart.v2",
                payload={},
                created_at="2026-08-10T12:00:00+00:00",
            )

    def test_behavior_and_goal_preference_contracts_round_trip(self) -> None:
        signal = BehaviorSignalV1(
            id="example.signal/1",
            plugin_id="example.world",
            target_id="target",
            entity_id="entity",
            capability_family="example.adjust",
            preference_id="example.world.preference.band/v1",
            old_value=1,
            new_value=2,
            context={"period": "day"},
            observed_at="2026-08-01T00:00:00+00:00",
            provenance={"source": "fixture"},
        )
        batch = BehaviorBatchV1("1", (signal,))
        self.assertEqual(batch, BehaviorBatchV1.from_dict(batch.to_dict()))
        manifest = load_static_manifest(
            Path(__file__).resolve().parents[3] / "plugins/reference-world"
        )
        self.assertEqual(
            PreferencePromotionMode.SHADOW_LOW_RISK,
            manifest.preference_specs[0].promotion_mode,
        )

    def test_behavior_signal_additive_routine_fields_round_trip(self) -> None:
        signal = BehaviorSignalV1(
            id="signal:routine:1",
            plugin_id="example.world",
            target_id="target",
            entity_id="entity",
            capability_family="example.adjust",
            preference_id="example.world.preference.band/v1",
            old_value=True,
            new_value=False,
            context={"stable": True},
            observed_at="2026-08-01T00:00:00+00:00",
            provenance={"origin": "unknown"},
            routine_template_id="daily-off/v1",
            pattern_value={"minute_of_day": 1320},
        )
        self.assertEqual(signal, BehaviorSignalV1.from_dict(signal.to_dict()))
        legacy = signal.to_dict()
        legacy.pop("routine_template_id")
        legacy.pop("pattern_value")
        parsed = BehaviorSignalV1.from_dict(legacy)
        self.assertIsNone(parsed.routine_template_id)
        self.assertIsNone(parsed.pattern_value)

    def test_scoped_condition_requires_a_selector_on_every_leaf(self) -> None:
        value = ScopedConditionV1(
            "all",
            children=(
                ScopedConditionV1(
                    "eq", {"entity_ids": ["context:local"]},
                    "observation:time.weekday", 1,
                ),
                ScopedConditionV1(
                    "eq", {"entity_ids": ["zone:1"]},
                    "observation:presence", True,
                ),
            ),
        )
        self.assertEqual(value, ScopedConditionV1.from_dict(value.to_dict()))
        with self.assertRaisesRegex(ContractError, "entity_selector"):
            ScopedConditionV1("eq", path="observation:presence", value=True)

    def test_autonomy_scope_is_exact_low_risk_and_shadow_never_dispatches(self) -> None:
        profile = AutonomyProfileV1(
            "profile:1", "example.world", "target", ("entity",),
            ("routine/v1",), ("example.adjust",), RiskClass.LOW,
            "fingerprint", {"minimum_cooldown_seconds": 300},
            "2026-08-01T00:00:00+00:00", "owner",
        )
        self.assertEqual(profile, AutonomyProfileV1.from_dict(profile.to_dict()))
        with self.assertRaisesRegex(ContractError, "wildcards"):
            AutonomyProfileV1(
                "profile:2", "example.world", "target", ("entity:*",),
                ("routine/v1",), ("example.adjust",), RiskClass.LOW,
                "fingerprint", {}, "2026-08-01T00:00:00+00:00", "owner",
            )
        with self.assertRaisesRegex(ContractError, "cannot record dispatches"):
            RoutineShadowEventV1(
                "shadow:1", "candidate:1", "day:1",
                "2026-08-01T00:00:00+00:00",
                "2026-08-01T00:30:00+00:00",
                dispatch_count=1,
            )
        with self.assertRaisesRegex(ContractError, "OBSERVED or DERIVED"):
            EvidenceRefV1(
                "obs:1", "entity:1", "bin.count", "plugin",
                "2026-08-01T00:00:00+00:00", EvidenceGrade.INFERRED, "world:1",
            )
        with self.assertRaisesRegex(ContractError, "cannot record dispatches"):
            AutonomyShadowOutcomeV1(
                "shadow:2", "enrollment:1", "key:1",
                "2026-08-01T00:00:00+00:00",
                "2026-08-01T00:45:00+00:00",
                "world:1", "entity:1", {"on": True}, "evaluation:1",
                dispatch_count=1,
            )

    def test_canonical_hash_is_order_independent(self) -> None:
        self.assertEqual(
            artifact_sha256({"b": 2, "a": {"y": 1, "x": 0}}),
            artifact_sha256({"a": {"x": 0, "y": 1}, "b": 2}),
        )

    def test_condition_ast_rejects_python_or_unknown_operators(self) -> None:
        with self.assertRaisesRegex(ContractError, "unsupported"):
            ConditionV1("python", path="__import__('os')")
        with self.assertRaisesRegex(ContractError, "requires child"):
            ConditionV1("all")

    def test_relation_hypothesis_cannot_be_relabelled_observed(self) -> None:
        with self.assertRaisesRegex(ContractError, "INFERRED"):
            RelationHypothesisV1(
                "hypothesis:1", "a", "b", "located_in", "model", (), 0.9,
                evidence_grade=EvidenceGrade.OBSERVED,
            )

    def test_bootstrap_world_loads_and_conforms_without_manual_edits(self) -> None:
        with tempfile.TemporaryDirectory(prefix="engine-plugin-bootstrap-") as raw:
            root = scaffold_plugin(raw, "sample-world", "world")
            manifest = load_static_manifest(root)
            sys.path.insert(0, str(root / "src"))
            try:
                module = importlib.import_module("sample_world.plugin")
                plugin = module.load_plugin()
                self.assertEqual((), compare_manifests(manifest, plugin.manifest))
                self.assertEqual((), check_plugin(plugin))
            finally:
                sys.path.remove(str(root / "src"))
                for name in tuple(sys.modules):
                    if name == "sample_world" or name.startswith("sample_world."):
                        del sys.modules[name]

    def test_static_manifest_requires_controller_executor_and_oracle_for_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="engine-plugin-invalid-") as raw:
            path = Path(raw) / "engine-plugin.toml"
            path.write_text(
                """
[plugin]
id = "example.invalid"
version = "0.1.0"
engine_api = ">=2,<3"
contract_version = "engine.plugin/v2"
description = "invalid"
[declarations]
world_providers = ["world"]
controllers = []
executors = []
effect_oracles = []
specialists = []
entity_types = ["thing"]
relation_types = []
observation_types = []
[needs]
network = []
filesystem = []
secrets = []
privacy = []
[store]
identity = "example.invalid.store"
schema_version = 1
[[capability_families]]
id = "example.invalid.move/v1"
family = "example.move"
control_layer = "semantic"
invocation_mode = "immediate"
risk_class = "low"
privacy_class = "local"
idempotent = true
deadline_ms = 1000
input_schema = {}
effect_schema = {}
""".strip(),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ContractError, "controller, executor"):
                load_static_manifest(path)


if __name__ == "__main__":
    unittest.main()
