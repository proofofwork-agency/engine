from __future__ import annotations

from importlib import metadata

from engine_sdk import (
    PluginManifestV2,
    load_static_manifest,
    locate_distribution_manifest,
)

from engine import PluginRegistryV2


def installed_manifests() -> tuple[PluginManifestV2, ...]:
    manifests: dict[str, PluginManifestV2] = {}
    for entry_point in metadata.entry_points(group="engine.plugins"):
        distribution = entry_point.dist
        path = locate_distribution_manifest(distribution)
        if path is None:
            continue
        manifest = load_static_manifest(path)
        manifests[manifest.id] = manifest
    return tuple(manifests[key] for key in sorted(manifests))


def load_registry() -> PluginRegistryV2:
    registry = PluginRegistryV2()
    registry.discover_installed()
    return registry
