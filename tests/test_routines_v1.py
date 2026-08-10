from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from engine_sdk import (
    CapabilitySpecV2,
    ConditionV1,
    ControlLayer,
    DesiredEffectV1,
    EntityV1,
    EvidenceGrade,
    GoalModeV2,
    GoalSpecV2,
    InvocationModeV2,
    ObservationV1,
    PrivacyClass,
    RiskClass,
    RoutineSpecV1,
    RoutineStatus,
    RoutineTemplateSpecV1,
    ScopedConditionV1,
    WorldSnapshotV2,
)

from engine.routines_v1 import RoutineRuntimeV1
from engine.world_store import WorldStore


class RoutineRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-routines-")
        self.store = WorldStore(Path(self.temporary.name) / "engine.sqlite3")
        self.now = datetime(2026, 10, 25, 22, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_scoped_guards_are_plugin_neutral_and_fail_closed(self) -> None:
        for plugin_id, target_id, entity_id, family in (
            ("engine.homey", "home", "zone:one", "homey.lighting.zone-state"),
            ("example.warehouse", "warehouse", "aisle:one", "warehouse.lighting.zone-state"),
        ):
            with self.subTest(plugin_id=plugin_id):
                registry = _Registry(plugin_id, target_id, family)
                runtime = RoutineRuntimeV1(
                    self.store, registry, clock=lambda: self.now
                )
                routine, goal = _routine_goal(
                    suffix=plugin_id,
                    plugin_id=plugin_id,
                    target_id=target_id,
                    entity_id=entity_id,
                    family=family,
                    fingerprint=registry.fingerprint,
                )
                self.store.create_goal(goal)
                self.store.save_routine(routine)
                self.assertTrue(
                    any(
                        item["kind"] == "routine_created"
                        and item["payload"]["routine_id"] == routine.id
                        for item in self.store.events()
                    )
                )
                snapshot = _snapshot(
                    1, entity_id, target_id,
                    minute=1320, any_on=True,
                )
                allowed = runtime.evaluate(snapshot)[goal.id]
                self.assertTrue(allowed.allowed)

                stale = _snapshot(
                    2, entity_id, target_id,
                    minute=1320, any_on=True,
                    state_grade=EvidenceGrade.STALE,
                )
                uncertain = runtime.evaluate(stale)[goal.id]
                self.assertFalse(uncertain.allowed)
                self.assertEqual(RoutineStatus.GUARD_UNCERTAIN, uncertain.status)

                # Isolate the second parameterized fixture in the shared store.
                self.store.rollback_active_routine(
                    self.store.get_routine(routine.id), None, None,
                    reason="fixture complete",
                )

    def test_false_guard_is_dormant_and_equal_priority_conflict_blocks_both(self) -> None:
        registry = _Registry(
            "example.warehouse", "warehouse", "warehouse.lighting.zone-state"
        )
        runtime = RoutineRuntimeV1(self.store, registry, clock=lambda: self.now)
        first, first_goal = _routine_goal(
            "first", "example.warehouse", "warehouse", "aisle:one",
            "warehouse.lighting.zone-state", registry.fingerprint,
        )
        second, second_goal = _routine_goal(
            "second", "example.warehouse", "warehouse", "aisle:one",
            "warehouse.lighting.zone-state", registry.fingerprint,
        )
        second = replace(second, desired_state={"on": True})
        self.store.create_goal(first_goal)
        self.store.create_goal(second_goal)
        self.store.save_routine(first)
        self.store.save_routine(second)

        false_snapshot = _snapshot(
            1, "aisle:one", "warehouse", minute=1200, any_on=True
        )
        false_values = runtime.evaluate(false_snapshot)
        self.assertTrue(all(not item.allowed for item in false_values.values()))
        self.assertTrue(all(item.status is RoutineStatus.DORMANT for item in false_values.values()))

        conflict = runtime.evaluate(
            _snapshot(2, "aisle:one", "warehouse", minute=1320, any_on=True)
        )
        self.assertTrue(all(not item.allowed for item in conflict.values()))
        self.assertTrue(all(item.status is RoutineStatus.CONFLICTED for item in conflict.values()))

        self.store.save_routine(replace(second, priority=first.priority + 1))
        ordered = runtime.evaluate(
            _snapshot(3, "aisle:one", "warehouse", minute=1320, any_on=True)
        )
        self.assertTrue(ordered[second_goal.id].allowed)
        self.assertFalse(ordered[first_goal.id].allowed)

    def test_daily_occurrence_is_exactly_once_across_dst_fallback(self) -> None:
        registry = _Registry(
            "example.warehouse", "warehouse", "warehouse.lighting.zone-state"
        )
        runtime = RoutineRuntimeV1(self.store, registry, clock=lambda: self.now)
        routine, goal = _routine_goal(
            "dst", "example.warehouse", "warehouse", "aisle:one",
            "warehouse.lighting.zone-state", registry.fingerprint,
        )
        self.store.create_goal(goal)
        self.store.save_routine(routine)
        first = _snapshot(
            1, "aisle:one", "warehouse", minute=1320, any_on=True,
            local_iso="2026-10-25T22:00:00+02:00",
        )
        evaluation = runtime.evaluate(first)[goal.id]
        self.assertTrue(evaluation.allowed)
        runtime.note_result(
            evaluation,
            status="monitoring",
            snapshot_id=first.id,
            request_id=None,
            entity_id="aisle:one",
        )
        fallback = _snapshot(
            2, "aisle:one", "warehouse", minute=1320, any_on=True,
            local_iso="2026-10-25T22:00:00+01:00",
        )
        repeated = runtime.evaluate(fallback)[goal.id]
        self.assertFalse(repeated.allowed)
        self.assertIn("already handled", repeated.reason)

        # No snapshot ever has the missing spring-forward minute; it is skipped.
        spring = _snapshot(
            3, "aisle:one", "warehouse", minute=180, any_on=True,
            local_iso="2027-03-28T03:00:00+02:00",
        )
        self.assertFalse(runtime.evaluate(spring)[goal.id].allowed)


class _Registry:
    def __init__(self, plugin_id: str, target_id: str, family: str):
        self.plugin_id = plugin_id
        self.target_id = target_id
        self.family = family
        self.fingerprint = "fixture-fingerprint:" + plugin_id
        self.template = RoutineTemplateSpecV1(
            "lighting.daily-off/v1", plugin_id, family,
            {"type": "object"}, {"type": "object"}, {"type": "object"},
            70,
        )
        self.capability_value = CapabilitySpecV2(
            plugin_id + ".zone-state/v1", plugin_id, family, "1.0.0",
            "fixture", {}, {}, ControlLayer.SEMANTIC,
            InvocationModeV2.IMMEDIATE, RiskClass.LOW, PrivacyClass.LOCAL,
            True, 1000,
        )
        self.registered = SimpleNamespace(
            static_manifest=SimpleNamespace(
                fingerprint=self.fingerprint,
                version="1.0.0",
                routine_templates=(self.template,),
            )
        )

    def plugin(self, plugin_id: str):
        if plugin_id != self.plugin_id:
            raise KeyError(plugin_id)
        return self.registered

    def routine_template(self, plugin_id: str, template_id: str):
        return self.template if plugin_id == self.plugin_id and template_id == self.template.id else None

    def capability(self, target_id: str, family: str):
        return self.capability_value if target_id == self.target_id and family == self.family else None

    def routine_compiler(self, plugin_id: str, template_id: str):
        del plugin_id, template_id
        return None


def _routine_goal(
    suffix: str,
    plugin_id: str,
    target_id: str,
    entity_id: str,
    family: str,
    fingerprint: str,
) -> tuple[RoutineSpecV1, GoalSpecV2]:
    guard = ScopedConditionV1(
        "all",
        children=(
            ScopedConditionV1(
                "gte", {"entity_ids": ["context:local"]},
                "observation:time.minute_of_day", 1305, "minute",
            ),
            ScopedConditionV1(
                "lte", {"entity_ids": ["context:local"]},
                "observation:time.minute_of_day", 1335, "minute",
            ),
            ScopedConditionV1(
                "eq", {"entity_ids": [entity_id]},
                "observation:lighting.any_on", True,
            ),
        ),
    )
    goal_id = "goal:" + suffix
    goal = GoalSpecV2(
        goal_id, "fixture", GoalModeV2.MAINTAIN,
        {"entity_ids": [entity_id]},
        (
            DesiredEffectV1(
                "off", family, {"entity_ids": [entity_id]},
                ConditionV1(
                    "eq", path="observation:lighting.any_on", value=False
                ),
                {"on": False},
            ),
        ),
    )
    routine = RoutineSpecV1(
        "routine:" + suffix,
        "lighting.daily-off/v1",
        plugin_id,
        target_id,
        (entity_id,),
        guard,
        goal_id,
        {"kind": "daily"},
        300,
        70,
        RoutineStatus.ACTIVE,
        "lighting.zone-state",
        {"on": False},
        manifest_fingerprint=fingerprint,
    )
    return routine, goal


def _snapshot(
    revision: int,
    entity_id: str,
    target_id: str,
    *,
    minute: int,
    any_on: bool,
    state_grade: EvidenceGrade = EvidenceGrade.DERIVED,
    local_iso: str = "2026-10-25T22:00:00+02:00",
) -> WorldSnapshotV2:
    observed_at = datetime(2026, 10, 25, 20, 0, tzinfo=UTC).isoformat()
    entities = (
        EntityV1("context:local", "engine.context.local", "context.local", "fixture"),
        EntityV1(entity_id, target_id, "fixture.zone", "fixture"),
    )
    observations = (
        ObservationV1(
            f"time:{revision}", "context:local", "time.minute_of_day", minute,
            "fixture", observed_at, EvidenceGrade.DERIVED, unit="minute",
        ),
        ObservationV1(
            f"iso:{revision}", "context:local", "time.iso8601", local_iso,
            "fixture", observed_at, EvidenceGrade.OBSERVED,
        ),
        ObservationV1(
            f"state:{revision}", entity_id, "lighting.any_on", any_on,
            "fixture", observed_at, state_grade,
        ),
    )
    return WorldSnapshotV2(
        f"world:{revision}", revision, observed_at,
        {"engine.context.local": revision, target_id: revision},
        entities, (), observations, {},
    )


if __name__ == "__main__":
    unittest.main()
