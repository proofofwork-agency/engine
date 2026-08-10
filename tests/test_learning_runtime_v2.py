from __future__ import annotations

import ast
import importlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Self

from engine_reference_world import create_plugin
from engine_runtime import OpenAICompatibleV2Model, RuntimeLease
from engine_runtime.lease import LeaseHeldError
from engine_sdk import (
    BehaviorBatchV1,
    BehaviorSignalV1,
    ConditionV1,
    DesiredEffectV1,
    GoalModeV2,
    GoalSpecV2,
    LearningStatus,
    StandingMandateV1,
)
from engine_sdk.scaffold import scaffold_plugin

from engine import (
    DeterministicExecutiveBrainV2,
    ModelExecutiveBrainV2,
    PluginRegistryV2,
    WorldHeartV2,
    WorldStore,
)

PLUGIN_ID = "engine.reference-world"
TARGET_ID = "engine.reference-world.warehouse"
ENTITY_ID = "warehouse:bin:reserve"
FAMILY = "warehouse.transfer-bin"
PREFERENCE_ID = "engine.reference-world.preference.reserve-target-band/v1"


class GenericLearningRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-learning-v2-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_reference_experience_is_exactly_once_promotes_and_survives_restart(self) -> None:
        plugin, registry, store, heart, goal = self._reference_system()
        plugin_store = plugin.providers[0].store
        store.save_plan(
            "old-plan",
            goal.id,
            PLUGIN_ID,
            FAMILY,
            registry.manifest_fingerprint(PLUGIN_ID),
            goal.mandate_id,
            {"old": True},
            {"achieved": True},
        )
        base = datetime.now(UTC) - timedelta(days=12)
        for index in range(5):
            plugin_store.record_behavior(
                old_value=3,
                new_value=5,
                context={"shift": "day"},
                observed_at=(base + timedelta(days=index // 2)).isoformat(),
                signal_id=f"warehouse-signal:{index}",
            )

        passes = heart.run_cycle()

        self.assertEqual(1, len(passes))
        promoted = store.get_goal(goal.id)
        self.assertEqual(2, promoted.version)
        self.assertEqual(5, promoted.preferences[PREFERENCE_ID])
        self.assertEqual(0, store.plan_count(goal.id))
        self.assertEqual(5, store.behavior_signal_count())
        candidates = store.learning_candidates(goal_id=goal.id)
        self.assertEqual(1, len(candidates))
        self.assertEqual(LearningStatus.PROMOTED, candidates[0].status)
        self.assertEqual(5, store.proposals(goal.id)[0].semantic_parameters["minimum_count"])

        heart.run_cycle()
        self.assertEqual(5, store.behavior_signal_count())
        self.assertEqual(5, len(store.preference_evidence(goal.id)))
        plugin_store.close()
        store.close()

        plugin2 = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin2.providers[0].store.close)
        registry2 = PluginRegistryV2()
        registry2.register(plugin2, "plugins/reference-world")
        store2 = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store2.close)
        heart2 = WorldHeartV2(
            store2, registry2, DeterministicExecutiveBrainV2()
        )

        heart2.run_cycle()

        self.assertEqual("5", store2.plugin_cursor("warehouse-experience"))
        self.assertEqual(5, store2.behavior_signal_count())
        self.assertEqual(5, store2.get_goal(goal.id).preferences[PREFERENCE_ID])

    def test_unknown_preference_is_retained_as_unlinked_evidence(self) -> None:
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        signal = BehaviorSignalV1(
            id="unknown:1",
            plugin_id=PLUGIN_ID,
            target_id=TARGET_ID,
            entity_id=ENTITY_ID,
            capability_family=FAMILY,
            preference_id="engine.reference-world.preference.unknown/v1",
            old_value=1,
            new_value=2,
            context={},
            observed_at=datetime.now(UTC).isoformat(),
            provenance={"source": "fixture"},
        )
        replacement = replace(
            plugin,
            experience_providers=(_OneBatchExperience(signal),),
        )
        registry = PluginRegistryV2()
        registry.register(replacement, "plugins/reference-world")
        store = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store.close)
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())

        self.assertEqual((), heart.run_cycle())

        self.assertEqual(1, store.behavior_signal_count())
        links = store.behavior_signal_links(signal.id)
        self.assertEqual("unlinked", links[0]["status"])
        self.assertIn("unknown preference", links[0]["reason"])

    def test_cycle_observes_connected_world_even_without_goals(self) -> None:
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        registry = PluginRegistryV2()
        registry.register(plugin, "plugins/reference-world")
        store = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store.close)
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())

        result = heart.run_cycle()

        self.assertEqual((), result)
        self.assertIsNotNone(store.latest_world_snapshot())
        self.assertEqual(1, store.latest_world_snapshot().target_revisions[TARGET_ID])

    def test_generated_full_plugin_learns_and_continues_after_restart(self) -> None:
        root = scaffold_plugin(self.base, "generated-learning", "full")
        sys.path.insert(0, str(root / "src"))
        try:
            module = importlib.import_module("generated_learning.plugin")
            plugin = module.load_plugin()
            provider = plugin.providers[0]
            base = datetime.now(UTC) - timedelta(days=12)
            for index in range(5):
                provider.publish_behavior(
                    4,
                    (base + timedelta(days=index // 2)).isoformat(),
                    {"shift": "day"},
                )
            registry = PluginRegistryV2()
            registry.register(plugin, root)
            store_path = self.base / "generated-engine.sqlite3"
            store = WorldStore(store_path)
            now = datetime.now(UTC)
            plugin_id = "example.generated-learning"
            target_id = plugin_id + ".warehouse"
            preference_id = plugin_id + ".preference.reserve-target-band/v1"
            mandate = StandingMandateV1(
                "mandate:generated-learning",
                (plugin_id,),
                (target_id,),
                (ENTITY_ID,),
                (FAMILY,),
                {},
                (),
                ("learning.low-risk",),
                (now - timedelta(days=20)).isoformat(),
                (now + timedelta(days=20)).isoformat(),
                {plugin_id: "0.1.0"},
                "owner",
            )
            goal = GoalSpecV2(
                id="goal:generated-learning",
                source_intent="Maintain the generated learned reserve target",
                mode=GoalModeV2.MAINTAIN,
                entity_scope={"target_ids": [target_id]},
                desired_effects=(
                    DesiredEffectV1(
                        id="reserve-minimum",
                        capability_family=FAMILY,
                        entity_selector={"entity_ids": [ENTITY_ID]},
                        condition=ConditionV1(
                            "gte",
                            path="observation:bin.count",
                            value=2,
                            unit="crate",
                        ),
                        parameters={"minimum_count": 2},
                    ),
                ),
                preferences={preference_id: 2},
                mandate_id=mandate.id,
            )
            store.save_mandate(mandate)
            store.create_goal(goal)
            heart = WorldHeartV2(
                store, registry, DeterministicExecutiveBrainV2()
            )

            heart.run_cycle()

            self.assertEqual(4, store.get_goal(goal.id).preferences[preference_id])
            self.assertEqual(5, store.behavior_signal_count())
            store.close()

            plugin2 = module.load_plugin()
            registry2 = PluginRegistryV2()
            registry2.register(plugin2, root)
            store2 = WorldStore(store_path)
            self.addCleanup(store2.close)
            heart2 = WorldHeartV2(
                store2, registry2, DeterministicExecutiveBrainV2()
            )

            heart2.run_cycle()

            self.assertEqual(4, store2.get_goal(goal.id).preferences[preference_id])
            self.assertEqual(5, store2.behavior_signal_count())
        finally:
            sys.path.remove(str(root / "src"))
            for name in tuple(sys.modules):
                if name == "generated_learning" or name.startswith("generated_learning."):
                    del sys.modules[name]

    def test_model_failure_isolated_while_stable_goal_keeps_running(self) -> None:
        plugin, registry, store, _, goal = self._reference_system()
        del plugin
        stable = replace(
            goal,
            id="goal:stable",
            desired_effects=(
                replace(
                    goal.desired_effects[0],
                    id="already-zero",
                    condition=ConditionV1(
                        "gte", path="observation:bin.count", value=0, unit="crate"
                    ),
                ),
            ),
            priority=-1,
        )
        store.create_goal(stable)
        heart = WorldHeartV2(store, registry, _FailingBrain())

        passes = heart.run_cycle()

        by_goal = {item.goal_id: item for item in passes}
        self.assertEqual("degraded", by_goal[goal.id].status)
        self.assertEqual("monitoring", by_goal[stable.id].status)

    def test_meta_openai_compatible_model_is_the_world_brain(self) -> None:
        response = {
            "kind": "consult_specialist",
            "rationale": "warehouse specialist has the typed family",
            "specialist_id": "engine.reference-world.warehouse-specialist/v1",
            "query": {"effect_id": "reserve-minimum"},
            "proposed_action": None,
        }
        with _ModelServer(response, model="muse-spark-1.1") as server:
            plugin, registry, store, _, goal = self._reference_system()
            del plugin
            model = OpenAICompatibleV2Model(
                base_url=server.base_url,
                api_key="fixture-key",
                model_id="muse-spark-1.1",
                provider_id="meta-model-api",
            )
            heart = WorldHeartV2(store, registry, ModelExecutiveBrainV2(model))

            result = heart.run_once(goal.id)

            self.assertTrue(result.brain_called)
            self.assertTrue(result.specialist_called)
            self.assertEqual("meta-model-api", model.last_usage["provider"])
            self.assertEqual("muse-spark-1.1", model.last_usage["model"])
            self.assertEqual(1, len(server.requests))
            self.assertEqual(
                "json_schema",
                server.requests[0]["response_format"]["type"],
            )
            self.assertEqual(512, server.requests[0]["max_tokens"])

    def test_loopback_model_request_can_omit_authorization(self) -> None:
        response = {
            "kind": "wait",
            "rationale": "bounded local fixture",
            "specialist_id": None,
            "query": {},
            "proposed_action": None,
        }
        with _ModelServer(response, model="local-gemma-1b") as server:
            model = OpenAICompatibleV2Model(
                base_url=server.base_url,
                api_key=None,
                model_id="local-gemma-1b",
                provider_id="local-llama.cpp",
            )
            model.decide(
                {
                    "world": {"snapshot_id": "local", "revision": 1},
                    "effect_results": {},
                    "specialists": [],
                }
            )
        self.assertEqual([None], server.authorizations)

    def test_goal_compiler_binds_selected_manifest_schema_and_output_budget(self) -> None:
        response = {
            "mode": "maintain",
            "entity_scope": {"target_ids": [TARGET_ID]},
            "desired_effects": [
                {
                    "id": "reserve-minimum",
                    "capability_family": FAMILY,
                    "entity_selector": {"entity_ids": [ENTITY_ID]},
                    "condition": {
                        "op": "gte",
                        "path": "observation:bin.count",
                        "value": 4,
                        "unit": "crate",
                        "children": [],
                    },
                    "parameters": {"minimum_count": 4},
                    "description": "Keep four crates in reserve",
                }
            ],
            "constraints": [],
            "budgets": {},
            "stop_conditions": [],
            "priority": 1,
        }
        effect_schema = {
            "type": "object",
            "required": ["minimum_count"],
            "properties": {
                "minimum_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                }
            },
            "additionalProperties": False,
        }
        context = {
            "source_intent": "Keep four crates in reserve",
            "required_selection": {
                "target_id": TARGET_ID,
                "entity_id": ENTITY_ID,
                "capability_family": FAMILY,
                "effect_schema": effect_schema,
                "effect_measurements": ["bin.count"],
                "measurement_units": {"bin.count": "crate"},
            },
        }
        with _ModelServer(response, model="local-gemma-4b") as server:
            model = OpenAICompatibleV2Model(
                base_url=server.base_url,
                api_key=None,
                model_id="local-gemma-4b",
                provider_id="local-llama.cpp",
            )

            result = model.compile(context)

        self.assertEqual(4, result["desired_effects"][0]["parameters"]["minimum_count"])
        request = server.requests[0]
        self.assertEqual(1_024, request["max_tokens"])
        schema = request["response_format"]["json_schema"]["schema"]
        effect = schema["properties"]["desired_effects"]["items"]
        self.assertEqual(effect_schema, effect["properties"]["parameters"])
        self.assertEqual(
            {"const": {"entity_ids": [ENTITY_ID]}},
            effect["properties"]["entity_selector"],
        )

    @unittest.skipUnless(
        os.environ.get("META_MODEL_API_BASE_URL")
        and os.environ.get("META_MODEL_API_KEY")
        and os.environ.get("META_MODEL_ID"),
        "live Meta Model API credentials are not configured",
    )
    def test_live_meta_model_api_structured_brain_canary(self) -> None:
        model = OpenAICompatibleV2Model(
            base_url=os.environ["META_MODEL_API_BASE_URL"],
            api_key=os.environ["META_MODEL_API_KEY"],
            model_id=os.environ["META_MODEL_ID"],
            provider_id="meta-model-api",
        )
        decision = model.decide(
            {
                "contract": "engine.model-canary/v1",
                "world": {"snapshot_id": "canary", "revision": 1},
                "effect_results": {},
                "specialists": [],
            }
        )
        self.assertIn(decision["kind"], {"query_world", "wait", "complete", "abandon"})

    @unittest.skipUnless(
        os.environ.get("ENGINE_LOCAL_MODEL_BASE_URL")
        and os.environ.get("ENGINE_LOCAL_MODEL_ID"),
        "live local structured model is not configured",
    )
    def test_live_local_gemma_is_the_engine_brain(self) -> None:
        _, _, _, _, goal = self._reference_system()
        model = OpenAICompatibleV2Model(
            base_url=os.environ["ENGINE_LOCAL_MODEL_BASE_URL"],
            api_key=None,
            model_id=os.environ["ENGINE_LOCAL_MODEL_ID"],
            provider_id="local-llama.cpp",
        )
        decision = ModelExecutiveBrainV2(model).decide(
            goal,
            {
                "world": {
                    "snapshot_id": "local-gemma-eval",
                    "revision": 1,
                    "entities": [],
                },
                "effect_results": {
                    "reserve-minimum": {"value": False, "evidence_ids": []}
                },
                "specialists": [
                    "engine.reference-world.warehouse-specialist/v1"
                ],
            },
        )
        self.assertIsNotNone(decision.kind)
        self.assertEqual("local-llama.cpp", model.last_usage["provider"])
        self.assertEqual(
            os.environ["ENGINE_LOCAL_MODEL_ID"], model.last_usage["model"]
        )

    def test_sqlite_runtime_lease_excludes_a_second_process(self) -> None:
        path = self.base / "lease.sqlite3"
        first = RuntimeLease(path, ttl_seconds=5).acquire()
        self.addCleanup(first.close)

        with self.assertRaises(LeaseHeldError):
            RuntimeLease(path, ttl_seconds=5).acquire()

        first.close()
        second = RuntimeLease(path, ttl_seconds=5).acquire()
        second.close()

    def test_runtime_lease_loss_invokes_the_execution_stop_boundary(self) -> None:
        path = self.base / "lost-lease.sqlite3"
        stopped = threading.Event()
        lease = RuntimeLease(
            path, ttl_seconds=0.3, on_lost=stopped.set
        ).acquire()
        self.addCleanup(lease.close)
        with sqlite3.connect(path) as connection:
            connection.execute(
                "DELETE FROM runtime_leases_v1 WHERE lease_name='engine-runtime'"
            )
        self.assertTrue(stopped.wait(2.0))
        self.assertTrue(lease.lost)

    def test_heart_and_runtime_have_no_concrete_plugin_import_or_branch(self) -> None:
        roots = (Path("src/engine"), Path("packages/engine-runtime/src"))
        forbidden = ("engine_homey", "engine_context", "engine_reference_world")
        for root in roots:
            for path in root.rglob("*.py"):
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
                imports = [
                    node.module or ""
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                ] + [
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                ]
                self.assertFalse(
                    any(item.startswith(forbidden) for item in imports), path
                )
                self.assertNotIn('plugin_id == "engine.homey"', source, path)

        for path in Path("plugins").glob("*/src/**/*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = [
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            ] + [
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            ]
            self.assertFalse(
                any(item == "engine" or item.startswith("engine.") for item in imports),
                path,
            )

    def _reference_system(self):
        plugin = create_plugin(self.base / "warehouse.sqlite3")
        self.addCleanup(plugin.providers[0].store.close)
        registry = PluginRegistryV2()
        registry.register(plugin, "plugins/reference-world")
        store = WorldStore(self.base / "engine.sqlite3")
        self.addCleanup(store.close)
        now = datetime.now(UTC)
        mandate = StandingMandateV1(
            id="mandate:reference-learning",
            plugin_ids=(PLUGIN_ID,),
            target_ids=(TARGET_ID,),
            entity_ids=(ENTITY_ID,),
            capability_families=(FAMILY,),
            limits={},
            privacy_permissions=(),
            learning_permissions=("learning.low-risk",),
            valid_from=(now - timedelta(days=20)).isoformat(),
            valid_until=(now + timedelta(days=20)).isoformat(),
            manifest_versions={PLUGIN_ID: "0.2.0"},
            activated_by="owner",
        )
        goal = GoalSpecV2(
            id="goal:reference-learning",
            source_intent="Maintain the learned reserve target",
            mode=GoalModeV2.MAINTAIN,
            entity_scope={"target_ids": [TARGET_ID]},
            desired_effects=(
                DesiredEffectV1(
                    id="reserve-minimum",
                    capability_family=FAMILY,
                    entity_selector={"entity_ids": [ENTITY_ID]},
                    condition=ConditionV1(
                        "gte", path="observation:bin.count", value=3, unit="crate"
                    ),
                    parameters={"minimum_count": 3},
                ),
            ),
            preferences={PREFERENCE_ID: 3},
            mandate_id=mandate.id,
        )
        store.save_mandate(mandate)
        store.create_goal(goal)
        heart = WorldHeartV2(store, registry, DeterministicExecutiveBrainV2())
        return plugin, registry, store, heart, goal


class _OneBatchExperience:
    id = "warehouse-experience"
    plugin_id = PLUGIN_ID

    def __init__(self, signal: BehaviorSignalV1):
        self.signal = signal

    def read(self, after_cursor: str | None, limit: int) -> BehaviorBatchV1:
        del limit
        if after_cursor is not None:
            return BehaviorBatchV1(after_cursor, ())
        return BehaviorBatchV1("1", (self.signal,))


class _FailingBrain:
    id = "test.failing-model/v1"

    def decide(self, goal: Any, context: dict[str, object]) -> Any:
        del goal, context
        raise RuntimeError("fixture provider is down")


class _ModelServer:
    def __init__(self, decision: dict[str, Any], *, model: str):
        self.decision = decision
        self.model = model
        self.requests: list[dict[str, Any]] = []
        self.authorizations: list[str | None] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                owner.requests.append(json.loads(self.rfile.read(length)))
                owner.authorizations.append(self.headers.get("Authorization"))
                payload = json.dumps(
                    {
                        "model": owner.model,
                        "choices": [
                            {"message": {"content": json.dumps(owner.decision)}}
                        ],
                        "usage": {"input_tokens": 10, "output_tokens": 5},
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    def __enter__(self) -> Self:
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
