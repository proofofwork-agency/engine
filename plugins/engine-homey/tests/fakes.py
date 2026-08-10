from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterable
from copy import deepcopy
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Self
from urllib.parse import unquote

from engine_homey.config import DeviceBinding, HomeyConfig, ZoneBinding
from engine_homey.transport import HomeyTransportError


class MemoryHomeyTransport:
    def __init__(self, zones: dict[str, Any], devices: dict[str, Any]) -> None:
        self.zones = deepcopy(zones)
        self.devices = deepcopy(devices)
        self.reads = 0
        self.writes: list[tuple[str, str, object]] = []
        self.ack_without_effect: set[tuple[str, str]] = set()
        self.raise_on_write: set[tuple[str, str]] = set()
        self.disconnect_on_write_error = False
        self.connected = True
        self.freeze_lux = False

    def read_house(self) -> tuple[dict[str, Any], dict[str, Any]]:
        self.reads += 1
        if not self.connected:
            raise HomeyTransportError("fixture disconnected")
        return deepcopy(self.zones), deepcopy(self.devices)

    def set_capability(
        self, device_id: str, capability_id: str, value: bool | float | str
    ) -> dict[str, Any]:
        self.writes.append((device_id, capability_id, value))
        if (device_id, capability_id) in self.raise_on_write:
            if self.disconnect_on_write_error:
                self.connected = False
            raise HomeyTransportError("fixture lost acknowledgement")
        if (device_id, capability_id) in self.ack_without_effect:
            return {"ok": True}
        self.external_set(device_id, capability_id, value)
        return {"ok": True}

    def external_set(self, device_id: str, capability_id: str, value: object) -> None:
        device = self.devices[device_id]
        capability = device["capabilitiesObj"][capability_id]
        capability["value"] = value
        capability["lastUpdated"] = datetime.now(UTC).isoformat()
        self._cascade(device)

    def _cascade(self, device: dict[str, Any]) -> None:
        if device.get("class") != "light":
            return
        zone = device["zone"]
        on = bool(device["capabilitiesObj"]["onoff"]["value"])
        dim = float(device["capabilitiesObj"]["dim"]["value"])
        device["capabilitiesObj"]["measure_power"]["value"] = (
            round(dim * 12.0, 3) if on else 0.0
        )
        for candidate in self.devices.values():
            if candidate.get("zone") == zone and "measure_luminance" in candidate.get(
                "capabilitiesObj", {}
            ):
                if self.freeze_lux:
                    continue
                candidate["capabilitiesObj"]["measure_luminance"]["value"] = (
                    round(dim * 100.0, 3) if on else 5.0
                )
                candidate["capabilitiesObj"]["measure_luminance"]["lastUpdated"] = (
                    datetime.now(UTC).isoformat()
                )


class FakeEventSource:
    def __init__(self) -> None:
        self.callback: Callable[[object], None] | None = None
        self.device_ids: tuple[str, ...] = ()
        self.closed = False

    def subscribe(
        self, device_ids: Iterable[str], callback: Callable[[object], None]
    ) -> Callable[[], None]:
        self.device_ids = tuple(device_ids)
        self.callback = callback

        def close() -> None:
            self.closed = True
            self.callback = None

        return close

    def emit(self, duplicates: int = 1) -> None:
        for _ in range(duplicates):
            if self.callback is not None:
                self.callback({"untrusted": "payload"})


def fixture_house(zone_count: int = 3) -> tuple[dict[str, Any], dict[str, Any]]:
    now = datetime.now(UTC).isoformat()
    zones: dict[str, Any] = {}
    devices: dict[str, Any] = {}
    for index in range(1, zone_count + 1):
        zone_id = f"zone-{index}"
        zones[zone_id] = {"id": zone_id, "name": f"Zone {index}", "parent": None}
        light_id = f"light-{index}"
        devices[light_id] = {
            "id": light_id,
            "name": f"Main Light {index}",
            "zone": zone_id,
            "class": "light",
            "available": True,
            "capabilities": ["onoff", "dim", "measure_power"],
            "capabilitiesObj": {
                "onoff": _cap("onoff", False, now, "boolean", setable=True),
                "dim": _cap("dim", 0.0, now, "number", setable=True),
                "measure_power": _cap("measure_power", 0.0, now, "number", units="W"),
            },
        }
        sensor_id = f"sensor-{index}"
        devices[sensor_id] = {
            "id": sensor_id,
            "name": f"Room Sensor {index}",
            "zone": zone_id,
            "class": "sensor",
            "available": True,
            "capabilities": [
                "measure_luminance",
                "alarm_motion",
                "measure_temperature",
            ],
            "capabilitiesObj": {
                "measure_luminance": _cap(
                    "measure_luminance", 5.0, now, "number", units="lx"
                ),
                "alarm_motion": _cap("alarm_motion", True, now, "boolean"),
                "measure_temperature": _cap(
                    "measure_temperature", 21.0, now, "number", units="°C"
                ),
            },
        }
    return zones, devices


def fixture_config(
    base: Path,
    *,
    mode: str = "act",
    armed: bool = True,
    zone_count: int = 3,
    address: str = "http://127.0.0.1",
) -> HomeyConfig:
    zones = tuple(
        ZoneBinding(f"zone-{index}", f"zone_{index}")
        for index in range(1, zone_count + 1)
    )
    devices: list[DeviceBinding] = []
    for index in range(1, zone_count + 1):
        devices.extend(
            (
                DeviceBinding(
                    id=f"light-{index}",
                    alias=f"zone_{index}_main_light",
                    zone=f"zone_{index}",
                    kind="light",
                    control=("onoff", "dim"),
                    capability_map={"on": "onoff", "brightness": "dim"},
                    limits={"brightness": (0.0, 0.7)},
                    rated_power_w=12.0,
                    priority=index,
                ),
                DeviceBinding(
                    id=f"sensor-{index}",
                    alias=f"zone_{index}_sensor",
                    zone=f"zone_{index}",
                    kind="sensor",
                ),
            )
        )
    return HomeyConfig(
        address=address,
        token="secret-fixture-token",
        target_id="home",
        mode=mode,
        armed=armed,
        plugin_database=base / "homeops.db",
        engine_database=base / "engine.db",
        homey_id="homey-fixture",
        timeout_seconds=0.5,
        poll_interval_seconds=0.01,
        events=True,
        zones=zones,
        devices=tuple(devices),
    )


class FakeHomeyServer:
    def __init__(self, transport: MemoryHomeyTransport, token: str) -> None:
        self.transport = transport
        self.token = token
        self.requests: list[tuple[str, str, str | None]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append(
                    ("GET", self.path, self.headers.get("Authorization"))
                )
                if not self._authorized():
                    return
                if self.path == "/api/manager/zones/zone":
                    self._json(owner.transport.zones)
                elif self.path == "/api/manager/devices/device":
                    self._json(owner.transport.devices)
                else:
                    self.send_error(404)

            def do_PUT(self) -> None:
                owner.requests.append(
                    ("PUT", self.path, self.headers.get("Authorization"))
                )
                if not self._authorized():
                    return
                parts = self.path.split("/")
                if len(parts) != 8 or parts[1:5] != [
                    "api",
                    "manager",
                    "devices",
                    "device",
                ]:
                    self.send_error(404)
                    return
                device_id = unquote(parts[5])
                capability_id = unquote(parts[7]) if parts[6] == "capability" else ""
                length = int(self.headers.get("Content-Length", "0"))
                value = json.loads(self.rfile.read(length))["value"]
                owner.transport.set_capability(device_id, capability_id, value)
                self._json({"ok": True})

            def _authorized(self) -> bool:
                if self.headers.get("Authorization") == f"Bearer {owner.token}":
                    return True
                self.send_response(401)
                self.end_headers()
                return False

            def _json(self, value: object) -> None:
                payload = json.dumps(value).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.address = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


def _cap(
    identifier: str,
    value: object,
    updated: str,
    value_type: str,
    *,
    units: str | None = None,
    setable: bool = False,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "value": value,
        "lastUpdated": updated,
        "type": value_type,
        "units": units,
        "getable": True,
        "setable": setable,
    }
