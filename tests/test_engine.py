from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from engine.brains import (
    AxisNavigationBrain,
    FileStructureBrain,
    GridNavigationBrain,
    RuleExecutiveBrain,
)
from engine.catalog import Catalog, CatalogError, EnginePlugin
from engine.heart import Heart
from engine.experiment import _engine_metrics
from engine.models import (
    BrainDecision,
    BrainManifest,
    CapabilitySpec,
    DecisionKind,
    Goal,
    InvocationMode,
    PluginManifest,
    SpecialistAdvice,
    ToolCall,
    ToolResult,
    WorldSnapshot,
)
from engine.store import EngineStore
from engine.providers import LlamaCppDecisionModel
from engine.worlds import FilesystemTarget, GridTarget


class EnginePrototypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-tests-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _heart(self, store: EngineStore, *targets, navigations=None) -> Heart:
        navigations = tuple(navigations or (GridNavigationBrain(),))
        catalog = Catalog()
        filesystem_targets = tuple(
            target for target in targets if isinstance(target, FilesystemTarget)
        )
        grid_targets = tuple(target for target in targets if isinstance(target, GridTarget))
        if filesystem_targets:
            catalog.register(
                EnginePlugin(
                    PluginManifest("engine.filesystem", "Filesystem plugin"),
                    targets=filesystem_targets,
                    specialists=(FileStructureBrain(),),
                )
            )
        if grid_targets:
            catalog.register(
                EnginePlugin(
                    PluginManifest("engine.spatial-grid", "Spatial grid plugin"),
                    targets=grid_targets,
                    specialists=navigations,
                )
            )
        return Heart(store, RuleExecutiveBrain(), catalog)

    def test_filesystem_goal_closes_through_general_specialist_tool_loop(self) -> None:
        store = EngineStore(self.base / "engine.db")
        target = FilesystemTarget("files", self.base / "files")
        target.seed({"inbox/a.txt": "a", "inbox/b.md": "b"})
        goal = Goal(
            id="organize",
            target_id="files",
            instruction="Organize both files",
            success_spec={
                "moves": [
                    {"source": "inbox/a.txt", "destination": "archive/text/a.txt"},
                    {"source": "inbox/b.md", "destination": "archive/markdown/b.md"},
                ]
            },
        )
        heart = self._heart(store, target)
        heart.register_goal(goal)

        result = heart.run(goal.id)

        self.assertEqual("completed", result.goal.status)
        self.assertTrue(target.goal_satisfied(goal, target.observe()))
        events = store.all_events(goal.id)
        self.assertIn("specialist_result", {event.kind for event in events})
        tool_events = [event for event in events if event.kind == "tool_result"]
        self.assertGreaterEqual(len(tool_events), 4)
        self.assertTrue(all(event.payload["result"]["succeeded"] for event in tool_events))
        store.close()

    def test_grid_replans_after_observed_partial_failure(self) -> None:
        store = EngineStore(self.base / "engine.db")
        target = GridTarget.default("grid", self.base / "grid.json")
        goal = Goal(
            id="navigate",
            target_id="grid",
            instruction="Get the key and reach the target",
            success_spec={"requires": ["key"], "target": [3, 2]},
        )
        heart = self._heart(store, target)
        heart.register_goal(goal)

        result = heart.run(goal.id)

        self.assertEqual("completed", result.goal.status)
        failures = [
            event
            for event in store.all_events(goal.id)
            if event.kind == "tool_result" and not event.payload["result"]["succeeded"]
        ]
        self.assertEqual(1, len(failures))
        self.assertTrue(failures[0].payload["result"]["partial"])
        self.assertEqual([[1, 0]], target.observe().state["known_blocked"])
        partial_receipts = [
            event
            for event in store.all_events(goal.id)
            if event.kind == "invocation" and event.payload["state"] == "partial"
        ]
        self.assertEqual(1, len(partial_receipts))
        store.close()

    def test_goal_working_memory_and_experience_survive_process_restart(self) -> None:
        store_path = self.base / "engine.db"
        target_path = self.base / "grid.json"
        store = EngineStore(store_path)
        target = GridTarget.default("grid", target_path)
        goal = Goal(
            id="restartable",
            target_id="grid",
            instruction="Get the key and reach the target",
            success_spec={"requires": ["key"], "target": [3, 2]},
        )
        first_heart = self._heart(store, target)
        first_heart.register_goal(goal)

        first = first_heart.run(goal.id, step_limit=1)
        self.assertEqual("active", first.goal.status)
        self.assertIn("specialist_results", store.load_memory(goal.id))
        event_count = len(store.all_events(goal.id))
        store.close()

        restarted_store = EngineStore(store_path)
        restarted_target = GridTarget("grid", target_path)
        restarted_heart = self._heart(restarted_store, restarted_target)
        result = restarted_heart.run(goal.id)

        self.assertEqual("completed", result.goal.status)
        self.assertGreater(len(restarted_store.all_events(goal.id)), event_count)
        self.assertNotIn("specialist_results", restarted_store.load_memory(goal.id))
        self.assertIsNotNone(restarted_store.latest_snapshot(goal.id))
        restarted_store.close()

    def test_specialist_brain_can_be_replaced_without_heart_changes(self) -> None:
        for index, navigation in enumerate(
            (GridNavigationBrain(), AxisNavigationBrain()), start=1
        ):
            with self.subTest(specialist=navigation.manifest.name):
                store = EngineStore(self.base / f"engine-{index}.db")
                target = GridTarget.default(f"grid-{index}", self.base / f"grid-{index}.json")
                goal = Goal(
                    id=f"swap-{index}",
                    target_id=f"grid-{index}",
                    instruction="Get the key and reach the target",
                    success_spec={"requires": ["key"], "target": [3, 2]},
                )
                heart = self._heart(store, target, navigations=(navigation,))
                heart.register_goal(goal)
                result = heart.run(goal.id)
                self.assertEqual("completed", result.goal.status)
                used = {
                    event.source
                    for event in store.all_events(goal.id)
                    if event.kind == "specialist_result"
                }
                self.assertIn(navigation.manifest.qualified_id, used)
                store.close()

    def test_brain_cannot_self_certify_completion(self) -> None:
        class PrematureBrain:
            manifest = BrainManifest("premature", "Always claims completion")

            def decide(self, context):
                return BrainDecision(DecisionKind.COMPLETE, rationale="looks done")

        store = EngineStore(self.base / "engine.db")
        target = GridTarget.default("grid", self.base / "grid.json")
        goal = Goal(
            id="not-done",
            target_id="grid",
            instruction="Reach a distant target",
            success_spec={"target": [3, 2]},
            max_cycles=2,
        )
        catalog = Catalog()
        catalog.register(
            EnginePlugin(
                PluginManifest("engine.spatial-grid", "Spatial grid plugin"),
                targets=(target,),
            )
        )
        heart = Heart(store, PrematureBrain(), catalog)
        heart.register_goal(goal)

        result = heart.run(goal.id)

        self.assertEqual("budget_exhausted", result.goal.status)
        rejected = [
            event for event in store.all_events(goal.id) if event.kind == "completion_rejected"
        ]
        self.assertEqual(2, len(rejected))
        store.close()

    def test_catalog_is_versioned_persisted_and_rejects_duplicate_plugins(self) -> None:
        store = EngineStore(self.base / "engine.db")
        target = GridTarget.default("grid", self.base / "grid.json")
        catalog = Catalog()
        plugin = EnginePlugin(
            PluginManifest("engine.spatial-grid", "Spatial grid plugin"),
            targets=(target,),
            specialists=(GridNavigationBrain(),),
        )
        catalog.register(plugin)
        Heart(store, RuleExecutiveBrain(), catalog)

        self.assertEqual(1, catalog.generation)
        self.assertEqual(1, len(store.system_events()))
        self.assertEqual("catalog_changed", store.system_events()[0]["kind"])
        with self.assertRaises(CatalogError):
            catalog.register(plugin)
        store.close()

    def test_experience_routes_away_from_unhelpful_specialist(self) -> None:
        class BrokenNavigationBrain:
            manifest = BrainManifest(
                "a-broken-navigation",
                "Always proposes schema-invalid movement",
                supported_capabilities=(
                    "engine.spatial.step/v1",
                    "engine.spatial.pick-up/v1",
                ),
                plugin_id="engine.spatial-grid",
            )

            def advise(self, context):
                return SpecialistAdvice(
                    "Try an impossible direction",
                    ToolCall("engine.spatial.step/v1", {"direction": "diagonal"}),
                )

        store = EngineStore(self.base / "engine.db")
        target = GridTarget.default("grid", self.base / "grid.json")
        goal = Goal(
            id="learn-route",
            target_id="grid",
            instruction="Get the key and reach the target",
            success_spec={"requires": ["key"], "target": [3, 2]},
        )
        heart = self._heart(
            store,
            target,
            navigations=(BrokenNavigationBrain(), GridNavigationBrain()),
        )
        heart.register_goal(goal)

        first = heart.run(goal.id, step_limit=2)
        self.assertEqual("active", first.goal.status)
        store.close()

        restarted_store = EngineStore(self.base / "engine.db")
        restarted_target = GridTarget("grid", self.base / "grid.json")
        restarted = self._heart(
            restarted_store,
            restarted_target,
            navigations=(BrokenNavigationBrain(), GridNavigationBrain()),
        )
        before = len(restarted_store.all_events(goal.id))
        restarted.run(goal.id, step_limit=1)
        after_restart = restarted_store.all_events(goal.id)[before:]
        first_post_restart = next(
            event.source
            for event in after_restart
            if event.kind == "specialist_result"
        )
        self.assertEqual(
            "engine.spatial-grid.grid-navigation-brain/v1", first_post_restart
        )
        result = restarted.run(goal.id)
        self.assertEqual("completed", result.goal.status)
        consulted = [
            event.source
            for event in restarted_store.all_events(goal.id)
            if event.kind == "specialist_result"
        ]
        self.assertEqual(
            "engine.spatial-grid.a-broken-navigation/v1", consulted[0]
        )
        self.assertIn(
            "engine.spatial-grid.grid-navigation-brain/v1", consulted[1:]
        )
        outcome = [
            event.payload
            for event in restarted_store.all_events(goal.id)
            if event.kind == "brain_outcome"
            and event.payload["brain_id"]
            == "engine.spatial-grid.a-broken-navigation/v1"
        ]
        self.assertEqual(False, outcome[0]["effectful"])
        restarted_store.close()

        control_store = EngineStore(self.base / "control.db")
        control_target = GridTarget.default("control-grid", self.base / "control.json")
        control_goal = replace(goal, id="control", target_id="control-grid")
        control = self._heart(
            control_store,
            control_target,
            navigations=(BrokenNavigationBrain(), GridNavigationBrain()),
        )
        control.register_goal(control_goal)
        control.run(control_goal.id, step_limit=1)
        control_first = next(
            event.source
            for event in control_store.all_events(control_goal.id)
            if event.kind == "specialist_result"
        )
        self.assertEqual(
            "engine.spatial-grid.a-broken-navigation/v1", control_first
        )
        control_store.close()

    def test_causal_ids_join_brains_decisions_invocations_and_outcomes(self) -> None:
        store = EngineStore(self.base / "engine.db")
        target = GridTarget.default("grid", self.base / "grid.json")
        goal = Goal(
            id="causal",
            target_id="grid",
            instruction="Get the key and reach the target",
            success_spec={"requires": ["key"], "target": [3, 2]},
        )
        heart = self._heart(store, target)
        heart.register_goal(goal)
        self.assertEqual("completed", heart.run(goal.id).goal.status)

        events = store.all_events(goal.id)
        request_events = [event for event in events if event.kind == "brain_request"]
        requests = {event.payload["id"] for event in request_events}
        executive_requests = {
            event.payload["id"]
            for event in request_events
            if event.payload["purpose"] == "select next cognitive operator"
        }
        specialist_requests = {
            event.payload["id"]
            for event in request_events
            if event.payload["purpose"] == "resolve bounded cognitive impasse"
        }
        for event in request_events:
            if event.payload["id"] in specialist_requests:
                self.assertIn(event.payload["parent_request_id"], executive_requests)
        for event in events:
            if event.kind == "brain_result":
                self.assertIn(event.payload["request_id"], requests)
            elif event.kind == "executive_decision":
                self.assertIn(event.payload["brain_request_id"], requests)

        invocations: dict[str, list[dict]] = {}
        for event in events:
            if event.kind == "invocation":
                invocations.setdefault(event.payload["id"], []).append(event.payload)
        self.assertTrue(invocations)
        for lifecycle in invocations.values():
            self.assertEqual("requested", lifecycle[0]["state"])
            self.assertIn(lifecycle[-1]["state"], {"succeeded", "failed", "partial"})
            self.assertIn(lifecycle[0]["decision_request_id"], executive_requests)
            self.assertTrue(
                set(lifecycle[0]["based_on"]).issubset(specialist_requests)
            )

        for event in events:
            if event.kind == "tool_result":
                self.assertIn(event.payload["invocation_id"], invocations)
            elif event.kind == "brain_outcome":
                self.assertIn(event.payload["brain_request_id"], requests)
                if event.payload["invocation_id"] is not None:
                    self.assertIn(event.payload["invocation_id"], invocations)
        store.close()

    def test_non_immediate_capability_is_rejected_without_dispatch(self) -> None:
        class TaskGrid(GridTarget):
            executed = 0

            def capabilities(self):
                capabilities = super().capabilities()
                return (
                    replace(capabilities[0], invocation_mode=InvocationMode.TASK),
                    capabilities[1],
                )

            def execute(self, call):
                self.executed += 1
                return super().execute(call)

        class DirectBrain:
            manifest = BrainManifest("direct", "Direct test brain")

            def decide(self, context):
                return BrainDecision(
                    DecisionKind.USE_TOOL,
                    name="engine.spatial.step/v1",
                    arguments={"direction": "north"},
                )

        store = EngineStore(self.base / "engine.db")
        target = TaskGrid.default("grid", self.base / "grid.json")
        catalog = Catalog()
        catalog.register(
            EnginePlugin(
                PluginManifest("engine.spatial-grid", "Spatial grid plugin"),
                targets=(target,),
            )
        )
        goal = Goal(
            id="task-reject",
            target_id="grid",
            instruction="Move north",
            success_spec={"target": [0, 1]},
            max_cycles=1,
        )
        heart = Heart(store, DirectBrain(), catalog)
        heart.register_goal(goal)
        heart.run(goal.id)

        self.assertEqual(0, target.executed)
        result = next(
            event.payload["result"]
            for event in store.all_events(goal.id)
            if event.kind == "tool_result"
        )
        self.assertIn("NOT_SUPPORTED", result["error"])
        store.close()

    def test_redundant_consult_is_rejected_and_advice_stays_bounded(self) -> None:
        class RepeatingBrain:
            manifest = BrainManifest("repeating", "Repeats one consult once")

            def __init__(self):
                self.calls = 0

            def decide(self, context):
                self.calls += 1
                if self.calls <= 2:
                    return BrainDecision(
                        DecisionKind.CONSULT_BRAIN,
                        name="engine.spatial-grid.grid-navigation-brain/v1",
                    )
                advice = context.pending_advice[0]
                call = advice["advice"]["suggested_action"]
                return BrainDecision(
                    DecisionKind.USE_TOOL,
                    name=call["capability_id"],
                    arguments=call["arguments"],
                    based_on=(advice["brain_request_id"],),
                )

        store = EngineStore(self.base / "engine.db")
        target = GridTarget.default("grid", self.base / "grid.json")
        catalog = Catalog()
        catalog.register(
            EnginePlugin(
                PluginManifest("engine.spatial-grid", "Spatial grid plugin"),
                targets=(target,),
                specialists=(GridNavigationBrain(),),
            )
        )
        goal = Goal(
            id="dedupe",
            target_id="grid",
            instruction="Move north",
            success_spec={"target": [0, 1]},
            max_cycles=5,
        )
        heart = Heart(store, RepeatingBrain(), catalog, require_specialist_first=True)
        heart.register_goal(goal)
        result = heart.run(goal.id)

        self.assertEqual("completed", result.goal.status)
        events = store.all_events(goal.id)
        self.assertEqual(1, sum(event.kind == "specialist_result" for event in events))
        self.assertEqual(1, sum(event.kind == "decision_rejected" for event in events))
        self.assertLessEqual(
            len(store.load_memory(goal.id).get("specialist_results", [])), 1
        )
        store.close()

    def test_lost_ack_always_closes_invocation_as_unknown(self) -> None:
        class LostAckGrid(GridTarget):
            def __init__(self, *args, effect_before_raise: bool, **kwargs):
                self.effect_before_raise = effect_before_raise
                super().__init__(*args, **kwargs)

            def execute(self, call):
                if self.effect_before_raise:
                    super().execute(call)
                raise TimeoutError("lost acknowledgement")

        class DirectBrain:
            manifest = BrainManifest("direct", "Direct test brain")

            def decide(self, context):
                return BrainDecision(
                    DecisionKind.USE_TOOL,
                    name="engine.spatial.step/v1",
                    arguments={"direction": "north"},
                )

        for effect_before_raise in (False, True):
            with self.subTest(effect_before_raise=effect_before_raise):
                suffix = "after" if effect_before_raise else "before"
                target = LostAckGrid(
                    f"grid-{suffix}",
                    self.base / f"grid-{suffix}.json",
                    initial_state={
                        "revision": 0,
                        "bounds": [2, 2],
                        "position": [0, 0],
                        "blocked": [],
                        "known_blocked": [],
                        "items": {},
                        "inventory": [],
                    },
                    effect_before_raise=effect_before_raise,
                )
                store = EngineStore(self.base / f"{suffix}.db")
                catalog = Catalog()
                catalog.register(
                    EnginePlugin(
                        PluginManifest("engine.spatial-grid", "Spatial plugin"),
                        targets=(target,),
                    )
                )
                goal = Goal(
                    id=f"unknown-{suffix}",
                    target_id=f"grid-{suffix}",
                    instruction="Move north",
                    success_spec={"target": [0, 1]},
                    max_cycles=1,
                )
                heart = Heart(store, DirectBrain(), catalog)
                heart.register_goal(goal)
                result = heart.run(goal.id)
                states = [
                    event.payload["state"]
                    for event in store.all_events(goal.id)
                    if event.kind == "invocation"
                ]
                self.assertEqual(["requested", "unknown"], states)
                self.assertEqual(effect_before_raise, result.goal.status == "completed")
                store.close()

    def test_failed_adapter_output_preserves_original_error(self) -> None:
        class MissingSourceBrain:
            manifest = BrainManifest("missing-source", "Uses a missing file")

            def decide(self, context):
                return BrainDecision(
                    DecisionKind.USE_TOOL,
                    name="engine.fs.move-file/v1",
                    arguments={"source": "missing.txt", "destination": "x.txt"},
                )

        store = EngineStore(self.base / "engine.db")
        target = FilesystemTarget("files", self.base / "files")
        catalog = Catalog()
        catalog.register(
            EnginePlugin(
                PluginManifest("engine.filesystem", "Filesystem plugin"),
                targets=(target,),
            )
        )
        goal = Goal(
            id="missing",
            target_id="files",
            instruction="Move a missing file",
            success_spec={"moves": [{"source": "missing.txt", "destination": "x.txt"}]},
            max_cycles=1,
        )
        heart = Heart(store, MissingSourceBrain(), catalog)
        heart.register_goal(goal)
        heart.run(goal.id)
        error = next(
            event.payload["result"]["error"]
            for event in store.all_events(goal.id)
            if event.kind == "tool_result"
        )
        self.assertEqual("source is missing", error)
        store.close()

    def test_wrong_target_observation_is_never_persisted(self) -> None:
        class WrongTargetGrid(GridTarget):
            def observe(self):
                return replace(super().observe(), target_id="wrong-target")

        store = EngineStore(self.base / "engine.db")
        target = WrongTargetGrid.default("expected", self.base / "grid.json")
        catalog = Catalog()
        catalog.register(
            EnginePlugin(
                PluginManifest("engine.spatial-grid", "Spatial plugin"),
                targets=(target,),
            )
        )
        goal = Goal(
            id="wrong-observe",
            target_id="expected",
            instruction="Observe",
            success_spec={"target": [0, 1]},
        )
        heart = Heart(store, RuleExecutiveBrain(), catalog)
        heart.register_goal(goal)
        with self.assertRaisesRegex(ValueError, "observed target wrong-target"):
            heart.run(goal.id)
        self.assertIsNone(store.latest_snapshot(goal.id))
        store.close()

    def test_catalog_refresh_contracts_binding_and_honest_retrieval(self) -> None:
        class DynamicGrid(GridTarget):
            extra = False

            def capabilities(self):
                base = super().capabilities()
                if not self.extra:
                    return base
                return (
                    *base,
                    CapabilitySpec(
                        id="engine.spatial.scan/v1",
                        local_name="scan",
                        description="Scan the nearby cells",
                        input_schema={"type": "object"},
                    ),
                )

        target = DynamicGrid.default("grid", self.base / "grid.json")
        catalog = Catalog()
        catalog.register(
            EnginePlugin(
                PluginManifest("engine.spatial-grid", "Spatial plugin"),
                targets=(target,),
            )
        )
        self.assertEqual(2, len(catalog.capabilities("grid")))
        target.extra = True
        self.assertTrue(catalog.refresh())
        self.assertEqual(3, len(catalog.capabilities("grid")))
        with self.assertRaisesRegex(CatalogError, "does not match binding"):
            catalog.validate_call(
                "grid",
                ToolCall(
                    "engine.spatial.step/v1",
                    {"direction": "north"},
                    target_id="other",
                ),
            )

        target.manifest = replace(target.manifest, contract_version="other/v9")
        incompatible = Catalog()
        with self.assertRaisesRegex(CatalogError, "unsupported target contract"):
            incompatible.register(
                EnginePlugin(
                    PluginManifest("engine.spatial-grid", "Spatial plugin"),
                    targets=(target,),
                )
            )

        class ManyCapabilities(DynamicGrid):
            def capabilities(self):
                return tuple(
                    CapabilitySpec(
                        id=f"engine.decoy.capability-{index}/v1",
                        local_name=f"capability_{index}",
                        description=f"Unrelated affordance {index}",
                        input_schema={"type": "object"},
                    )
                    for index in range(40)
                )

        many = ManyCapabilities.default("many", self.base / "many.json")
        many_catalog = Catalog()
        many_catalog.register(
            EnginePlugin(
                PluginManifest("engine.spatial-grid", "Many plugin"),
                targets=(many,),
            )
        )
        search = many_catalog.search("many", ("nothing-matches",), limit=32)
        self.assertFalse(search.retrieval_sufficient)
        self.assertFalse(search.complete)
        self.assertEqual(40, search.omitted_count)
        self.assertEqual((), search.selections)

    def test_malformed_tool_result_never_leaves_requested(self) -> None:
        class MalformedGrid(GridTarget):
            return_value = None

            def execute(self, call):
                return self.return_value

        class DirectBrain:
            manifest = BrainManifest("direct", "Direct test brain")

            def decide(self, context):
                return BrainDecision(
                    DecisionKind.USE_TOOL,
                    name="engine.spatial.step/v1",
                    arguments={"direction": "north"},
                )

        malformed = (
            {"succeeded": True},
            ToolResult(True, False, error="contradiction"),
            ToolResult(False, True, error="changed but not partial"),
            ToolResult(False, False, error="partial without change", partial=True),
            ToolResult(False, False, output={"bad": object()}, error="bad output"),
        )
        for index, value in enumerate(malformed):
            with self.subTest(case=index):
                target = MalformedGrid.default(
                    f"malformed-{index}", self.base / f"malformed-{index}.json"
                )
                target.return_value = value
                store = EngineStore(self.base / f"malformed-{index}.db")
                catalog = Catalog()
                catalog.register(
                    EnginePlugin(
                        PluginManifest("engine.spatial-grid", "Spatial plugin"),
                        targets=(target,),
                    )
                )
                goal = Goal(
                    id=f"malformed-{index}",
                    target_id=f"malformed-{index}",
                    instruction="Move north",
                    success_spec={"target": [0, 1]},
                    max_cycles=1,
                )
                heart = Heart(store, DirectBrain(), catalog)
                heart.register_goal(goal)

                result = heart.run(goal.id)

                self.assertNotEqual("completed", result.goal.status)
                states = [
                    event.payload["state"]
                    for event in store.all_events(goal.id)
                    if event.kind == "invocation"
                ]
                self.assertEqual(["requested", "unknown"], states)
                tool_result = next(
                    event.payload["result"]
                    for event in store.all_events(goal.id)
                    if event.kind == "tool_result"
                )
                self.assertIn("contract", tool_result["error"])
                store.close()

    def test_completion_oracle_requires_exact_bool_and_records_failures(self) -> None:
        class OracleGrid(GridTarget):
            oracle_value = "false"

            def goal_satisfied(self, goal, snapshot):
                if isinstance(self.oracle_value, Exception):
                    raise self.oracle_value
                return self.oracle_value

        class WaitBrain:
            manifest = BrainManifest("wait", "Wait test brain")

            def decide(self, context):
                return BrainDecision(DecisionKind.WAIT, rationale="test")

        for index, value in enumerate(("false", RuntimeError("oracle offline"))):
            with self.subTest(case=index):
                target = OracleGrid.default(
                    f"oracle-{index}", self.base / f"oracle-{index}.json"
                )
                target.oracle_value = value
                store = EngineStore(self.base / f"oracle-{index}.db")
                catalog = Catalog()
                catalog.register(
                    EnginePlugin(
                        PluginManifest("engine.spatial-grid", "Spatial plugin"),
                        targets=(target,),
                    )
                )
                goal = Goal(
                    id=f"oracle-{index}",
                    target_id=f"oracle-{index}",
                    instruction="Wait",
                    success_spec={"target": [0, 0]},
                    max_cycles=1,
                )
                heart = Heart(store, WaitBrain(), catalog)
                heart.register_goal(goal)

                result = heart.run(goal.id)

                self.assertNotEqual("completed", result.goal.status)
                kinds = {event.kind for event in store.all_events(goal.id)}
                expected = "oracle_error" if isinstance(value, Exception) else "oracle_contract_error"
                self.assertIn(expected, kinds)
                self.assertNotIn("goal_completed", kinds)
                store.close()

    def test_same_revision_cannot_describe_different_state(self) -> None:
        previous = WorldSnapshot("target", 7, {"value": 1}, "before")

        class DriftTarget:
            manifest = replace(
                GridTarget.default("unused", self.base / "unused.json").manifest,
                id="target",
            )

            def observe(self):
                return WorldSnapshot("target", 7, {"value": 2}, "after")

        with self.assertRaisesRegex(ValueError, "changed without revision"):
            Heart._observe(DriftTarget(), previous=previous)

    def test_context_contains_only_target_relevant_specialists(self) -> None:
        class CaptureBrain:
            manifest = BrainManifest("capture", "Capture context")

            def __init__(self):
                self.specialists = ()

            def decide(self, context):
                self.specialists = context.specialists
                return BrainDecision(DecisionKind.ABANDON, rationale="captured")

        store = EngineStore(self.base / "scope.db")
        filesystem = FilesystemTarget("files", self.base / "files")
        grid = GridTarget.default("grid", self.base / "grid.json")
        catalog = Catalog()
        catalog.register(
            EnginePlugin(
                PluginManifest("engine.filesystem", "Filesystem plugin"),
                targets=(filesystem,),
                specialists=(FileStructureBrain(),),
            )
        )
        catalog.register(
            EnginePlugin(
                PluginManifest("engine.spatial-grid", "Spatial plugin"),
                targets=(grid,),
                specialists=(GridNavigationBrain(),),
            )
        )
        brain = CaptureBrain()
        heart = Heart(store, brain, catalog)
        goal = Goal(
            id="scope",
            target_id="files",
            instruction="Inspect filesystem",
            success_spec={"moves": []},
            max_cycles=1,
        )
        heart.register_goal(goal)
        heart.run(goal.id)

        self.assertEqual(
            ["engine.filesystem.structure-brain/v1"],
            [manifest.qualified_id for manifest in brain.specialists],
        )
        store.close()

    def test_refresh_order_is_canonical_and_specialist_replace_is_validated(self) -> None:
        class ReorderedGrid(GridTarget):
            reverse = False
            changed_description = False

            def capabilities(self):
                capabilities = list(super().capabilities())
                if self.changed_description:
                    capabilities[0] = replace(
                        capabilities[0], description="Semantically changed"
                    )
                self.reverse = not self.reverse
                return tuple(reversed(capabilities)) if self.reverse else tuple(capabilities)

        target = ReorderedGrid.default("grid", self.base / "ordered.json")
        original = GridNavigationBrain()
        catalog = Catalog()
        catalog.register(
            EnginePlugin(
                PluginManifest("engine.spatial-grid", "Spatial plugin"),
                targets=(target,),
                specialists=(original,),
            )
        )
        generation = catalog.generation
        fingerprint = catalog.fingerprint()
        self.assertFalse(catalog.refresh())
        self.assertFalse(catalog.refresh())
        self.assertEqual(generation, catalog.generation)
        self.assertEqual(fingerprint, catalog.fingerprint())
        self.assertEqual(
            sorted(capability.id for capability in catalog.capabilities("grid")),
            [capability.id for capability in catalog.capabilities("grid")],
        )
        target.changed_description = True
        self.assertTrue(catalog.refresh())
        self.assertFalse(catalog.refresh())

        class SpoofedBrain:
            manifest = replace(original.manifest, plugin_id="engine.other")

            def advise(self, context):
                return SpecialistAdvice("spoof")

        with self.assertRaisesRegex(CatalogError, "changed plugin owner"):
            catalog.replace_specialist(SpoofedBrain())
        self.assertIs(original, catalog.specialist(original.manifest.qualified_id))

    def test_provider_schema_constrains_cognitive_phase_and_handles_bad_responses(self) -> None:
        projection = {
            "specialists": [{"id": "engine.brain/v1"}],
            "capabilities": [{"id": "engine.tool/v1"}],
            "pending_advice": [{"brain_request_id": "advice-1"}],
        }
        schema = LlamaCppDecisionModel._decision_schema(projection)
        validator = Draft202012Validator(schema)
        validator.validate(
            {
                "kind": "use_tool",
                "name": "engine.tool/v1",
                "arguments": {},
                "rationale": "use bounded advice",
                "based_on": ["advice-1"],
            }
        )
        with self.assertRaises(ValidationError):
            validator.validate(
                {
                    "kind": "consult_brain",
                    "name": "engine.brain/v1",
                    "arguments": {},
                    "rationale": "repeat",
                    "based_on": [],
                }
            )
        self.assertNotIn("oneOf", schema)

        class Response:
            def __init__(self, value):
                self.value = value

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                import json

                return json.dumps(self.value).encode("utf-8")

        model = LlamaCppDecisionModel()
        with patch(
            "engine.providers.request.urlopen",
            return_value=Response({"model": "fake", "choices": []}),
        ):
            with self.assertRaisesRegex(RuntimeError, "no choices"):
                model.decide({})
        with self.assertRaisesRegex(RuntimeError, "exceeds byte budget"):
            LlamaCppDecisionModel(max_input_bytes=10).decide(
                {"snapshot": {"state": "x" * 100}}
            )

        bounded = LlamaCppDecisionModel(
            keep_session_history=True, history_turn_limit=2
        )
        valid_wait = {
            "model": "fake",
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"kind":"wait","name":"","arguments":{},'
                            '"rationale":"bounded","based_on":[]}'
                        )
                    }
                }
            ],
        }
        with patch(
            "engine.providers.request.urlopen", return_value=Response(valid_wait)
        ):
            for _ in range(5):
                bounded.decide({})
        self.assertEqual(4, len(bounded._history))

    def test_experiment_metrics_count_invocation_lifecycle_once(self) -> None:
        store = EngineStore(self.base / "metrics.db")
        target = FilesystemTarget("files", self.base / "metrics-files")
        target.seed({"inbox/a.txt": "a"})
        goal = Goal(
            id="metrics",
            target_id="files",
            instruction="Organize one file",
            success_spec={
                "moves": [
                    {"source": "inbox/a.txt", "destination": "archive/a.txt"}
                ]
            },
        )
        heart = self._heart(store, target)
        heart.register_goal(goal)
        heart.run(goal.id)

        metrics = _engine_metrics(
            store,
            goal,
            target,
            wall_ms=1.0,
            restart_boundary=None,
            initial_snapshot_hash="fixture",
        )

        events = store.all_events(goal.id)
        self.assertEqual(
            sum(event.kind == "tool_result" for event in events),
            metrics["tool_invocation_attempts"],
        )
        self.assertEqual(
            metrics["executive_attempts"],
            metrics["executive_succeeded"] + metrics["executive_failed"],
        )
        store.close()


if __name__ == "__main__":
    unittest.main()
