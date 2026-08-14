from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from engine_context.plugin import (
    ContextStore,
    ContextWorldProvider,
    ExplicitLocationProvider,
    MacOSCoreLocationProvider,
)
from engine_context.sun import solar_position
from engine_sdk import EvidenceGrade, load_static_manifest


class _Weather:
    source = "fixture.weather/v1"

    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

    def current(self, latitude: float, longitude: float):
        self.calls.append((latitude, longitude))
        return {
            "temperature_c": 17.5,
            "cloud_cover_pct": 80,
            "precipitation_mm": 0.2,
            "observed_at": "2026-08-10T12:00:00+00:00",
        }


class ContextPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-context-")
        self.base = Path(self.temporary.name)
        self.manifest = load_static_manifest(Path(__file__).resolve().parents[1])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _store(self) -> ContextStore:
        store = ContextStore(self.base / "context.sqlite3")
        self.addCleanup(store.close)
        return store

    def test_location_is_not_transmitted_without_explicit_permission(self) -> None:
        weather = _Weather()
        provider = ContextWorldProvider(
            self._store(),
            self.manifest,
            ExplicitLocationProvider(52.37, 4.89),
            weather,
            share_location_with_weather=False,
            clock=lambda: datetime(2026, 8, 10, 14, tzinfo=UTC),
        )

        observed = provider.observe()

        self.assertEqual([], weather.calls)
        self.assertFalse(observed.coverage["location_transmitted"])
        weather_values = [
            item for item in observed.observations
            if item.entity_id == "context:weather"
        ]
        self.assertTrue(weather_values)
        self.assertTrue(
            all(item.evidence_grade is EvidenceGrade.UNKNOWN for item in weather_values)
        )

    def test_permissioned_weather_preserves_provider_provenance(self) -> None:
        weather = _Weather()
        provider = ContextWorldProvider(
            self._store(),
            self.manifest,
            ExplicitLocationProvider(52.37, 4.89),
            weather,
            share_location_with_weather=True,
        )

        observed = provider.observe()

        self.assertEqual([(52.37, 4.89)], weather.calls)
        temperature = next(
            item for item in observed.observations
            if item.property == "weather.temperature_c"
        )
        self.assertEqual(17.5, temperature.value)
        self.assertEqual("fixture.weather/v1", temperature.source)
        self.assertEqual(EvidenceGrade.OBSERVED, temperature.evidence_grade)

    def test_missing_location_is_unknown_not_false(self) -> None:
        provider = ContextWorldProvider(
            self._store(),
            self.manifest,
            ExplicitLocationProvider(None, None),
            _Weather(),
            share_location_with_weather=True,
        )

        observed = provider.observe()

        latitude = next(
            item for item in observed.observations
            if item.property == "location.latitude"
        )
        self.assertIsNone(latitude.value)
        self.assertEqual(EvidenceGrade.UNKNOWN, latitude.evidence_grade)
        self.assertEqual("UNKNOWN", observed.coverage["location"])

    def test_macos_provider_never_calls_reader_before_os_permission(self) -> None:
        calls = 0

        def reader():
            nonlocal calls
            calls += 1
            return 52.0, 5.0

        provider = MacOSCoreLocationProvider(
            reader, os_permission_confirmed=False
        )

        self.assertIsNone(provider.location())
        self.assertEqual(0, calls)

    def test_same_minute_reobserve_reuses_context_revision(self) -> None:
        clock = [datetime(2026, 8, 14, 12, 24, 10, tzinfo=UTC)]
        provider = ContextWorldProvider(
            self._store(),
            self.manifest,
            ExplicitLocationProvider(None, None),
            None,
            share_location_with_weather=False,
            clock=lambda: clock[0],
        )
        first = provider.observe()
        clock[0] = datetime(2026, 8, 14, 12, 24, 40, tzinfo=UTC)
        same_minute = provider.observe()
        clock[0] = datetime(2026, 8, 14, 12, 25, 5, tzinfo=UTC)
        next_minute = provider.observe()

        self.assertEqual(first.revision, same_minute.revision)
        self.assertEqual(first.revision + 1, next_minute.revision)
        self.assertNotEqual(
            first.semantic_fingerprint(), next_minute.semantic_fingerprint()
        )

    def test_noaa_solar_elevation_matches_ephemeris_fixtures(self) -> None:
        fixtures = (
            # NREL SPA Reda & Andreas 2004, Boulder; NOAA refraction stays
            # inside the ±0.5° C1 gate of the published 39.888° geometric
            # elevation.
            (
                39.742476,
                -105.1786,
                datetime(2003, 10, 17, 19, 30, 30, tzinfo=UTC),
                39.888,
            ),
            # Local solar noon near the March equinox at the equator.
            (0.0, 0.0, datetime(2024, 3, 20, 12, 7, tzinfo=UTC), 90.0),
            # Midwinter polar night at the North Pole.
            (90.0, 0.0, datetime(2024, 12, 21, 12, tzinfo=UTC), -23.4),
        )
        for latitude, longitude, when, expected in fixtures:
            elevation, above, phase = solar_position(latitude, longitude, when)
            with self.subTest(when=when.isoformat()):
                self.assertLessEqual(abs(elevation - expected), 0.5)
                self.assertEqual(above, elevation >= 0.0)
                if elevation >= 0.0:
                    self.assertEqual("day", phase)
                elif elevation >= -6.0:
                    self.assertEqual("civil_twilight", phase)
                else:
                    self.assertEqual("night", phase)

    def test_sun_observations_are_unknown_without_coordinates(self) -> None:
        provider = ContextWorldProvider(
            self._store(),
            self.manifest,
            ExplicitLocationProvider(None, None),
            _Weather(),
            share_location_with_weather=True,
        )
        observed = provider.observe()
        sun = [
            item for item in observed.observations
            if item.property.startswith("sun.")
        ]
        self.assertEqual(3, len(sun))
        self.assertTrue(all(item.evidence_grade is EvidenceGrade.UNKNOWN for item in sun))
        self.assertTrue(all(item.value is None for item in sun))
        self.assertEqual("UNKNOWN", observed.coverage["sun"])

    def test_sun_observations_are_derived_when_location_is_known(self) -> None:
        provider = ContextWorldProvider(
            self._store(),
            self.manifest,
            ExplicitLocationProvider(52.37, 4.89),
            _Weather(),
            share_location_with_weather=False,
            clock=lambda: datetime(2026, 8, 10, 14, tzinfo=UTC),
        )
        observed = provider.observe()
        elevation = next(
            item for item in observed.observations
            if item.property == "sun.elevation_deg"
        )
        phase = next(
            item for item in observed.observations
            if item.property == "sun.phase"
        )
        self.assertEqual(EvidenceGrade.DERIVED, elevation.evidence_grade)
        self.assertEqual("derived", observed.coverage["sun"])
        self.assertIn(phase.value, {"day", "civil_twilight", "night"})
        self.assertIn("sun.elevation_deg", self.manifest.observation_types)


if __name__ == "__main__":
    unittest.main()
