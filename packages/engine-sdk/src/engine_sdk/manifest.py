from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .models import (
    CapabilitySpecV2,
    ConditionV1,
    ContractError,
    ControlLayer,
    InvocationModeV2,
    PluginManifestV2,
    PreferencePromotionMode,
    PreferenceSpecV1,
    PrivacyClass,
    RiskClass,
    RoutineTemplateSpecV1,
)

_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")


def locate_distribution_manifest(distribution: Any) -> Path | None:
    """Locate wheel data or an editable project's static plugin manifest."""
    candidates: list[Path] = []
    for item in distribution.files or ():
        if Path(str(item)).name != "engine-plugin.toml":
            continue
        candidate = Path(distribution.locate_file(item))
        if candidate.is_file():
            candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0]
    direct_url = distribution.read_text("direct_url.json")
    if direct_url:
        try:
            parsed = urlparse(str(json.loads(direct_url)["url"]))
            if parsed.scheme == "file":
                editable = Path(unquote(parsed.path)) / "engine-plugin.toml"
                if editable.is_file():
                    return editable
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    installed = Path(distribution.locate_file("engine-plugin.toml"))
    if installed.is_file() and not candidates:
        return installed
    # A source-tree ``*.egg-info`` discovered through PYTHONPATH has neither
    # wheel data paths nor direct_url.json. Its locate root is usually ``src``.
    source_root = Path(distribution.locate_file("."))
    for parent in (source_root, source_root.parent, source_root.parent.parent):
        candidate = parent / "engine-plugin.toml"
        if candidate.is_file():
            return candidate
    return None


def load_static_manifest(path: str | Path) -> PluginManifestV2:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "engine-plugin.toml"
    try:
        raw = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ContractError(f"cannot load {manifest_path}: {exc}") from exc
    return manifest_from_dict(raw)


def manifest_from_dict(raw: Mapping[str, Any]) -> PluginManifestV2:
    plugin = _table(raw, "plugin")
    declarations = _table(raw, "declarations", required=False)
    needs = _table(raw, "needs", required=False)
    store = _table(raw, "store", required=False)
    capability_rows = raw.get("capability_families", [])
    if not isinstance(capability_rows, list):
        raise ContractError("capability_families must be an array of tables")
    capabilities = tuple(_capability(item, str(plugin.get("id", ""))) for item in capability_rows)
    preference_rows = raw.get("preferences", [])
    if not isinstance(preference_rows, list):
        raise ContractError("preferences must be an array of tables")
    preferences = tuple(
        _preference(item, str(plugin.get("id", ""))) for item in preference_rows
    )
    routine_rows = raw.get("routines", [])
    if not isinstance(routine_rows, list):
        raise ContractError("routines must be an array of tables")
    routines = tuple(
        _routine(item, str(plugin.get("id", ""))) for item in routine_rows
    )
    manifest = PluginManifestV2(
        id=str(plugin.get("id", "")),
        version=str(plugin.get("version", "")),
        engine_api=str(plugin.get("engine_api", "")),
        description=str(plugin.get("description", "")),
        contract_version=str(plugin.get("contract_version", "")),
        world_providers=_strings(declarations, "world_providers"),
        controllers=_strings(declarations, "controllers"),
        executors=_strings(declarations, "executors"),
        effect_oracles=_strings(declarations, "effect_oracles"),
        specialists=_strings(declarations, "specialists"),
        entity_types=_strings(declarations, "entity_types"),
        relation_types=_strings(declarations, "relation_types"),
        observation_types=_strings(declarations, "observation_types"),
        capabilities=capabilities,
        lifecycle_observers=_strings(declarations, "lifecycle_observers"),
        experience_providers=_strings(declarations, "experience_providers"),
        preference_specs=preferences,
        routine_compilers=_strings(declarations, "routine_compilers"),
        routine_templates=routines,
        network_needs=_strings(needs, "network"),
        filesystem_needs=_strings(needs, "filesystem"),
        secret_needs=_strings(needs, "secrets"),
        privacy_needs=_strings(needs, "privacy"),
        store_identity=str(store.get("identity", "")),
        store_schema_version=int(store.get("schema_version", 1)),
    )
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: PluginManifestV2) -> None:
    if not _ID.fullmatch(manifest.id):
        raise ContractError("plugin.id must be a dotted stable lowercase identity")
    if not manifest.engine_api:
        raise ContractError("plugin.engine_api must be declared")
    if (
        not manifest.world_providers
        and not manifest.specialists
        and not manifest.lifecycle_observers
    ):
        raise ContractError(
            "plugin must declare a world provider, specialist or lifecycle observer"
        )
    if manifest.capabilities and not manifest.world_providers:
        raise ContractError("capability families require a world provider")
    if any(item.plugin_id != manifest.id for item in manifest.capabilities):
        raise ContractError("capability plugin_id must match plugin.id")
    declared_families = {item.family for item in manifest.capabilities}
    for preference in manifest.preference_specs:
        if preference.plugin_id != manifest.id:
            raise ContractError("preference plugin_id must match plugin.id")
        if preference.capability_family not in declared_families:
            raise ContractError("preference capability_family must be declared")
    if manifest.preference_specs and not manifest.experience_providers:
        raise ContractError("preference specs require an experience provider")
    for routine in manifest.routine_templates:
        if routine.plugin_id != manifest.id:
            raise ContractError("routine template plugin_id must match plugin.id")
        if routine.capability_family not in declared_families:
            raise ContractError("routine capability_family must be declared")
    if manifest.routine_templates and not manifest.routine_compilers:
        raise ContractError("routine templates require a routine compiler")
    if manifest.routine_templates and not manifest.experience_providers:
        raise ContractError("routine templates require an experience provider")
    actuating = [
        item for item in manifest.capabilities
        if item.control_layer is not ControlLayer.QUERY
    ]
    if actuating and (not manifest.controllers or not manifest.executors or not manifest.effect_oracles):
        raise ContractError(
            "mutable capability families require controller, executor and effect oracle"
        )
    if manifest.store_schema_version < 1:
        raise ContractError("store schema version must be positive")


def compare_manifests(
    static: PluginManifestV2, loaded: PluginManifestV2
) -> tuple[str, ...]:
    mismatches: list[str] = []
    exact_fields = (
        "id", "version", "engine_api", "contract_version", "world_providers",
        "controllers", "executors", "effect_oracles", "specialists",
        "entity_types", "relation_types", "observation_types",
        "lifecycle_observers", "experience_providers", "routine_compilers",
    )
    for name in exact_fields:
        if getattr(static, name) != getattr(loaded, name):
            mismatches.append(name)
    static_caps = {item.family: item.to_dict() for item in static.capabilities}
    loaded_caps = {item.family: item.to_dict() for item in loaded.capabilities}
    if static_caps != loaded_caps:
        mismatches.append("capability_families")
    static_preferences = {item.id: item.to_dict() for item in static.preference_specs}
    loaded_preferences = {item.id: item.to_dict() for item in loaded.preference_specs}
    if static_preferences != loaded_preferences:
        mismatches.append("preferences")
    static_routines = {item.id: item.to_dict() for item in static.routine_templates}
    loaded_routines = {item.id: item.to_dict() for item in loaded.routine_templates}
    if static_routines != loaded_routines:
        mismatches.append("routines")
    return tuple(mismatches)


def _capability(raw: object, plugin_id: str) -> CapabilitySpecV2:
    if not isinstance(raw, Mapping):
        raise ContractError("capability family must be a table")
    preconditions = raw.get("preconditions", [])
    if not isinstance(preconditions, list):
        raise ContractError("capability preconditions must be a list")
    return CapabilitySpecV2(
        id=str(raw.get("id", "")),
        plugin_id=plugin_id,
        family=str(raw.get("family", "")),
        version=str(raw.get("version", "1.0.0")),
        description=str(raw.get("description", "")),
        input_schema=dict(raw.get("input_schema", {})),
        effect_schema=dict(raw.get("effect_schema", {})),
        control_layer=ControlLayer(str(raw.get("control_layer", "query"))),
        invocation_mode=InvocationModeV2(str(raw.get("invocation_mode", "immediate"))),
        risk_class=RiskClass(str(raw.get("risk_class", "read_only"))),
        privacy_class=PrivacyClass(str(raw.get("privacy_class", "local"))),
        idempotent=bool(raw.get("idempotent", False)),
        deadline_ms=int(raw.get("deadline_ms", 30_000)),
        units=dict(raw.get("units", {})),
        limits=dict(raw.get("limits", {})),
        preconditions=tuple(ConditionV1.from_dict(item) for item in preconditions),
        effect_measurements=tuple(str(item) for item in raw.get("effect_measurements", ())),
        recovery=str(raw.get("recovery", "observe_and_defer")),
        opaque=bool(raw.get("opaque", False)),
    )


def _preference(raw: object, plugin_id: str) -> PreferenceSpecV1:
    if not isinstance(raw, Mapping):
        raise ContractError("preference must be a table")
    schema = raw.get("value_schema", {})
    if not isinstance(schema, Mapping):
        raise ContractError("preference value_schema must be a table")
    return PreferenceSpecV1(
        id=str(raw.get("id", "")),
        plugin_id=plugin_id,
        capability_family=str(raw.get("capability_family", "")),
        value_schema=dict(schema),
        unit=str(raw["unit"]) if raw.get("unit") is not None else None,
        promotion_mode=PreferencePromotionMode(
            str(raw.get("promotion_mode", "explicit_only"))
        ),
        description=str(raw.get("description", "")),
    )


def _routine(raw: object, plugin_id: str) -> RoutineTemplateSpecV1:
    if not isinstance(raw, Mapping):
        raise ContractError("routine must be a table")
    for name in ("pattern_schema", "guard_schema", "goal_schema"):
        if not isinstance(raw.get(name, {}), Mapping):
            raise ContractError(f"routine {name} must be a table")
    return RoutineTemplateSpecV1(
        id=str(raw.get("id", "")),
        plugin_id=plugin_id,
        capability_family=str(raw.get("capability_family", "")),
        pattern_schema=dict(raw.get("pattern_schema", {})),
        guard_schema=dict(raw.get("guard_schema", {})),
        goal_schema=dict(raw.get("goal_schema", {})),
        priority=int(raw.get("priority", 0)),
        shadow_days=int(raw.get("shadow_days", 7)),
        minimum_shadow_opportunities=int(
            raw.get("minimum_shadow_opportunities", 3)
        ),
        minimum_shadow_agreement=float(
            raw.get("minimum_shadow_agreement", 0.80)
        ),
        trigger_window_seconds=int(raw.get("trigger_window_seconds", 1800)),
        description=str(raw.get("description", "")),
    )


def _table(
    raw: Mapping[str, Any], name: str, *, required: bool = True
) -> Mapping[str, Any]:
    value = raw.get(name)
    if value is None and not required:
        return {}
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be a table")
    return value


def _strings(raw: Mapping[str, Any], name: str) -> tuple[str, ...]:
    value = raw.get(name, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractError(f"{name} must be an array of strings")
    return tuple(value)
