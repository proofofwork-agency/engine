from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine_reference_world import create_plugin
from engine_runtime import EngineApplication, RuntimeConfig
from engine_runtime.cli import build_parser
from jsonschema.exceptions import ValidationError

from engine import PluginRegistryV2


class EngineRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-runtime-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_plugin_neutral_setup_previews_then_activates_model_compiled_goal(self) -> None:
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        registry = PluginRegistryV2()
        registry.register(plugin, "plugins/reference-world")
        app = EngineApplication(
            RuntimeConfig(store_path=self.base / "engine.sqlite3"),
            registry=registry,
            model=_GoalModel(),
        )
        self.addCleanup(app.close)
        arguments = {
            "plugin_id": "engine.reference-world",
            "target_id": "engine.reference-world.warehouse",
            "entity_id": "warehouse:bin:reserve",
            "capability_family": "warehouse.transfer-bin",
            "preference_id": (
                "engine.reference-world.preference.reserve-target-band/v1"
            ),
            "intent": "Keep the reserve supplied",
        }

        preview = app.setup(**arguments, activate=False)

        self.assertFalse(preview["activated"])
        self.assertEqual((), app.store.live_goals())
        activated = app.setup(**arguments, activate=True)
        self.assertTrue(activated["activated"])
        self.assertEqual(1, len(app.store.live_goals()))
        self.assertEqual(
            1,
            app.store.live_goals()[0].preferences[arguments["preference_id"]],
        )

    def test_explicit_correction_is_schema_validated_and_versioned(self) -> None:
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        registry = PluginRegistryV2()
        registry.register(plugin, "plugins/reference-world")
        app = EngineApplication(
            RuntimeConfig(store_path=self.base / "engine.sqlite3"),
            registry=registry,
            model=_GoalModel(),
        )
        self.addCleanup(app.close)
        preference = "engine.reference-world.preference.reserve-target-band/v1"
        result = app.setup(
            plugin_id="engine.reference-world",
            target_id="engine.reference-world.warehouse",
            entity_id="warehouse:bin:reserve",
            capability_family="warehouse.transfer-bin",
            preference_id=preference,
            intent="Keep the reserve supplied",
            activate=True,
        )
        goal_id = result["goal"]["id"]

        corrected = app.correct(goal_id=goal_id, preference_id=preference, value=4)

        self.assertEqual(2, corrected.version)
        self.assertEqual(4, corrected.preferences[preference])
        with self.assertRaises(ValidationError):
            app.correct(goal_id=goal_id, preference_id=preference, value=99)

    def test_cli_surface_contains_generic_commands(self) -> None:
        parser = build_parser()
        cases = (
            ["plugins", "list"],
            ["plugins", "inspect", "engine.reference-world"],
            ["world", "observe"],
            ["run"],
            ["status", "--json"],
            ["learning", "status"],
            ["learning", "rollback", "--candidate", "habit:1"],
            ["yolo", "enable", "--entity", "homey:home:zone:study"],
            ["yolo", "status"],
            ["yolo", "disable"],
            ["routines", "list"],
            ["routines", "inspect", "routine:1"],
            ["routines", "approve", "candidate:1"],
            ["routines", "reject", "candidate:1"],
            ["routines", "rollback", "routine:1"],
            ["model", "canary"],
        )
        for argv in cases:
            with self.subTest(argv=argv):
                self.assertIsNotNone(parser.parse_args(argv).command)

    def test_local_model_needs_no_key_but_remote_model_fails_closed(self) -> None:
        local = EngineApplication(
            RuntimeConfig(
                store_path=self.base / "local.sqlite3",
                model_base_url="http://127.0.0.1:18081/v1",
                model_id="local-gemma-1b",
                model_provider_id="local-llama.cpp",
            ),
            registry=PluginRegistryV2(),
        )
        self.addCleanup(local.close)
        self.assertEqual("local-llama.cpp", local.model.provider_id)

        with self.assertRaisesRegex(RuntimeError, "remote.*API key"):
            EngineApplication(
                RuntimeConfig(
                    store_path=self.base / "remote.sqlite3",
                    model_base_url="https://models.example/v1",
                    model_id="remote-model",
                ),
                registry=PluginRegistryV2(),
            )

    def test_local_environment_alias_selects_llama_cpp(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "ENGINE_LOCAL_MODEL_BASE_URL": "http://localhost:18081/v1",
                "ENGINE_LOCAL_MODEL_ID": "local-gemma-1b",
            },
            clear=True,
        ):
            config = RuntimeConfig.from_environment()
        self.assertEqual("local-llama.cpp", config.model_provider_id)
        self.assertIsNone(config.model_api_key)


class _GoalModel:
    provider_id = "fixture"
    model_id = "goal-model"

    def compile(self, context):
        del context
        return {
            "mode": "maintain",
            "entity_scope": {
                "target_ids": ["engine.reference-world.warehouse"]
            },
            "desired_effects": [
                {
                    "id": "reserve-minimum",
                    "capability_family": "warehouse.transfer-bin",
                    "entity_selector": {
                        "entity_ids": ["warehouse:bin:reserve"]
                    },
                    "condition": {
                        "op": "gte",
                        "path": "observation:bin.count",
                        "value": 3,
                        "unit": "crate",
                        "children": [],
                    },
                    "parameters": {"minimum_count": 3},
                    "description": "Keep three crates in reserve",
                }
            ],
            "constraints": [],
            "budgets": {},
            "stop_conditions": [],
            "priority": 1,
        }

    def decide(self, context):
        del context
        return {
            "kind": "wait",
            "rationale": "fixture",
            "specialist_id": None,
            "query": {},
            "proposed_action": None,
        }
