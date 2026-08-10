from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine_reference_world import create_plugin

from engine import NaturalIntentCompilerV2, PluginRegistryV2, WorldStore
from engine.world_heart import DeterministicExecutiveBrainV2, WorldHeartV2


class _GoalModel:
    provider_id = "fixture"
    model_id = "goal-compiler"

    def __init__(self, family: str = "warehouse.transfer-bin") -> None:
        self.family = family
        self.context = None

    def compile(self, context):
        self.context = context
        return {
            "mode": "maintain",
            "entity_scope": {"target_ids": ["engine.reference-world.warehouse"]},
            "desired_effects": [
                {
                    "id": "reserve-minimum",
                    "capability_family": self.family,
                    "entity_selector": {"entity_ids": ["warehouse:bin:reserve"]},
                    "condition": {
                        "op": "gte",
                        "path": "observation:bin.count",
                        "value": 3,
                        "unit": "crate",
                    },
                    "parameters": {"minimum_count": 3},
                }
            ],
            "constraints": [],
            "budgets": {"max_actions": 4},
            "stop_conditions": [],
        }


class CognitionV2Tests(unittest.TestCase):
    def test_natural_intent_compiles_to_typed_goal_but_cannot_mint_mandate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="engine-cognition-v2-") as raw:
            base = Path(raw)
            plugin = create_plugin(base / "warehouse.sqlite3")
            self.addCleanup(plugin.providers[0].store.close)
            registry = PluginRegistryV2()
            registry.register(plugin, "plugins/reference-world")
            store = WorldStore(base / "engine.sqlite3")
            self.addCleanup(store.close)
            # Observation is local and durable before any model projection.
            seed_goal = _seed_goal()
            heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())
            snapshot = heart.observe_world(seed_goal, refresh_targets=None)
            model = _GoalModel()

            goal = NaturalIntentCompilerV2(model).compile(
                "Keep the reserve stocked",
                snapshot,
                registry.manifests,
                mandate_id="owner-selected-mandate",
                goal_id="goal:compiled",
            )

            self.assertEqual("owner-selected-mandate", goal.mandate_id)
            self.assertEqual("warehouse.transfer-bin", goal.desired_effects[0].capability_family)
            self.assertIsNotNone(model.context)
            self.assertIn("input_sha256", model.context)

    def test_goal_model_cannot_invent_capability_family(self) -> None:
        with tempfile.TemporaryDirectory(prefix="engine-cognition-v2-") as raw:
            base = Path(raw)
            plugin = create_plugin(base / "warehouse.sqlite3")
            self.addCleanup(plugin.providers[0].store.close)
            registry = PluginRegistryV2()
            registry.register(plugin, "plugins/reference-world")
            store = WorldStore(base / "engine.sqlite3")
            self.addCleanup(store.close)
            heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())
            snapshot = heart.observe_world(_seed_goal(), refresh_targets=None)

            with self.assertRaisesRegex(ValueError, "unknown capability"):
                NaturalIntentCompilerV2(_GoalModel("warehouse.teleport")).compile(
                    "Teleport it", snapshot, registry.manifests,
                    mandate_id="mandate", goal_id="goal:bad",
                )

    def test_required_setup_selection_and_effect_schema_reach_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="engine-cognition-selection-") as raw:
            base = Path(raw)
            plugin = create_plugin(base / "warehouse.sqlite3")
            self.addCleanup(plugin.providers[0].store.close)
            registry = PluginRegistryV2()
            registry.register(plugin, "plugins/reference-world")
            store = WorldStore(base / "engine.sqlite3")
            self.addCleanup(store.close)
            heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())
            snapshot = heart.observe_world(_seed_goal(), refresh_targets=None)
            model = _GoalModel()

            NaturalIntentCompilerV2(model).compile(
                "Keep four crates in reserve",
                snapshot,
                registry.manifests,
                mandate_id="mandate",
                required_target_id="engine.reference-world.warehouse",
                required_entity_id="warehouse:bin:reserve",
                required_capability_family="warehouse.transfer-bin",
            )

            selection = model.context["required_selection"]
            self.assertEqual("warehouse.transfer-bin", selection["capability_family"])
            self.assertEqual(
                ["minimum_count"],
                selection["effect_schema"]["required"],
            )
            self.assertEqual(["bin.count"], selection["effect_measurements"])
            self.assertEqual({"bin.count": "crate"}, selection["measurement_units"])


def _seed_goal():
    from engine_sdk import ConditionV1, DesiredEffectV1, GoalModeV2, GoalSpecV2

    return GoalSpecV2(
        "goal:seed", "observe", GoalModeV2.MAINTAIN,
        {"target_ids": ["engine.reference-world.warehouse"]},
        (
            DesiredEffectV1(
                "seed", "warehouse.transfer-bin",
                {"entity_ids": ["warehouse:bin:reserve"]},
                ConditionV1("gte", path="observation:bin.count", value=0, unit="crate"),
                {"minimum_count": 1},
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
