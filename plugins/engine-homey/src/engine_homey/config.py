from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class HomeyConfigError(ValueError):
    """Configuration is unsafe, ambiguous or incomplete."""


_ALIAS = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class ZoneBinding:
    id: str
    alias: str


@dataclass(frozen=True)
class DeviceBinding:
    id: str
    alias: str
    zone: str | None = None
    kind: str = "device"
    control: tuple[str, ...] = ()
    capability_map: Mapping[str, str] = field(default_factory=dict)
    limits: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    rated_power_w: float | None = None
    priority: int = 0

    def capability(self, semantic_name: str, default: str) -> str:
        return str(self.capability_map.get(semantic_name, default))

    def limit(
        self, semantic_name: str, default: tuple[float, float]
    ) -> tuple[float, float]:
        return self.limits.get(semantic_name, default)


@dataclass(frozen=True)
class HomeyConfig:
    address: str
    token: str = field(repr=False)
    target_id: str
    mode: str
    armed: bool
    plugin_database: Path
    engine_database: Path
    auth_mode: str = "token"
    homey_id: str | None = None
    timeout_seconds: float = 5.0
    poll_interval_seconds: float = 2.0
    max_snapshot_age_seconds: float = 30.0
    events: bool = True
    zones: tuple[ZoneBinding, ...] = ()
    devices: tuple[DeviceBinding, ...] = ()
    config_path: Path | None = None

    @property
    def zone_by_id(self) -> dict[str, ZoneBinding]:
        return {item.id: item for item in self.zones}

    @property
    def device_by_id(self) -> dict[str, DeviceBinding]:
        return {item.id: item for item in self.devices}

    @property
    def device_by_alias(self) -> dict[str, DeviceBinding]:
        return {item.alias: item for item in self.devices}


def load_config(
    path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> HomeyConfig:
    values = os.environ if environ is None else environ
    raw_path = path or values.get("ENGINE_HOMEY_CONFIG")
    if not raw_path:
        raise HomeyConfigError("ENGINE_HOMEY_CONFIG must name a TOML file")
    config_path = Path(raw_path).expanduser().resolve()
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise HomeyConfigError(f"cannot read Homey config: {error}") from error
    homey = _mapping(raw.get("homey"), "[homey]")
    auth_mode = values.get("ENGINE_HOMEY_AUTH", "token")
    if auth_mode not in {"token", "cli"}:
        raise HomeyConfigError("ENGINE_HOMEY_AUTH must be 'token' or 'cli'")
    token = values.get("ENGINE_HOMEY_TOKEN", "")
    if auth_mode == "token" and not token:
        raise HomeyConfigError("ENGINE_HOMEY_TOKEN is required")

    address = str(homey.get("address", "")).rstrip("/")
    parsed = urlparse(address)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HomeyConfigError("homey.address must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise HomeyConfigError("homey.address must not contain credentials")
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise HomeyConfigError("homey.address must be a credential-free origin URL")

    mode = values.get("ENGINE_HOMEY_MODE", str(homey.get("mode", "observe")))
    if mode not in {"observe", "act"}:
        raise HomeyConfigError("Homey mode must be 'observe' or 'act'")
    armed = values.get("ENGINE_HOMEY_ARMED", "0") == "1"

    base = config_path.parent
    plugin_database = _database_path(
        base, values.get("ENGINE_HOMEY_DB", homey.get("plugin_database", "homeops.db"))
    )
    engine_database = _database_path(
        base,
        values.get(
            "ENGINE_HOMEY_ENGINE_DB",
            homey.get("engine_database", "engine-homeops.db"),
        ),
    )
    if plugin_database == engine_database:
        raise HomeyConfigError(
            "plugin_database and engine_database must be separate files"
        )

    zones = tuple(_zone(item) for item in _list(raw.get("zones"), "zones"))
    devices = tuple(_device(item) for item in _list(raw.get("devices"), "devices"))
    _unique((item.id for item in zones), "zone id")
    _unique((item.alias for item in zones), "zone alias")
    _unique((item.id for item in devices), "device id")
    _unique((item.alias for item in devices), "device alias")
    zone_aliases = {item.alias for item in zones}
    for device in devices:
        if device.zone is not None and device.zone not in zone_aliases:
            raise HomeyConfigError(
                f"device {device.alias!r} names unknown zone alias {device.zone!r}"
            )

    timeout = float(homey.get("timeout_seconds", 5.0))
    poll = float(
        homey.get("poll_interval_seconds", 30.0 if mode == "observe" else 2.0)
    )
    max_snapshot_age = float(homey.get("max_snapshot_age_seconds", 30.0))
    if timeout <= 0 or poll <= 0 or max_snapshot_age <= 0:
        raise HomeyConfigError(
            "timeouts, polling intervals and maximum snapshot age must be positive"
        )

    target_id = str(homey.get("target_id", "home"))
    if not _ALIAS.fullmatch(target_id):
        raise HomeyConfigError("homey.target_id must be a stable lowercase alias")
    homey_id = str(homey["homey_id"]) if homey.get("homey_id") else None
    events = bool(homey.get("events", True))
    if events and not homey_id:
        # A missing Homey id disables the optimization, never polling correctness.
        events = False
    if auth_mode == "cli":
        # CLI OAuth remains inside the official CLI process. Without a raw
        # credential the adapter deliberately relies on authoritative polling.
        events = False

    return HomeyConfig(
        address=address,
        token=token,
        auth_mode=auth_mode,
        target_id=target_id,
        mode=mode,
        armed=armed,
        plugin_database=plugin_database,
        engine_database=engine_database,
        homey_id=homey_id,
        timeout_seconds=timeout,
        poll_interval_seconds=poll,
        max_snapshot_age_seconds=max_snapshot_age,
        events=events,
        zones=zones,
        devices=devices,
        config_path=config_path,
    )


def _zone(value: object) -> ZoneBinding:
    item = _mapping(value, "zone binding")
    identifier = _required_string(item, "id", "zone")
    alias = _required_alias(item, "alias", "zone")
    return ZoneBinding(identifier, alias)


def _device(value: object) -> DeviceBinding:
    item = _mapping(value, "device binding")
    identifier = _required_string(item, "id", "device")
    alias = _required_alias(item, "alias", "device")
    control_raw = item.get("control", [])
    if not isinstance(control_raw, list) or not all(
        isinstance(value, str) and value for value in control_raw
    ):
        raise HomeyConfigError(f"device {alias!r} control must be a string list")
    capability_map_raw = _mapping(
        item.get("capability_map", {}), f"device {alias!r} capability_map"
    )
    capability_map = {
        str(key): _nonempty(value, f"capability map {key!r}")
        for key, value in capability_map_raw.items()
    }
    limits_raw = _mapping(item.get("limits", {}), f"device {alias!r} limits")
    limits: dict[str, tuple[float, float]] = {}
    for key, raw_limit in limits_raw.items():
        if (
            not isinstance(raw_limit, list)
            or len(raw_limit) != 2
            or isinstance(raw_limit[0], bool)
            or isinstance(raw_limit[1], bool)
        ):
            raise HomeyConfigError(f"limit {key!r} must be [minimum, maximum]")
        low, high = float(raw_limit[0]), float(raw_limit[1])
        if low > high:
            raise HomeyConfigError(f"limit {key!r} minimum exceeds maximum")
        limits[str(key)] = (low, high)
    mapped = set(capability_map.values())
    if not mapped.issubset(set(control_raw)):
        raise HomeyConfigError(
            f"device {alias!r} capability_map values must be in control allowlist"
        )
    rated = item.get("rated_power_w")
    if rated is not None and (isinstance(rated, bool) or float(rated) <= 0):
        raise HomeyConfigError(f"device {alias!r} rated_power_w must be positive")
    return DeviceBinding(
        id=identifier,
        alias=alias,
        zone=(str(item["zone"]) if item.get("zone") else None),
        kind=str(item.get("kind", "device")),
        control=tuple(control_raw),
        capability_map=capability_map,
        limits=limits,
        rated_power_w=float(rated) if rated is not None else None,
        priority=int(item.get("priority", 0)),
    )


def _database_path(base: Path, value: object) -> Path:
    path = Path(str(value)).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise HomeyConfigError(f"{label} must be a TOML table")
    return value


def _list(value: object, label: str) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HomeyConfigError(f"{label} must be an array of tables")
    return value


def _required_string(item: Mapping[str, Any], key: str, label: str) -> str:
    if key not in item:
        raise HomeyConfigError(f"{label} binding requires {key!r}")
    return _nonempty(item[key], f"{label}.{key}")


def _required_alias(item: Mapping[str, Any], key: str, label: str) -> str:
    value = _required_string(item, key, label)
    if not _ALIAS.fullmatch(value):
        raise HomeyConfigError(
            f"{label}.{key} must match {_ALIAS.pattern!r}, got {value!r}"
        )
    return value


def _nonempty(value: object, label: str) -> str:
    result = str(value)
    if not result.strip():
        raise HomeyConfigError(f"{label} cannot be empty")
    return result


def _unique(values: object, label: str) -> None:
    seen: set[str] = set()
    for value in values:  # type: ignore[union-attr]
        if value in seen:
            raise HomeyConfigError(f"duplicate {label}: {value!r}")
        seen.add(value)
