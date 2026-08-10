from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from collections.abc import Callable, Iterable
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

JsonObject = dict[str, Any]


class HomeyTransportError(RuntimeError):
    """A Homey operation failed without leaking credentials or response bodies."""


class HomeyHTTPError(HomeyTransportError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        del request, fp, code, msg, headers, newurl


class HomeyTransport(Protocol):
    def read_house(self) -> tuple[JsonObject, JsonObject]: ...

    def set_capability(
        self, device_id: str, capability_id: str, value: bool | float | str
    ) -> JsonObject: ...


class EventSource(Protocol):
    def subscribe(
        self, device_ids: Iterable[str], callback: Callable[[object], None]
    ) -> Callable[[], None]: ...


class HTTPHomeyTransport:
    """Small official Homey HTTP contract implemented with the Python stdlib."""

    def __init__(self, address: str, token: str, timeout_seconds: float = 5.0) -> None:
        self._address = address.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds
        self._opener = build_opener(_NoRedirect())

    def read_house(self) -> tuple[JsonObject, JsonObject]:
        zones = self._request("GET", "/api/manager/zones/zone")
        devices = self._request("GET", "/api/manager/devices/device")
        if not isinstance(zones, dict) or not isinstance(devices, dict):
            raise HomeyHTTPError("Homey discovery returned a non-object payload")
        return zones, devices

    def set_capability(
        self, device_id: str, capability_id: str, value: bool | float | str
    ) -> JsonObject:
        path = (
            "/api/manager/devices/device/"
            f"{quote(device_id, safe='')}/capability/{quote(capability_id, safe='')}"
        )
        result = self._request("PUT", path, {"value": value})
        return result if isinstance(result, dict) else {"acknowledged": True}

    def _request(
        self, method: str, path: str, body: JsonObject | None = None
    ) -> object:
        encoded = (
            json.dumps(body, separators=(",", ":")).encode("utf-8")
            if body is not None
            else None
        )
        request = Request(
            f"{self._address}{path}",
            data=encoded,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload = response.read()
        except HTTPError as error:
            error.close()
            raise HomeyHTTPError(
                f"Homey HTTP {error.code} for {method} {path}"
            ) from None
        except (TimeoutError, URLError, OSError) as error:
            raise HomeyHTTPError(
                f"Homey transport failed for {method} {path}: {type(error).__name__}"
            ) from None
        if not payload:
            return {}
        try:
            return json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HomeyHTTPError(
                f"Homey returned invalid JSON for {method} {path}"
            ) from None


class CLIHomeyTransport:
    """Use the already-authorized official Homey CLI as the transport.

    Engine never reads, persists or prints the CLI's OAuth credential. The
    subprocess returns only Homey's JSON API result. This mode intentionally
    uses polling; Socket.IO requires a separately supplied runtime token.
    """

    def __init__(
        self,
        homey_id: str | None = None,
        *,
        timeout_seconds: float = 5.0,
        executable: str = "homey",
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._homey_id = homey_id
        self._timeout = timeout_seconds
        self._executable = executable
        self._runner = runner

    def selected_homey(self) -> JsonObject:
        result = self._run(("select", "current", "--json"), "select current")
        if not isinstance(result, dict) or not result.get("id"):
            raise HomeyTransportError(
                "Homey CLI has no selected Homey; run `homey select` first"
            )
        return result

    def read_house(self) -> tuple[JsonObject, JsonObject]:
        zones = self._api(("zones", "get-zones"), "zones get-zones")
        devices = self._api(("devices", "get-devices"), "devices get-devices")
        if not isinstance(zones, dict) or not isinstance(devices, dict):
            raise HomeyTransportError("Homey CLI discovery returned a non-object payload")
        return zones, devices

    def set_capability(
        self, device_id: str, capability_id: str, value: bool | float | str
    ) -> JsonObject:
        if type(value) is bool:
            raw_value = "true" if value else "false"
        else:
            raw_value = str(value)
        result = self._api(
            (
                "devices",
                "set-capability-value",
                "--device-id",
                device_id,
                "--capability-id",
                capability_id,
                "--value",
                raw_value,
            ),
            "devices set-capability-value",
        )
        return result if isinstance(result, dict) else {"acknowledged": True}

    def _api(self, arguments: tuple[str, ...], label: str) -> object:
        common = [
            "--json",
            "--timeout",
            str(max(1, int(self._timeout * 1000))),
        ]
        if self._homey_id:
            common.extend(("--homey-id", self._homey_id))
        return self._run(("api", *arguments, *common), label)

    def _run(self, arguments: tuple[str, ...], label: str) -> object:
        command = (self._executable, *arguments)
        try:
            # Node may drop the tail of a large console write when stdout is a
            # pipe. A local anonymous file keeps the official CLI output
            # complete and is unlinked automatically when this call returns.
            with tempfile.TemporaryFile() as output:
                completed = self._runner(
                    command,
                    stdout=output,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=self._timeout + 2.0,
                )
                raw_stdout = completed.stdout
                if raw_stdout is None:
                    output.seek(0)
                    raw_stdout = output.read()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as error:
            raise HomeyTransportError(
                f"Homey CLI failed for {label}: {type(error).__name__}"
            ) from None
        if completed.returncode != 0:
            # stderr may contain account, target or transport details. Keep the
            # exception useful without copying subprocess output into logs.
            raise HomeyTransportError(f"Homey CLI command failed for {label}")
        try:
            if isinstance(raw_stdout, bytes):
                raw_stdout = raw_stdout.decode("utf-8")
            parsed = json.loads(raw_stdout)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
            raise HomeyTransportError(
                f"Homey CLI returned invalid JSON for {label}"
            ) from None
        return parsed


class SocketIOEventSource:
    """Homey Socket.IO wake hints with fail-safe polling fallback.

    The official protocol authenticates on `/`, returns the broadcast namespace,
    then accepts `subscribe` calls for `homey:device:<id>` URIs. Event data is
    deliberately discarded; callers receive only a wake signal.
    """

    def __init__(
        self,
        address: str,
        token: str,
        homey_id: str,
        *,
        timeout_seconds: float = 5.0,
        client_factory: Callable[[], object] | None = None,
    ) -> None:
        self._address = address.rstrip("/")
        self._token = token
        self._homey_id = homey_id
        self._timeout = timeout_seconds
        self._client_factory = client_factory

    def subscribe(
        self, device_ids: Iterable[str], callback: Callable[[object], None]
    ) -> Callable[[], None]:
        try:
            import socketio
        except ImportError as error:  # pragma: no cover - packaging installs it
            raise HomeyTransportError("python-socketio is not installed") from error

        client = (
            self._client_factory()
            if self._client_factory is not None
            else socketio.Client(
                reconnection=True,
                logger=False,
                engineio_logger=False,
                request_timeout=self._timeout,
                handle_sigint=False,
            )
        )
        uris = tuple(f"homey:device:{item}" for item in sorted(set(device_ids)))
        ready = threading.Event()
        failure: list[Exception] = []
        subscribed: list[tuple[str, str]] = []

        def wake_only(*_args: object) -> None:
            callback({"kind": "homey_event_wake"})

        def ack(*args: object) -> None:
            error, result = _ack_parts(args)
            if error:
                failure.append(HomeyTransportError("Homey Socket.IO handshake failed"))
                ready.set()
                return
            namespace = (
                str(result.get("namespace", "/api"))
                if isinstance(result, dict)
                else "/api"
            )

            def joined_namespace() -> None:
                try:
                    # A Socket.IO reconnect creates a new server-side session.
                    # Rebuild the subscription ledger and subscribe every URI
                    # again instead of treating the old session as authoritative.
                    subscribed[:] = [
                        item for item in subscribed if item[0] != namespace
                    ]
                    for uri in uris:
                        client.emit("subscribe", uri, namespace=namespace)
                        subscribed.append((namespace, uri))
                except Exception as error:  # noqa: BLE001 - optional SDK boundary
                    failure.append(
                        HomeyTransportError(
                            f"Homey Socket.IO subscribe failed: {type(error).__name__}"
                        )
                    )
                ready.set()

            try:
                # Homey normally returns /api. Register handlers before the
                # namespace joins so no wake is lost. Subscription must wait for
                # the server's namespace-connect acknowledgement.
                if namespace != "/":
                    client.on("connect", handler=joined_namespace, namespace=namespace)
                for uri in uris:
                    client.on(uri, handler=wake_only, namespace=namespace)
                namespace_joined = namespace in getattr(client, "namespaces", {})
                if not namespace_joined:
                    sender = getattr(client, "_send_packet", None)
                    if not callable(sender):
                        raise HomeyTransportError(
                            "Socket.IO client cannot join Homey's namespace"
                        )
                    sender(
                        socketio.packet.Packet(
                            socketio.packet.CONNECT, namespace=namespace
                        )
                    )
                else:
                    joined_namespace()
            except Exception as error:  # noqa: BLE001 - optional SDK boundary
                failure.append(
                    error
                    if isinstance(error, HomeyTransportError)
                    else HomeyTransportError(
                        f"Homey Socket.IO subscribe failed: {type(error).__name__}"
                    )
                )
                ready.set()

        def connected() -> None:
            client.emit(
                "handshakeClient",
                {"token": self._token, "homeyId": self._homey_id},
                callback=ack,
                namespace="/",
            )

        client.on("connect", handler=connected, namespace="/")
        try:
            client.connect(
                self._address,
                transports=["websocket"],
                namespaces=["/"],
                wait_timeout=self._timeout,
            )
        except Exception as error:  # noqa: BLE001 - optional SDK boundary
            raise HomeyTransportError(
                f"Homey Socket.IO connect failed: {type(error).__name__}"
            ) from None
        if not ready.wait(self._timeout):
            client.disconnect()
            raise HomeyTransportError("Homey Socket.IO handshake timed out")
        if failure:
            client.disconnect()
            raise failure[0]

        def unsubscribe() -> None:
            for namespace, uri in subscribed:
                try:
                    client.emit("unsubscribe", uri, namespace=namespace)
                except Exception:  # noqa: BLE001,S110 - best-effort unsubscribe
                    pass
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001,S110 - best-effort disconnect
                pass

        return unsubscribe


def _ack_parts(args: tuple[object, ...]) -> tuple[object | None, object | None]:
    if len(args) >= 2:
        return args[0], args[1]
    if len(args) == 1:
        value = args[0]
        if isinstance(value, dict) and "namespace" in value:
            return None, value
        if isinstance(value, (tuple, list)) and len(value) >= 2:
            return value[0], value[1]
        return value, None
    return "missing acknowledgement", None


class NullEventSource:
    def subscribe(
        self, device_ids: Iterable[str], callback: Callable[[object], None]
    ) -> Callable[[], None]:
        del device_ids, callback
        return lambda: None
