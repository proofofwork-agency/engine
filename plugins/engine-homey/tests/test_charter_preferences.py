from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from engine_homey.charter import (
    CharterError,
    HomeCharterCompiler,
    PreferenceLearner,
    effective_desired,
)
from engine_homey.store import HomeOpsStore
from engine_homey.target import HomeyTarget
from fakes import MemoryHomeyTransport, fixture_config, fixture_house


class CharterPreferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-homey-charter-")
        self.base = Path(self.temporary.name)
        self.config = fixture_config(self.base, zone_count=1)
        self.store = HomeOpsStore(self.config.plugin_database)
        self.text = (
            "Verlicht gebruikte zones wanneer het donker is tussen 50 en 100 lux, "
            "onder 15 W en maximaal 60%. Beheer energiezuinig en gebruik passieve koeling."
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_compiler_produces_versioned_schema_valid_policy_data(self) -> None:
        charter = HomeCharterCompiler().compile(self.text, devices=self.config.devices)
        lighting = next(
            item for item in charter["rules"] if item["domain"] == "lighting"
        )
        self.assertEqual(
            {"min": 50.0, "max": 100.0}, lighting["desired"]["illuminance_lux"]
        )
        self.assertEqual(15.0, lighting["desired"]["power_w"]["max"])
        self.assertEqual(0.6, lighting["desired"]["light"]["brightness_max"])
        self.assertTrue(charter["version_id"].startswith("charter_"))
        with self.assertRaises(CharterError):
            HomeCharterCompiler().compile("Maak het gezellig")

    def test_compiler_constrains_rules_to_explicit_configured_zones(self) -> None:
        charter = HomeCharterCompiler().compile(
            self.text,
            zone_aliases=("second_floor_hall", "kitchen", "second_floor_hall"),
            devices=self.config.devices,
        )

        self.assertTrue(charter["rules"])
        self.assertTrue(
            all(
                rule["scope"]["zones"] == ["kitchen", "second_floor_hall"]
                for rule in charter["rules"]
            )
        )

    def test_direct_correction_versions_charter_and_changes_equivalent_decision_bound(
        self,
    ) -> None:
        charter = HomeCharterCompiler().compile(self.text, devices=self.config.devices)
        self.store.save_charter(charter, self.text)
        lighting = next(
            item for item in charter["rules"] if item["domain"] == "lighting"
        )
        before = effective_desired(
            charter,
            lighting,
            zone="zone_1",
            observed_at="2026-08-10T23:30:00+02:00",
        )

        result = PreferenceLearner(
            self.store,
            clock=lambda: datetime(2026, 8, 10, 21, 30, tzinfo=UTC),
        ).apply_correction(
            "Na 23:00 is dit te fel",
            zone="zone_1",
            context={"brightness": 0.35},
        )

        patched = result["charter"]
        patched_rule = next(
            item for item in patched["rules"] if item["domain"] == "lighting"
        )
        after = effective_desired(
            patched,
            patched_rule,
            zone="zone_1",
            observed_at="2026-08-10T23:30:00+02:00",
        )
        other_zone = effective_desired(
            patched,
            patched_rule,
            zone="zone_2",
            observed_at="2026-08-10T23:30:00+02:00",
        )
        self.assertEqual(0.6, before["light"]["brightness_max"])
        self.assertEqual(0.35, after["light"]["brightness_max"])
        self.assertEqual(0.6, other_zone["light"]["brightness_max"])
        self.assertNotEqual(charter["version_id"], patched["version_id"])
        evidence = self.store.preferences()[0]
        self.assertEqual("OBSERVED", evidence["grade"])
        self.assertEqual("direct_user_correction", evidence["source"])
        self.assertEqual(0.35, evidence["patch"]["new_brightness_max"])

        zones, devices = fixture_house(1)
        target = HomeyTarget(
            self.config,
            self.store,
            MemoryHomeyTransport(zones, devices),
            clock=lambda: datetime(
                2026, 8, 10, 23, 30, tzinfo=timezone(timedelta(hours=2))
            ),
        )
        snapshot = target.observe()
        obligation = next(
            item
            for item in snapshot.state["obligations"]
            if item["domain"] == "lighting" and item["status"] == "VIOLATED"
        )
        context = BrainContext(
            goal=Goal("goal", "home", "maintain", {"charter": "active"}),
            snapshot=snapshot,
            capabilities=target.capabilities(),
            specialists=(),
            recent_experience=(),
            working_memory={},
            specialist_query={"obligation_id": obligation["id"]},
        )
        advice = LightingBrain().advise(context)
        self.assertLessEqual(advice.suggested_action.arguments["brightness"], 0.35)

    def test_unexplained_manual_override_is_inferred_and_does_not_patch(self) -> None:
        charter = HomeCharterCompiler().compile(self.text, devices=self.config.devices)
        self.store.save_charter(charter, self.text)
        evidence_id = PreferenceLearner(self.store).record_manual_override(
            {"alias": "zone_1_main_light", "capability": "dim", "value": 0.2}
        )
        self.assertEqual(charter, self.store.active_charter())
        evidence = next(
            item for item in self.store.preferences() if item["id"] == evidence_id
        )
        self.assertEqual("INFERRED", evidence["grade"])
        self.assertIsNone(evidence["patch"])


if __name__ == "__main__":
    unittest.main()
from engine_homey.brains import LightingBrain

from engine.models import BrainContext, Goal
