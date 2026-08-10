from __future__ import annotations

import os
import re
from dataclasses import dataclass
from importlib import metadata
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Mapping
from urllib import request
from urllib.parse import quote, urlparse

from engine_sdk import (
    LifecycleEventV1,
    PluginManifestV2,
    load_static_manifest,
    locate_distribution_manifest,
)


_TOPIC = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


@dataclass(frozen=True)
class NtfyConfig:
    base_url: str
    topic: str | None
    title: str = "engine"
    timeout_seconds: float = 5.0

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] | None = None
    ) -> NtfyConfig:
        values = os.environ if environ is None else environ
        topic = values.get("ENGINE_NTFY_TOPIC", "").strip() or None
        if topic is not None and not _TOPIC.fullmatch(topic):
            raise ValueError("ENGINE_NTFY_TOPIC must be a simple ntfy topic name")
        base_url = values.get("ENGINE_NTFY_BASE_URL", "https://ntfy.sh").rstrip("/")
        parsed = urlparse(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("ENGINE_NTFY_BASE_URL must be a credential-free origin")
        if parsed.scheme != "https" and not _is_loopback(parsed.hostname):
            raise ValueError("remote ntfy endpoints require HTTPS")
        title = values.get("ENGINE_NTFY_TITLE", "engine").strip()
        if not title or len(title) > 64 or "\n" in title or "\r" in title:
            raise ValueError("ENGINE_NTFY_TITLE must be a single non-empty line")
        timeout = float(values.get("ENGINE_NTFY_TIMEOUT_SECONDS", "5"))
        if timeout <= 0 or timeout > 30:
            raise ValueError("ENGINE_NTFY_TIMEOUT_SECONDS must be in (0, 30]")
        return cls(base_url, topic, title, timeout)


class NtfyLifecycleObserver:
    """Export selected durable milestones; never receive world snapshots."""

    id = "ntfy-engine-milestones"
    plugin_id = "engine.ntfy"

    def __init__(self, config: NtfyConfig) -> None:
        self.config = config

    def observe(self, events: tuple[LifecycleEventV1, ...]) -> None:
        if self.config.topic is None:
            return
        messages = _messages(events)
        if not messages:
            return
        body = "\n".join(messages[:10])
        if len(messages) > 10:
            body += f"\n… en {len(messages) - 10} andere mijlpalen"
        outgoing = request.Request(
            f"{self.config.base_url}/{quote(self.config.topic, safe='')}",
            data=body[:2048].encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Title": self.config.title,
                "Tags": "robot",
                "User-Agent": "engine-ntfy/0.1",
            },
        )
        with request.urlopen(outgoing, timeout=self.config.timeout_seconds) as response:
            if not 200 <= int(response.status) < 300:
                raise RuntimeError(f"ntfy returned HTTP {response.status}")


@dataclass(frozen=True)
class NtfyPlugin:
    manifest: PluginManifestV2
    lifecycle_observers: tuple[Any, ...]
    providers: tuple[Any, ...] = ()
    controllers: tuple[Any, ...] = ()
    executors: tuple[Any, ...] = ()
    oracles: tuple[Any, ...] = ()
    specialists: tuple[Any, ...] = ()
    experience_providers: tuple[Any, ...] = ()
    routine_compilers: tuple[Any, ...] = ()


def load_plugin() -> NtfyPlugin:
    path = Path(__file__).resolve().parents[2] / "engine-plugin.toml"
    if not path.is_file():
        path = locate_distribution_manifest(metadata.distribution("engine-ntfy"))
        if path is None:
            raise FileNotFoundError("engine-ntfy static manifest is not installed")
    manifest = load_static_manifest(path)
    observer = NtfyLifecycleObserver(NtfyConfig.from_environment())
    return NtfyPlugin(manifest, (observer,))


def _messages(events: tuple[LifecycleEventV1, ...]) -> list[str]:
    messages: list[str] = []
    for event in events:
        payload = event.payload
        if event.kind == "goal_created":
            messages.append(f"Goal toegevoegd: {_safe(event.goal_id or payload.get('id'))}")
        elif event.kind == "routine_candidate_created":
            messages.append(
                "Routine geleerd: "
                f"{_safe(payload.get('template_id'))} "
                f"({_non_negative_int(payload.get('example_count'))} voorbeelden)"
            )
        elif event.kind == "routine_candidate_ready":
            messages.append(
                "Routine klaar voor goedkeuring: "
                f"{_safe(payload.get('template_id'))}"
            )
        elif event.kind == "learning_candidate_created":
            messages.append(
                "Voorkeur geleerd: "
                f"{_safe(payload.get('field_path'))} voor {_safe(event.goal_id)}"
            )
        elif event.kind == "preference_promoted":
            messages.append(
                "Voorkeur geactiveerd: "
                f"{_safe(payload.get('preference_id') or payload.get('candidate_id'))}"
            )
        elif event.kind == "routine_created":
            messages.append(
                "Routine toegevoegd: "
                f"{_safe(payload.get('template_id'))} ({_safe(payload.get('routine_id'))})"
            )
        elif event.kind == "routine_activated":
            messages.append(
                f"Routine toegevoegd en geactiveerd: {_safe(payload.get('routine_id'))}"
            )
        elif event.kind == "proposal_created" and str(
            payload.get("proposed_by", event.source)
        ).startswith("engine.brain.model/"):
            messages.append(
                "LLM-suggestie: "
                f"{_safe(payload.get('capability_family'))} voor {_safe(event.goal_id)}"
            )
    return messages


def _safe(value: object, *, limit: int = 120) -> str:
    rendered = " ".join(str(value or "onbekend").split())
    return rendered[:limit]


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(str(value)))
    except ValueError:
        return 0


def _is_loopback(hostname: str) -> bool:
    if hostname == "localhost":
        return True
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False
