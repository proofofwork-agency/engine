from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from engine_sdk import (
    CapabilitySpecV2,
    ControlLayer,
    EntityV1,
    EvidenceGrade,
    ObservationV1,
    PluginManifestV2,
    PrivacyClass,
    RiskClass,
    TargetObservationV2,
    compare_manifests,
    load_static_manifest,
    locate_distribution_manifest,
)


@dataclass(frozen=True)
class RegisteredPluginV2:
    plugin: Any
    static_manifest: PluginManifestV2
    mutation_enabled: bool


class PluginRegistryV2:
    def __init__(self) -> None:
        self._plugins: dict[str, RegisteredPluginV2] = {}
        self._targets: dict[str, Any] = {}
        self._lifecycle_observers: dict[str, Any] = {}
        self._experience_providers: dict[str, Any] = {}
        self._routine_compilers: dict[str, Any] = {}
        self._autonomy_strategies: dict[str, Any] = {}
        self._goal_template_compilers: dict[str, Any] = {}
        self._discovery_failures: dict[str, str] = {}

    def register(self, plugin: Any, static_manifest_path: str | Path) -> None:
        static = load_static_manifest(static_manifest_path)
        loaded = plugin.manifest
        mismatches = compare_manifests(static, loaded)
        if mismatches:
            raise ValueError(
                f"loaded manifest differs from static manifest in: {', '.join(mismatches)}"
            )
        if static.id in self._plugins:
            raise ValueError(f"duplicate plugin id: {static.id}")
        providers = tuple(plugin.providers)
        if static.contract_version == "engine.plugin/v3":
            self._validate_v3_roles(plugin, static)
        for provider in providers:
            if provider.target_id in self._targets:
                raise ValueError(f"duplicate target id: {provider.target_id}")
            if provider.plugin_id != static.id:
                raise ValueError("provider plugin identity mismatch")
        lifecycle_observers = tuple(getattr(plugin, "lifecycle_observers", ()))
        declared_observers = set(static.lifecycle_observers)
        loaded_observers = {str(item.id) for item in lifecycle_observers}
        if loaded_observers != declared_observers:
            raise ValueError("loaded lifecycle observers differ from static manifest")
        for observer in lifecycle_observers:
            if observer.plugin_id != static.id:
                raise ValueError("lifecycle observer plugin identity mismatch")
            if observer.id in self._lifecycle_observers:
                raise ValueError(f"duplicate lifecycle observer id: {observer.id}")
        experience_providers = tuple(getattr(plugin, "experience_providers", ()))
        declared_experience = set(static.experience_providers)
        loaded_experience = {str(item.id) for item in experience_providers}
        if loaded_experience != declared_experience:
            raise ValueError("loaded experience providers differ from static manifest")
        for provider in experience_providers:
            if provider.plugin_id != static.id:
                raise ValueError("experience provider plugin identity mismatch")
            if provider.id in self._experience_providers:
                raise ValueError(f"duplicate experience provider id: {provider.id}")
        routine_compilers = tuple(getattr(plugin, "routine_compilers", ()))
        declared_compilers = set(static.routine_compilers)
        loaded_compilers = {str(item.id) for item in routine_compilers}
        if loaded_compilers != declared_compilers:
            raise ValueError("loaded routine compilers differ from static manifest")
        templates = {item.id for item in static.routine_templates}
        for compiler in routine_compilers:
            if compiler.plugin_id != static.id:
                raise ValueError("routine compiler plugin identity mismatch")
            if not set(compiler.supported_templates) <= templates:
                raise ValueError("routine compiler exposes an undeclared template")
            if compiler.id in self._routine_compilers:
                raise ValueError(f"duplicate routine compiler id: {compiler.id}")
        autonomy_strategies = tuple(getattr(plugin, "autonomy_strategies", ()))
        declared_strategies = {item.id: item for item in static.autonomy_strategies}
        if {str(item.id) for item in autonomy_strategies} != set(declared_strategies):
            raise ValueError("loaded autonomy strategies differ from static manifest")
        for strategy in autonomy_strategies:
            if strategy.plugin_id != static.id:
                raise ValueError("autonomy strategy plugin identity mismatch")
            if strategy.spec.to_dict() != declared_strategies[str(strategy.id)].to_dict():
                raise ValueError("loaded autonomy strategy spec differs from static manifest")
            if strategy.id in self._autonomy_strategies:
                raise ValueError(f"duplicate autonomy strategy id: {strategy.id}")
        goal_template_compilers = tuple(
            getattr(plugin, "goal_template_compilers", ())
        )
        if {str(item.id) for item in goal_template_compilers} != set(
            static.goal_template_compilers
        ):
            raise ValueError("loaded goal template compilers differ from static manifest")
        declared_goal_templates = {item.id for item in static.goal_templates}
        compiled_goal_templates: list[str] = []
        for compiler in goal_template_compilers:
            if compiler.plugin_id != static.id:
                raise ValueError("goal template compiler plugin identity mismatch")
            if not set(compiler.supported_templates) <= declared_goal_templates:
                raise ValueError("goal template compiler exposes an undeclared template")
            if compiler.id in self._goal_template_compilers:
                raise ValueError(f"duplicate goal template compiler id: {compiler.id}")
            compiled_goal_templates.extend(str(item) for item in compiler.supported_templates)
        if (
            set(compiled_goal_templates) != declared_goal_templates
            or len(compiled_goal_templates) != len(set(compiled_goal_templates))
        ):
            raise ValueError(
                "goal template compilers must cover every declared template exactly once"
            )
        self._plugins[static.id] = RegisteredPluginV2(plugin, static, True)
        self._targets.update({provider.target_id: provider for provider in providers})
        self._lifecycle_observers.update(
            {observer.id: observer for observer in lifecycle_observers}
        )
        self._experience_providers.update(
            {provider.id: provider for provider in experience_providers}
        )
        self._routine_compilers.update(
            {compiler.id: compiler for compiler in routine_compilers}
        )
        self._autonomy_strategies.update(
            {strategy.id: strategy for strategy in autonomy_strategies}
        )
        self._goal_template_compilers.update(
            {compiler.id: compiler for compiler in goal_template_compilers}
        )

    @staticmethod
    def _validate_v3_roles(plugin: Any, manifest: PluginManifestV2) -> None:
        roles = (
            ("world providers", tuple(plugin.providers), manifest.world_providers),
            ("controllers", tuple(plugin.controllers), manifest.controllers),
            ("executors", tuple(plugin.executors), manifest.executors),
            ("effect oracles", tuple(plugin.oracles), manifest.effect_oracles),
            ("specialists", tuple(plugin.specialists), manifest.specialists),
        )
        for label, loaded, declared in roles:
            loaded_ids = tuple(str(getattr(item, "id", "")) for item in loaded)
            if set(loaded_ids) != set(declared) or len(loaded_ids) != len(set(loaded_ids)):
                raise ValueError(f"loaded {label} differ from static manifest")
            if any(getattr(item, "plugin_id", None) != manifest.id for item in loaded):
                raise ValueError(f"loaded {label} contain another plugin identity")

    def register_v1_observe_only(self, plugin: Any) -> None:
        """Compatibility bridge: v1 facts are visible, v1 execute is never exposed."""
        plugin_id = str(plugin.manifest.id)
        if plugin_id in self._plugins:
            raise ValueError(f"duplicate plugin id: {plugin_id}")
        providers = tuple(
            V1ObserveOnlyProvider(plugin_id, target) for target in plugin.targets
        )
        manifest = PluginManifestV2(
            id=plugin_id,
            version=str(plugin.manifest.version),
            engine_api=">=2.0,<3",
            description=f"Observe-only compatibility bridge for {plugin_id}",
            world_providers=tuple(item.target_id for item in providers),
            controllers=(), executors=(), effect_oracles=(), specialists=(),
            entity_types=("engine.v1.target",), relation_types=(),
            observation_types=("legacy.state",), capabilities=(),
            store_identity=f"{plugin_id}.v1-bridge",
            contract_version="engine.plugin/v2",
        )
        bridged = _BridgedPlugin(manifest, providers)
        self._plugins[plugin_id] = RegisteredPluginV2(bridged, manifest, False)
        for provider in providers:
            if provider.target_id in self._targets:
                raise ValueError(f"duplicate target id: {provider.target_id}")
            self._targets[provider.target_id] = provider

    def discover_installed(self) -> tuple[str, ...]:
        loaded_ids: list[str] = []
        entry_points = metadata.entry_points(group="engine.plugins")
        for entry_point in sorted(entry_points, key=lambda item: item.name):
            try:
                distribution = entry_point.dist
                static_path = locate_distribution_manifest(distribution)
                if static_path is None:
                    self._discovery_failures[entry_point.name] = (
                        "static engine-plugin.toml was not found"
                    )
                    continue
                static = load_static_manifest(static_path)
                factory = entry_point.load()
                plugin = factory()
                if getattr(plugin.manifest, "contract_version", None) not in {
                    "engine.plugin/v2", "engine.plugin/v3"
                }:
                    continue
                if static.id in self._plugins:
                    continue
                self.register(plugin, static_path)
                loaded_ids.append(static.id)
            except Exception as exc:
                self._discovery_failures[entry_point.name] = (
                    f"{type(exc).__name__}: {exc}"
                )
        return tuple(loaded_ids)

    @property
    def providers(self) -> tuple[Any, ...]:
        return tuple(self._targets[key] for key in sorted(self._targets))

    @property
    def manifests(self) -> tuple[PluginManifestV2, ...]:
        return tuple(
            self._plugins[key].static_manifest for key in sorted(self._plugins)
        )

    @property
    def lifecycle_observers(self) -> tuple[Any, ...]:
        return tuple(
            self._lifecycle_observers[key]
            for key in sorted(self._lifecycle_observers)
        )

    @property
    def experience_providers(self) -> tuple[Any, ...]:
        return tuple(
            self._experience_providers[key]
            for key in sorted(self._experience_providers)
        )

    @property
    def routine_compilers(self) -> tuple[Any, ...]:
        return tuple(
            self._routine_compilers[key] for key in sorted(self._routine_compilers)
        )

    @property
    def autonomy_strategies(self) -> tuple[Any, ...]:
        return tuple(
            self._autonomy_strategies[key]
            for key in sorted(self._autonomy_strategies)
        )

    @property
    def goal_template_compilers(self) -> tuple[Any, ...]:
        return tuple(
            self._goal_template_compilers[key]
            for key in sorted(self._goal_template_compilers)
        )

    @property
    def discovery_failures(self) -> dict[str, str]:
        return dict(self._discovery_failures)

    def preference(self, plugin_id: str, preference_id: str) -> Any | None:
        registered = self._plugins.get(plugin_id)
        if registered is None:
            return None
        return next(
            (
                item for item in registered.static_manifest.preference_specs
                if item.id == preference_id
            ),
            None,
        )

    def routine_template(self, plugin_id: str, template_id: str) -> Any | None:
        registered = self._plugins.get(plugin_id)
        if registered is None:
            return None
        return next(
            (
                item for item in registered.static_manifest.routine_templates
                if item.id == template_id
            ),
            None,
        )

    def routine_compiler(self, plugin_id: str, template_id: str) -> Any | None:
        return next(
            (
                item for item in self._routine_compilers.values()
                if item.plugin_id == plugin_id
                and template_id in item.supported_templates
            ),
            None,
        )

    def autonomy_strategy(self, plugin_id: str, strategy_id: str) -> Any | None:
        strategy = self._autonomy_strategies.get(strategy_id)
        if strategy is None or strategy.plugin_id != plugin_id:
            return None
        return strategy

    def goal_template(self, plugin_id: str, template_id: str) -> Any | None:
        registered = self._plugins.get(plugin_id)
        if registered is None:
            return None
        return next(
            (
                item for item in registered.static_manifest.goal_templates
                if item.id == template_id
            ),
            None,
        )

    def goal_template_compiler(self, plugin_id: str, template_id: str) -> Any | None:
        return next(
            (
                item for item in self._goal_template_compilers.values()
                if item.plugin_id == plugin_id
                and template_id in item.supported_templates
            ),
            None,
        )

    def plugin(self, plugin_id: str) -> RegisteredPluginV2:
        return self._plugins[plugin_id]

    def plugin_for_target(self, target_id: str) -> RegisteredPluginV2:
        provider = self._targets[target_id]
        return self._plugins[provider.plugin_id]

    def capabilities_for_target(self, target_id: str) -> tuple[CapabilitySpecV2, ...]:
        provider = self._targets[target_id]
        registered = self._plugins[provider.plugin_id]
        declared = {
            item.family: item for item in registered.static_manifest.capabilities
        }
        result: list[CapabilitySpecV2] = []
        for discovered in provider.discover():
            known = declared.get(discovered.family)
            if known is not None and discovered.id == known.id:
                result.append(known)
            else:
                result.append(
                    CapabilitySpecV2(
                        id=f"{provider.plugin_id}.opaque.{discovered.family}/v1",
                        plugin_id=provider.plugin_id,
                        family=discovered.family,
                        version=discovered.version,
                        description=f"Opaque read-only discovery: {discovered.description}",
                        input_schema={}, effect_schema={},
                        control_layer=ControlLayer.QUERY,
                        invocation_mode=discovered.invocation_mode,
                        risk_class=RiskClass.READ_ONLY,
                        privacy_class=discovered.privacy_class,
                        idempotent=True, deadline_ms=discovered.deadline_ms,
                        units=discovered.units, limits={}, effect_measurements=(),
                        recovery="observe_only", opaque=True,
                    )
                )
        return tuple(sorted(result, key=lambda item: item.family))

    def capability(
        self, target_id: str, family: str
    ) -> CapabilitySpecV2 | None:
        return next(
            (
                item for item in self.capabilities_for_target(target_id)
                if item.family == family
            ),
            None,
        )

    def controller(self, plugin_id: str, family: str) -> Any:
        registered = self._plugins[plugin_id]
        return next(
            item for item in registered.plugin.controllers
            if family in item.supported_families
        )

    def executor(self, plugin_id: str) -> Any:
        registered = self._plugins[plugin_id]
        if not registered.mutation_enabled:
            raise PermissionError("v1 compatibility plugins are observe-only")
        return next(iter(registered.plugin.executors))

    def oracle(self, plugin_id: str, family: str) -> Any:
        registered = self._plugins[plugin_id]
        return next(
            item for item in registered.plugin.oracles
            if family in item.supported_families
        )

    def specialists(self, family: str | None = None) -> tuple[Any, ...]:
        values = tuple(
            specialist
            for item in self._plugins.values()
            for specialist in item.plugin.specialists
        )
        if family is None:
            return values
        return tuple(
            item for item in values if family in item.supported_families
        )

    def manifest_fingerprint(self, plugin_id: str) -> str:
        return self._plugins[plugin_id].static_manifest.fingerprint

    def mutation_enabled(self, plugin_id: str) -> bool:
        return self._plugins[plugin_id].mutation_enabled


class V1ObserveOnlyProvider:
    poll_interval_seconds = 5.0
    freshness_seconds = 30.0

    def __init__(self, plugin_id: str, target: Any):
        self.plugin_id = plugin_id
        self.target = target
        self.target_id = str(target.manifest.id)

    def discover(self) -> tuple[CapabilitySpecV2, ...]:
        return tuple(
            CapabilitySpecV2(
                id=f"{self.plugin_id}.opaque.{item.local_name}/v1",
                plugin_id=self.plugin_id, family=f"v1.{item.local_name}",
                version=item.version, description=item.description,
                input_schema={}, effect_schema={}, control_layer=ControlLayer.QUERY,
                invocation_mode=item.invocation_mode,
                risk_class=RiskClass.READ_ONLY, privacy_class=PrivacyClass.LOCAL,
                idempotent=True, deadline_ms=item.default_timeout_ms,
                opaque=True,
            )
            for item in self.target.capabilities()
        )

    def observe(self) -> TargetObservationV2:
        old = self.target.observe()
        entity = EntityV1(
            id=f"v1-target:{self.target_id}", target_id=self.target_id,
            entity_type="engine.v1.target", source=self.plugin_id,
            name=self.target_id, attributes={"contract": "engine.target/v1"},
        )
        observation = ObservationV1(
            id=f"{entity.id}:state:r{old.revision}", entity_id=entity.id,
            property="legacy.state", value=old.state, source=self.plugin_id,
            observed_at=old.observed_at, evidence_grade=EvidenceGrade.OBSERVED,
            quality=1.0, coverage="target-defined",
        )
        return TargetObservationV2(
            self.target_id, old.revision, old.observed_at, (entity,), (),
            (observation,), {"legacy.state": "target-defined"}, self.plugin_id,
        )

    def subscribe(self, wake: Any) -> Any:
        subscribe = getattr(self.target, "subscribe", None)
        return subscribe(wake) if subscribe is not None else None


@dataclass(frozen=True)
class _BridgedPlugin:
    manifest: PluginManifestV2
    providers: tuple[Any, ...]
    controllers: tuple[Any, ...] = ()
    executors: tuple[Any, ...] = ()
    oracles: tuple[Any, ...] = ()
    specialists: tuple[Any, ...] = ()
    experience_providers: tuple[Any, ...] = ()
    routine_compilers: tuple[Any, ...] = ()
    lifecycle_observers: tuple[Any, ...] = ()
    autonomy_strategies: tuple[Any, ...] = ()
    goal_template_compilers: tuple[Any, ...] = ()
