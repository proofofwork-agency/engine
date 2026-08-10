from __future__ import annotations

import json
import os
import sqlite3
import threading
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from engine_sdk import (
    CapabilitySpecV2,
    EntityV1,
    EvidenceGrade,
    ObservationV1,
    PluginManifestV2,
    RelationV1,
    TargetObservationV2,
    load_static_manifest,
    locate_distribution_manifest,
)


class LocationProvider(Protocol):
    @property
    def source(self) -> str: ...

    def location(self) -> tuple[float, float] | None: ...


class WeatherProvider(Protocol):
    @property
    def source(self) -> str: ...

    def current(self, latitude: float, longitude: float) -> dict[str, Any]: ...


class ExplicitLocationProvider:
    source = "explicit_owner_location"

    def __init__(self, latitude: float | None, longitude: float | None):
        self.latitude = latitude
        self.longitude = longitude

    def location(self) -> tuple[float, float] | None:
        if self.latitude is None or self.longitude is None:
            return None
        return self.latitude, self.longitude


class MacOSCoreLocationProvider:
    """Optional OS-provider seam; the caller supplies an already-authorized reader."""

    source = "macos_core_location"

    def __init__(
        self,
        authorized_reader: Callable[[], tuple[float, float] | None],
        *,
        os_permission_confirmed: bool,
    ) -> None:
        self.reader = authorized_reader
        self.permission = os_permission_confirmed

    def location(self) -> tuple[float, float] | None:
        return self.reader() if self.permission else None


class OpenMeteoWeatherProvider:
    source = "open-meteo.current/v1"

    def __init__(
        self,
        endpoint: str = "https://api.open-meteo.com/v1/forecast",
        *,
        timeout_seconds: float = 5.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self._opener = opener or urllib.request.urlopen

    def current(self, latitude: float, longitude: float) -> dict[str, Any]:
        query = urllib.parse.urlencode({
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,cloud_cover,precipitation",
        })
        request = urllib.request.Request(
            f"{self.endpoint}?{query}",
            headers={"User-Agent": "engine-context/0.2"},
        )
        with self._opener(request, timeout=self.timeout_seconds) as response:
            raw = json.loads(response.read().decode("utf-8"))
        current = raw.get("current")
        if not isinstance(current, dict):
            raise TypeError("weather provider response lacks current object")
        return {
            "temperature_c": current.get("temperature_2m"),
            "cloud_cover_pct": current.get("cloud_cover"),
            "precipitation_mm": current.get("precipitation"),
            "observed_at": current.get("time"),
        }


class ContextStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Open and migrate only when the provider is actually observed.

        Loading a plugin manifest or calling its entrypoint must remain inert.
        """
        if self._connection is not None:
            return self._connection
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS revision_ledger(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO revision_ledger(id, revision) VALUES(1, 0)"
        )
        connection.commit()
        self._connection = connection
        return connection

    def next_revision(self) -> int:
        self.connection.execute("UPDATE revision_ledger SET revision=revision+1 WHERE id=1")
        self.connection.commit()
        return int(self.connection.execute("SELECT revision FROM revision_ledger WHERE id=1").fetchone()[0])

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


class ContextWorldProvider:
    plugin_id = "engine.context"
    target_id = "engine.context.local"
    poll_interval_seconds = 60.0
    freshness_seconds = 180.0

    def __init__(
        self,
        store: ContextStore,
        manifest: PluginManifestV2,
        location: LocationProvider,
        weather: WeatherProvider | None,
        *,
        share_location_with_weather: bool,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.manifest = manifest
        self.location_provider = location
        self.weather_provider = weather
        self.share_location_with_weather = share_location_with_weather
        self.clock = clock or (lambda: datetime.now().astimezone())
        self._wake_lock = threading.Lock()
        self._scheduled: list[tuple[datetime, Callable[..., None]]] = []

    def discover(self) -> tuple[CapabilitySpecV2, ...]:
        return self.manifest.capabilities

    def observe(self) -> TargetObservationV2:
        now = self.clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        observed_at = now.isoformat()
        revision = self.store.next_revision()
        local = EntityV1(
            "context:local", self.target_id, "context.local", self.plugin_id,
            "Local context", {"timezone": str(now.tzinfo)},
        )
        location_entity = EntityV1(
            "context:location", self.target_id, "context.location", self.plugin_id,
            "Confirmed location", {"provider": self.location_provider.source},
        )
        weather_entity = EntityV1(
            "context:weather", self.target_id, "context.weather", self.plugin_id,
            "Current weather", {"provider": getattr(self.weather_provider, "source", None)},
        )
        observations = [
            ObservationV1(
                f"context:time:r{revision}", local.id, "time.iso8601", observed_at,
                "engine.context.clock", observed_at, EvidenceGrade.OBSERVED,
                quality=1.0, coverage="instant",
            ),
            ObservationV1(
                f"context:hour:r{revision}", local.id, "time.hour", now.hour,
                "engine.context.clock", observed_at, EvidenceGrade.DERIVED,
                unit="hour", quality=1.0, coverage="instant",
            ),
            ObservationV1(
                f"context:minute-of-day:r{revision}", local.id,
                "time.minute_of_day", now.hour * 60 + now.minute,
                "engine.context.clock", observed_at, EvidenceGrade.DERIVED,
                unit="minute", quality=1.0, coverage="instant",
            ),
            ObservationV1(
                f"context:weekday:r{revision}", local.id, "time.weekday", now.weekday(),
                "engine.context.clock", observed_at, EvidenceGrade.DERIVED,
                quality=1.0, coverage="instant",
            ),
        ]
        errors: list[str] = []
        coordinates = self.location_provider.location()
        if coordinates is None:
            observations.extend(_unknown_location(revision, observed_at, self.location_provider.source))
            errors.append("weather deferred: confirmed location is unavailable")
            observations.extend(_unknown_weather(revision, observed_at, "location_unavailable"))
        else:
            latitude, longitude = coordinates
            observations.extend((
                ObservationV1(
                    f"context:latitude:r{revision}", location_entity.id,
                    "location.latitude", latitude, self.location_provider.source,
                    observed_at, EvidenceGrade.OBSERVED, unit="degree",
                    quality=1.0, coverage="confirmed_point",
                ),
                ObservationV1(
                    f"context:longitude:r{revision}", location_entity.id,
                    "location.longitude", longitude, self.location_provider.source,
                    observed_at, EvidenceGrade.OBSERVED, unit="degree",
                    quality=1.0, coverage="confirmed_point",
                ),
            ))
            if self.weather_provider is not None and self.share_location_with_weather:
                try:
                    current = self.weather_provider.current(latitude, longitude)
                    weather_time = str(current.get("observed_at") or observed_at)
                    for property_name, unit in (
                        ("temperature_c", "degC"),
                        ("cloud_cover_pct", "%"),
                        ("precipitation_mm", "mm"),
                    ):
                        value = current.get(property_name)
                        observations.append(
                            ObservationV1(
                                f"context:weather:{property_name}:r{revision}",
                                weather_entity.id, f"weather.{property_name}", value,
                                self.weather_provider.source, weather_time,
                                EvidenceGrade.OBSERVED if value is not None else EvidenceGrade.UNKNOWN,
                                unit=unit, quality=1.0 if value is not None else None,
                                coverage="provider_current",
                            )
                        )
                except Exception as exc:  # noqa: BLE001 - optional provider isolation
                    errors.append(f"weather unavailable: {type(exc).__name__}")
                    observations.extend(_unknown_weather(revision, observed_at, self.weather_provider.source))
            else:
                errors.append("weather deferred: location sharing is not permitted")
                observations.extend(_unknown_weather(revision, observed_at, "not_transmitted"))
        relations = (
            RelationV1(
                "context:local:located-at", "located_at", local.id,
                location_entity.id, self.plugin_id, observed_at,
                EvidenceGrade.OBSERVED if coordinates is not None else EvidenceGrade.UNKNOWN,
            ),
            RelationV1(
                "context:weather:for-location", "weather_for", weather_entity.id,
                location_entity.id, self.plugin_id, observed_at,
                EvidenceGrade.DERIVED if coordinates is not None and self.share_location_with_weather else EvidenceGrade.UNKNOWN,
            ),
        )
        self._fire_due(now)
        return TargetObservationV2(
            self.target_id, revision, observed_at,
            (local, location_entity, weather_entity), relations, tuple(observations),
            {
                "time": "complete",
                "location": "confirmed" if coordinates is not None else "UNKNOWN",
                "weather": "provider_current" if not errors else "UNKNOWN",
                "location_transmitted": bool(coordinates and self.share_location_with_weather and self.weather_provider),
            },
            self.plugin_id,
            available=True,
            errors=tuple(errors),
        )

    def subscribe(self, wake: Callable[..., None]) -> Callable[[], None] | None:
        # Polling is authoritative; scheduled wakes can additionally call this
        # callback and still force Heart to observe before acting.
        with self._wake_lock:
            self._default_wake = wake
        return None

    def schedule(self, at: datetime, wake: Callable[..., None] | None = None) -> None:
        callback = wake or getattr(self, "_default_wake", None)
        if callback is None:
            raise ValueError("no wake callback is registered")
        with self._wake_lock:
            self._scheduled.append((at, callback))

    def _fire_due(self, now: datetime) -> None:
        with self._wake_lock:
            due = [item for item in self._scheduled if item[0] <= now]
            self._scheduled = [item for item in self._scheduled if item[0] > now]
        for _, callback in due:
            callback()


@dataclass(frozen=True)
class ContextPlugin:
    manifest: PluginManifestV2
    providers: tuple[Any, ...]
    controllers: tuple[Any, ...] = ()
    executors: tuple[Any, ...] = ()
    oracles: tuple[Any, ...] = ()
    specialists: tuple[Any, ...] = ()


def load_plugin() -> ContextPlugin:
    local_path = Path(__file__).resolve().parents[2] / "engine-plugin.toml"
    if not local_path.is_file():
        from importlib import metadata

        local_path = locate_distribution_manifest(metadata.distribution("engine-context"))
        if local_path is None:
            raise FileNotFoundError("engine-context static manifest is not installed")
    manifest = load_static_manifest(local_path)
    store_path = Path(os.environ.get("ENGINE_CONTEXT_DATABASE", ".engine/context.sqlite3"))
    latitude = _optional_float(os.environ.get("ENGINE_CONTEXT_LATITUDE"))
    longitude = _optional_float(os.environ.get("ENGINE_CONTEXT_LONGITUDE"))
    consent = os.environ.get("ENGINE_CONTEXT_SHARE_LOCATION_WITH_WEATHER") == "1"
    store = ContextStore(store_path)
    provider = ContextWorldProvider(
        store, manifest, ExplicitLocationProvider(latitude, longitude),
        OpenMeteoWeatherProvider(
            os.environ.get("ENGINE_CONTEXT_WEATHER_ENDPOINT", "https://api.open-meteo.com/v1/forecast")
        ),
        share_location_with_weather=consent,
    )
    return ContextPlugin(manifest, (provider,))


def _unknown_location(revision: int, observed_at: str, source: str) -> tuple[ObservationV1, ...]:
    return tuple(
        ObservationV1(
            f"context:{name}:r{revision}", "context:location", f"location.{name}",
            None, source, observed_at, EvidenceGrade.UNKNOWN, unit="degree",
            coverage="no_confirmed_location",
        )
        for name in ("latitude", "longitude")
    )


def _unknown_weather(revision: int, observed_at: str, source: str) -> tuple[ObservationV1, ...]:
    return tuple(
        ObservationV1(
            f"context:weather:{name}:r{revision}", "context:weather", f"weather.{name}",
            None, source, observed_at, EvidenceGrade.UNKNOWN, unit=unit,
            coverage="provider_unavailable",
        )
        for name, unit in (
            ("temperature_c", "degC"),
            ("cloud_cover_pct", "%"),
            ("precipitation_mm", "mm"),
        )
    )


def _optional_float(value: str | None) -> float | None:
    return float(value) if value not in {None, ""} else None
