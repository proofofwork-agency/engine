from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from engine_homey.brains import ClimateBrain, EnergyBrain
from engine_homey.charter import HomeCharterCompiler
from engine_homey.config import DeviceBinding
from engine_homey.store import HomeOpsStore
from engine_homey.target import SET_COVER, SET_LIGHT, SET_THERMOSTAT, HomeyTarget
from fakes import MemoryHomeyTransport, _cap, fixture_config, fixture_house

from engine.models import BrainContext, Goal


class SpecialistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-homey-specialists-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_climate_brain_uses_cover_before_thermostat_without_zone_code(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        cover = DeviceBinding(
            id="cover-1",
            alias="zone_1_cover",
            zone="zone_1",
            kind="cover",
            control=("windowcoverings_set",),
            capability_map={"position": "windowcoverings_set"},
            limits={"position": (0.0, 1.0)},
        )
        thermostat = DeviceBinding(
            id="thermostat-1",
            alias="zone_1_thermostat",
            zone="zone_1",
            kind="thermostat",
            control=("target_temperature",),
            capability_map={"target": "target_temperature"},
            limits={"temperature_c": (15.0, 28.0)},
        )
        config = replace(config, devices=config.devices + (cover, thermostat))
        zones, devices = fixture_house(1)
        devices["sensor-1"]["capabilitiesObj"]["measure_temperature"]["value"] = 27.0
        updated = devices["sensor-1"]["capabilitiesObj"]["measure_temperature"][
            "lastUpdated"
        ]
        devices["cover-1"] = {
            "id": "cover-1",
            "name": "Cover",
            "zone": "zone-1",
            "class": "cover",
            "available": True,
            "capabilities": ["windowcoverings_set"],
            "capabilitiesObj": {
                "windowcoverings_set": _cap(
                    "windowcoverings_set", 1.0, updated, "number", setable=True
                )
            },
        }
        devices["thermostat-1"] = {
            "id": "thermostat-1",
            "name": "Thermostat",
            "zone": "zone-1",
            "class": "thermostat",
            "available": True,
            "capabilities": ["target_temperature"],
            "capabilitiesObj": {
                "target_temperature": _cap(
                    "target_temperature",
                    24.0,
                    updated,
                    "number",
                    units="°C",
                    setable=True,
                )
            },
        }
        transport = MemoryHomeyTransport(zones, devices)
        store = HomeOpsStore(config.plugin_database)
        charter_text = "Houd de temperatuur onder 25 C. Gebruik passieve koeling voor actieve koeling."
        charter = HomeCharterCompiler().compile(charter_text, devices=config.devices)
        store.save_charter(charter, charter_text)
        target = HomeyTarget(config, store, transport)
        brain = ClimateBrain()

        first = target.observe()
        advice = brain.advise(self._context(first, target, "climate"))
        self.assertEqual(SET_COVER, advice.suggested_action.capability_id)
        self.assertEqual(0.0, advice.suggested_action.arguments["position"])
        self.assertTrue(target.execute(advice.suggested_action).succeeded)

        second = target.observe()
        advice = brain.advise(self._context(second, target, "climate"))
        self.assertEqual(SET_THERMOSTAT, advice.suggested_action.capability_id)
        self.assertEqual(24.0, advice.suggested_action.arguments["temperature_c"])
        store.close()

    def test_energy_brain_sheds_lowest_priority_allowlisted_load(self) -> None:
        config = fixture_config(self.base, zone_count=1)
        zones, devices = fixture_house(1)
        devices["light-1"]["capabilitiesObj"]["onoff"]["value"] = True
        devices["light-1"]["capabilitiesObj"]["dim"]["value"] = 1.0
        devices["light-1"]["capabilitiesObj"]["measure_power"]["value"] = 12.0
        transport = MemoryHomeyTransport(zones, devices)
        store = HomeOpsStore(config.plugin_database)
        charter_text = "Beperk het totale energieverbruik van het huis tot 5 W."
        charter = HomeCharterCompiler().compile(charter_text, devices=config.devices)
        store.save_charter(charter, charter_text)
        target = HomeyTarget(config, store, transport)
        snapshot = target.observe()

        advice = EnergyBrain().advise(self._context(snapshot, target, "energy"))

        self.assertEqual(SET_LIGHT, advice.suggested_action.capability_id)
        self.assertEqual(
            {"alias": "zone_1_main_light", "on": False},
            advice.suggested_action.arguments,
        )
        store.close()

    @staticmethod
    def _context(snapshot, target, domain: str) -> BrainContext:
        obligation = next(
            item
            for item in snapshot.state["obligations"]
            if item["domain"] == domain and item["status"] == "VIOLATED"
        )
        return BrainContext(
            goal=Goal("goal", "home", "maintain", {"charter": "active"}),
            snapshot=snapshot,
            capabilities=target.capabilities(),
            specialists=(),
            recent_experience=(),
            working_memory={},
            specialist_query={"obligation_id": obligation["id"]},
        )


if __name__ == "__main__":
    unittest.main()
