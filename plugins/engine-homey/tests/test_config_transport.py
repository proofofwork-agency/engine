from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine_homey.config import HomeyConfigError, load_config
from engine_homey.transport import (
    CLIHomeyTransport,
    HomeyHTTPError,
    HomeyTransportError,
    HTTPHomeyTransport,
    SocketIOEventSource,
)
from fakes import FakeHomeyServer, MemoryHomeyTransport, fixture_house


class ConfigAndTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="engine-homey-config-")
        self.base = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_config_keeps_databases_separate_and_token_out_of_toml(self) -> None:
        path = self.base / "homey.toml"
        path.write_text(
            """
[homey]
address = "http://127.0.0.1"
target_id = "home"
mode = "act"
plugin_database = "plugin.db"
engine_database = "engine.db"

[[zones]]
id = "zone-1"
alias = "living_room"

[[devices]]
id = "light-1"
alias = "living_main"
zone = "living_room"
kind = "light"
control = ["onoff", "dim"]
capability_map = { on = "onoff", brightness = "dim" }
limits = { brightness = [0.0, 0.7] }
""".strip(),
            encoding="utf-8",
        )
        config = load_config(
            path,
            environ={"ENGINE_HOMEY_TOKEN": "runtime-only", "ENGINE_HOMEY_ARMED": "1"},
        )
        self.assertEqual("runtime-only", config.token)
        self.assertTrue(config.armed)
        self.assertNotEqual(config.plugin_database, config.engine_database)
        self.assertNotIn("runtime-only", path.read_text(encoding="utf-8"))
        self.assertNotIn("runtime-only", repr(config))

        duplicate = path.read_text().replace("engine.db", "plugin.db")
        path.write_text(duplicate)
        with self.assertRaisesRegex(HomeyConfigError, "separate"):
            load_config(path, environ={"ENGINE_HOMEY_TOKEN": "runtime-only"})

    def test_http_contract_authenticates_discovers_and_sets_capability(self) -> None:
        zones, devices = fixture_house(1)
        memory = MemoryHomeyTransport(zones, devices)
        with FakeHomeyServer(memory, "pat-value") as server:
            client = HTTPHomeyTransport(server.address, "pat-value", 1.0)
            observed_zones, observed_devices = client.read_house()
            self.assertEqual({"zone-1"}, set(observed_zones))
            self.assertEqual({"light-1", "sensor-1"}, set(observed_devices))
            client.set_capability("light-1", "onoff", True)

            self.assertTrue(
                memory.devices["light-1"]["capabilitiesObj"]["onoff"]["value"]
            )
            self.assertTrue(
                all(auth == "Bearer pat-value" for _, _, auth in server.requests)
            )
            self.assertEqual(
                [
                    "/api/manager/zones/zone",
                    "/api/manager/devices/device",
                    "/api/manager/devices/device/light-1/capability/onoff",
                ],
                [path for _, path, _ in server.requests],
            )

    def test_cli_transport_uses_selected_session_without_exporting_credentials(self) -> None:
        commands: list[tuple[str, ...]] = []

        def runner(command, **_options):
            command = tuple(command)
            commands.append(command)
            if command[1:4] == ("select", "current", "--json"):
                payload = '{"id":"homey-1","name":"Lab"}'
            elif "get-zones" in command:
                payload = '{"zone-1":{"id":"zone-1"}}'
            elif "get-devices" in command:
                payload = '{"light-1":{"id":"light-1"}}'
            else:
                payload = '{"ok":true}'
            return subprocess.CompletedProcess(command, 0, payload, "")

        client = CLIHomeyTransport(runner=runner)
        self.assertEqual("homey-1", client.selected_homey()["id"])
        zones, devices = client.read_house()
        self.assertEqual({"zone-1"}, set(zones))
        self.assertEqual({"light-1"}, set(devices))
        client.set_capability("light-1", "onoff", True)
        flattened = " ".join(" ".join(command) for command in commands)
        self.assertNotIn("token", flattened.lower())
        self.assertIn("--value true", flattened)

    def test_cli_auth_config_needs_no_token_and_disables_socket_events(self) -> None:
        path = self.base / "cli.toml"
        path.write_text(
            """
[homey]
address = "http://homey.local"
target_id = "home"
homey_id = "homey-1"
events = true
""".strip(),
            encoding="utf-8",
        )
        config = load_config(path, environ={"ENGINE_HOMEY_AUTH": "cli"})
        self.assertEqual("cli", config.auth_mode)
        self.assertEqual("", config.token)
        self.assertFalse(config.events)

    def test_cli_transport_reads_large_device_json_without_pipe_truncation(self) -> None:
        devices = {
            f"device-{index}": {
                "id": f"device-{index}",
                "name": "x" * 100,
                "capabilitiesObj": {"measure": {"value": index}},
            }
            for index in range(1000)
        }
        self.assertGreater(len(json.dumps(devices)), 65_536)

        def runner(command, **options):
            payload = (
                {"zone-1": {"id": "zone-1"}}
                if "get-zones" in command
                else devices
            )
            options["stdout"].write(json.dumps(payload).encode("utf-8"))
            return subprocess.CompletedProcess(command, 0, None, b"")

        zones, observed = CLIHomeyTransport(runner=runner).read_house()
        self.assertEqual({"zone-1"}, set(zones))
        self.assertEqual(1000, len(observed))

    def test_http_errors_never_include_token_or_response_body(self) -> None:
        zones, devices = fixture_house(1)
        memory = MemoryHomeyTransport(zones, devices)
        with FakeHomeyServer(memory, "right-token") as server:
            client = HTTPHomeyTransport(server.address, "wrong-secret", 1.0)
            with self.assertRaises(HomeyHTTPError) as caught:
                client.read_house()
        self.assertNotIn("wrong-secret", str(caught.exception))
        self.assertIn("HTTP 401", str(caught.exception))

    def test_socketio_contract_handshakes_subscribes_and_discards_event_payload(
        self,
    ) -> None:
        class FakeSocketClient:
            def __init__(self) -> None:
                self.handlers = {}
                self.namespaces = {}
                self.emits = []
                self.disconnected = False

            def on(self, event, handler, namespace):
                self.handlers[(namespace, event)] = handler

            def connect(self, address, **options):
                self.address = address
                self.options = options
                self.namespaces["/"] = "root"
                self.handlers[("/", "connect")]()

            def emit(self, event, data, callback=None, namespace=None):
                self.emits.append((namespace, event, data))
                if event == "handshakeClient":
                    callback(None, {"namespace": "/api"})

            def _send_packet(self, packet):
                self.namespaces[packet.namespace] = "joined"
                self.handlers[(packet.namespace, "connect")]()

            def disconnect(self):
                self.disconnected = True

        client = FakeSocketClient()
        wakes = []
        source = SocketIOEventSource(
            "http://homey.local",
            "socket-secret",
            "homey-id",
            client_factory=lambda: client,
        )
        unsubscribe = source.subscribe(["device-b", "device-a"], wakes.append)
        handshake = next(item for item in client.emits if item[1] == "handshakeClient")
        self.assertEqual(
            {"token": "socket-secret", "homeyId": "homey-id"}, handshake[2]
        )
        subscriptions = [item[2] for item in client.emits if item[1] == "subscribe"]
        self.assertEqual(
            ["homey:device:device-a", "homey:device:device-b"], subscriptions
        )
        client.handlers[("/api", "connect")]()
        subscriptions = [item[2] for item in client.emits if item[1] == "subscribe"]
        self.assertEqual(
            [
                "homey:device:device-a",
                "homey:device:device-b",
                "homey:device:device-a",
                "homey:device:device-b",
            ],
            subscriptions,
        )
        client.handlers[("/api", "homey:device:device-a")](
            "capability", {"value": "must-not-be-trusted"}
        )
        self.assertEqual([{"kind": "homey_event_wake"}], wakes)
        unsubscribe()
        self.assertTrue(client.disconnected)

    def test_socketio_handshake_timeout_fails_to_polling_boundary(self) -> None:
        class NoAckClient:
            def __init__(self) -> None:
                self.handlers = {}
                self.namespaces = {}
                self.disconnected = False

            def on(self, event, handler, namespace):
                self.handlers[(namespace, event)] = handler

            def connect(self, *_args, **_kwargs):
                self.namespaces["/"] = "root"
                self.handlers[("/", "connect")]()

            def emit(self, *_args, **_kwargs):
                return None

            def disconnect(self):
                self.disconnected = True

        client = NoAckClient()
        source = SocketIOEventSource(
            "http://homey.local",
            "secret",
            "homey-id",
            timeout_seconds=0.01,
            client_factory=lambda: client,
        )
        with self.assertRaisesRegex(HomeyTransportError, "timed out"):
            source.subscribe(["device"], lambda _event: None)
        self.assertTrue(client.disconnected)


if __name__ == "__main__":
    unittest.main()
