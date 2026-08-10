from __future__ import annotations

from .brains import ClimateBrain, EnergyBrain, LightingBrain, PresenceBrain
from .config import HomeyConfig, load_config
from .contracts import EnginePlugin, PluginManifest
from .store import HomeOpsStore
from .target import HomeyTarget
from .transport import (
    CLIHomeyTransport,
    EventSource,
    HomeyTransport,
    HTTPHomeyTransport,
    NullEventSource,
    SocketIOEventSource,
)


def build_target(
    config: HomeyConfig,
    store: HomeOpsStore,
    *,
    transport: HomeyTransport | None = None,
    event_source: EventSource | None = None,
) -> HomeyTarget:
    if transport is not None:
        actual_transport = transport
    elif config.auth_mode == "cli":
        # `--from-cli` deliberately follows the Homey selected in the already
        # authorized official CLI session. The configured id remains target
        # provenance; forcing it back into every CLI call can select a Homey
        # that differs from the active onboarding choice.
        actual_transport = CLIHomeyTransport(
            timeout_seconds=config.timeout_seconds
        )
    else:
        actual_transport = HTTPHomeyTransport(
            config.address, config.token, config.timeout_seconds
        )
    if event_source is None:
        event_source = (
            SocketIOEventSource(
                config.address,
                config.token,
                config.homey_id or "",
                timeout_seconds=config.timeout_seconds,
            )
            if config.events and config.homey_id
            else NullEventSource()
        )
    return HomeyTarget(
        config,
        store,
        actual_transport,
        event_source=event_source,
    )


def create_plugin(
    config: HomeyConfig,
    store: HomeOpsStore,
    *,
    transport: HomeyTransport | None = None,
    event_source: EventSource | None = None,
) -> EnginePlugin:
    target = build_target(config, store, transport=transport, event_source=event_source)
    return EnginePlugin(
        PluginManifest(
            id="engine.homey",
            description="HomeOps whole-house application on Engine",
            version="0.1.0",
        ),
        targets=(target,),
        specialists=(
            LightingBrain(),
            ClimateBrain(),
            EnergyBrain(),
            PresenceBrain(),
        ),
    )


def load_plugin() -> EnginePlugin:
    """Zero-argument `engine.plugins` entrypoint factory."""
    config = load_config()
    store = HomeOpsStore(config.plugin_database)
    try:
        return create_plugin(config, store)
    except Exception:
        store.close()
        raise
