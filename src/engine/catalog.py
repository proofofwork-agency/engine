from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from importlib import metadata
from typing import Iterable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .interfaces import SpecialistBrain, TargetAdapter
from .models import CapabilitySpec, JsonObject, PluginManifest, ToolCall


class CatalogError(ValueError):
    pass


class CapabilityValidationError(CatalogError):
    pass


@dataclass(frozen=True)
class EnginePlugin:
    manifest: PluginManifest
    targets: tuple[TargetAdapter, ...] = ()
    specialists: tuple[SpecialistBrain, ...] = ()


@dataclass(frozen=True)
class CatalogSelection:
    target_id: str
    capability_id: str
    score: float
    reason: str

    def to_dict(self) -> JsonObject:
        return asdict(self)


@dataclass(frozen=True)
class CatalogSearchResult:
    selections: tuple[CatalogSelection, ...]
    candidate_count: int
    complete: bool
    omitted_count: int
    max_score: float
    retrieval_sufficient: bool

    def to_dict(self) -> JsonObject:
        return {
            "selections": [item.to_dict() for item in self.selections],
            "candidate_count": self.candidate_count,
            "complete": self.complete,
            "omitted_count": self.omitted_count,
            "max_score": self.max_score,
            "retrieval_sufficient": self.retrieval_sufficient,
        }


class Catalog:
    """Engine-owned catalog of versioned world and cognition plugins.

    Python entry points are only a discovery transport. Once loaded, every plugin
    is represented by Engine-native manifests and contracts; no packaging or
    provider object leaks into Heart or durable events.
    """

    entry_point_group = "engine.plugins"

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}
        self._targets: dict[str, TargetAdapter] = {}
        self._specialists: dict[str, SpecialistBrain] = {}
        self._capabilities: dict[str, dict[str, CapabilitySpec]] = {}
        self._generation = 0

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def targets(self) -> dict[str, TargetAdapter]:
        return dict(self._targets)

    @property
    def specialists(self) -> dict[str, SpecialistBrain]:
        return dict(self._specialists)

    def register(self, plugin: EnginePlugin) -> None:
        if plugin.manifest.contract_version != "engine.plugin/v1":
            raise CatalogError(
                f"unsupported plugin contract: {plugin.manifest.contract_version}"
            )
        if plugin.manifest.id in self._plugins:
            raise CatalogError(f"duplicate plugin id: {plugin.manifest.id}")

        target_ids = [target.manifest.id for target in plugin.targets]
        brain_ids = [brain.manifest.qualified_id for brain in plugin.specialists]
        if len(set(target_ids)) != len(target_ids):
            raise CatalogError(f"duplicate target id inside plugin {plugin.manifest.id}")
        if len(set(brain_ids)) != len(brain_ids):
            raise CatalogError(f"duplicate brain id inside plugin {plugin.manifest.id}")
        collisions = set(target_ids).intersection(self._targets)
        if collisions:
            raise CatalogError(f"target id already registered: {sorted(collisions)}")
        brain_collisions = set(brain_ids).intersection(self._specialists)
        if brain_collisions:
            raise CatalogError(f"brain id already registered: {sorted(brain_collisions)}")

        prepared: dict[str, dict[str, CapabilitySpec]] = {}
        for target in plugin.targets:
            if target.manifest.contract_version != "engine.target/v1":
                raise CatalogError(
                    f"unsupported target contract for {target.manifest.id}: "
                    f"{target.manifest.contract_version}"
                )
            if not target.manifest.id.strip():
                raise CatalogError("target id cannot be empty")
            if target.manifest.plugin_id != plugin.manifest.id:
                raise CatalogError(
                    f"target {target.manifest.id} claims plugin "
                    f"{target.manifest.plugin_id}, expected {plugin.manifest.id}"
                )
            capabilities = tuple(
                sorted(target.capabilities(), key=lambda capability: capability.id)
            )
            by_id = {capability.id: capability for capability in capabilities}
            if len(by_id) != len(capabilities):
                raise CatalogError(
                    f"duplicate capability id on target {target.manifest.id}"
                )
            for capability in capabilities:
                self._validate_spec(capability)
            prepared[target.manifest.id] = by_id

        for specialist in plugin.specialists:
            if specialist.manifest.contract_version != "engine.brain/v1":
                raise CatalogError(
                    f"unsupported brain contract for "
                    f"{specialist.manifest.qualified_id}: "
                    f"{specialist.manifest.contract_version}"
                )
            if not specialist.manifest.qualified_id.strip():
                raise CatalogError("brain id cannot be empty")
            if specialist.manifest.plugin_id != plugin.manifest.id:
                raise CatalogError(
                    f"brain {specialist.manifest.qualified_id} claims plugin "
                    f"{specialist.manifest.plugin_id}, expected {plugin.manifest.id}"
                )

        self._plugins[plugin.manifest.id] = plugin.manifest
        self._targets.update({target.manifest.id: target for target in plugin.targets})
        self._specialists.update(
            {brain.manifest.qualified_id: brain for brain in plugin.specialists}
        )
        self._capabilities.update(prepared)
        self._generation += 1

    def replace_specialist(self, brain: SpecialistBrain) -> None:
        brain_id = brain.manifest.qualified_id
        if brain_id not in self._specialists:
            raise CatalogError(f"unknown specialist: {brain.manifest.qualified_id}")
        existing = self._specialists[brain_id].manifest
        if brain.manifest.contract_version != "engine.brain/v1":
            raise CatalogError(
                f"unsupported brain contract for {brain_id}: "
                f"{brain.manifest.contract_version}"
            )
        if brain.manifest.plugin_id != existing.plugin_id:
            raise CatalogError(
                f"replacement brain {brain_id} changed plugin owner from "
                f"{existing.plugin_id} to {brain.manifest.plugin_id}"
            )
        self._specialists[brain_id] = brain
        self._generation += 1

    def target(self, target_id: str) -> TargetAdapter:
        try:
            return self._targets[target_id]
        except KeyError as error:
            raise CatalogError(f"unknown target: {target_id}") from error

    def specialist(self, brain_id: str) -> SpecialistBrain:
        try:
            return self._specialists[brain_id]
        except KeyError as error:
            raise CatalogError(f"unknown specialist: {brain_id}") from error

    def capabilities(self, target_id: str) -> tuple[CapabilitySpec, ...]:
        try:
            return tuple(
                self._capabilities[target_id][capability_id]
                for capability_id in sorted(self._capabilities[target_id])
            )
        except KeyError as error:
            raise CatalogError(f"unknown target: {target_id}") from error

    def capability(self, target_id: str, capability_id: str) -> CapabilitySpec:
        try:
            return self._capabilities[target_id][capability_id]
        except KeyError as error:
            raise CatalogError(
                f"unknown capability {capability_id} on target {target_id}"
            ) from error

    def validate_call(self, target_id: str, call: ToolCall) -> CapabilitySpec:
        if call.target_id is not None and call.target_id != target_id:
            raise CapabilityValidationError(
                f"call target {call.target_id} does not match binding {target_id}"
            )
        capability = self.capability(target_id, call.capability_id)
        try:
            Draft202012Validator(capability.input_schema).validate(call.arguments)
        except ValidationError as error:
            raise CapabilityValidationError(
                f"invalid input for {capability.id}: {error.message}"
            ) from error
        return capability

    def validate_output(
        self, target_id: str, capability_id: str, output: JsonObject
    ) -> None:
        capability = self.capability(target_id, capability_id)
        if not capability.output_schema:
            return
        try:
            Draft202012Validator(capability.output_schema).validate(output)
        except ValidationError as error:
            raise CapabilityValidationError(
                f"invalid output for {capability.id}: {error.message}"
            ) from error

    def search(
        self, target_id: str, terms: Iterable[str], limit: int = 16
    ) -> CatalogSearchResult:
        """Transparent lexical baseline for bounded capability projection.

        Retrieval is an explicit replaceable component. The baseline exposes its
        scores and reasons instead of hiding correctness state in embeddings.
        """
        needles = {term.casefold() for term in terms if term.strip()}
        selections: list[CatalogSelection] = []
        for capability in self.capabilities(target_id):
            haystack = f"{capability.id} {capability.description}".casefold()
            hits = sorted(term for term in needles if term in haystack)
            score = float(len(hits))
            selections.append(
                CatalogSelection(
                    target_id=target_id,
                    capability_id=capability.id,
                    score=score,
                    reason=(f"lexical matches: {', '.join(hits)}" if hits else "fallback"),
                )
            )
        selections.sort(key=lambda item: (-item.score, item.capability_id))
        max_score = max((item.score for item in selections), default=0.0)
        complete = len(selections) <= limit
        retrieval_sufficient = complete or max_score > 0
        chosen = tuple(selections[:limit]) if retrieval_sufficient else ()
        return CatalogSearchResult(
            selections=chosen,
            candidate_count=len(selections),
            complete=complete,
            omitted_count=max(0, len(selections) - len(chosen)),
            max_score=max_score,
            retrieval_sufficient=retrieval_sufficient,
        )

    def refresh(self) -> bool:
        """Atomically refresh dynamic capability bindings from registered targets."""
        refreshed: dict[str, dict[str, CapabilitySpec]] = {}
        for target_id, target in self._targets.items():
            capabilities = tuple(
                sorted(target.capabilities(), key=lambda capability: capability.id)
            )
            by_id = {capability.id: capability for capability in capabilities}
            if len(by_id) != len(capabilities):
                raise CatalogError(f"duplicate capability id on target {target_id}")
            for capability in capabilities:
                self._validate_spec(capability)
            refreshed[target_id] = by_id
        before = json.dumps(
            {
                target_id: [asdict(item) for item in capabilities.values()]
                for target_id, capabilities in sorted(self._capabilities.items())
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        after = json.dumps(
            {
                target_id: [asdict(item) for item in capabilities.values()]
                for target_id, capabilities in sorted(refreshed.items())
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if before == after:
            return False
        self._capabilities = refreshed
        self._generation += 1
        return True

    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.snapshot(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def snapshot(self) -> JsonObject:
        return {
            "generation": self.generation,
            "plugins": [
                asdict(manifest)
                for _, manifest in sorted(self._plugins.items())
            ],
            "targets": [
                {
                    "manifest": asdict(target.manifest),
                    "capabilities": [
                        asdict(capability)
                        for capability in self.capabilities(target.manifest.id)
                    ],
                }
                for _, target in sorted(self._targets.items())
            ],
            "specialists": [
                brain.manifest.to_dict()
                for _, brain in sorted(self._specialists.items())
            ],
        }

    def discover(self, group: str | None = None) -> tuple[str, ...]:
        loaded: list[str] = []
        for entry_point in metadata.entry_points(
            group=group or self.entry_point_group
        ):
            factory = entry_point.load()
            plugin = factory()
            if not isinstance(plugin, EnginePlugin):
                # The shared discovery group also carries engine.plugin/v2.
                # Legacy Catalog deliberately ignores it; PluginRegistryV2 owns
                # static-manifest comparison and v2 registration.
                if getattr(getattr(plugin, "manifest", None), "contract_version", None) == "engine.plugin/v2":
                    continue
                raise CatalogError(f"entry point {entry_point.name} returned an unknown plugin contract")
            self.register(plugin)
            if plugin.manifest.id not in loaded:
                loaded.append(plugin.manifest.id)
        return tuple(loaded)

    @staticmethod
    def _validate_spec(capability: CapabilitySpec) -> None:
        if not capability.id or "." not in capability.id or "/" not in capability.id:
            raise CatalogError(
                f"capability id must be qualified and versioned: {capability.id!r}"
            )
        if capability.default_timeout_ms <= 0:
            raise CatalogError(f"timeout must be positive for {capability.id}")
        try:
            Draft202012Validator.check_schema(capability.input_schema)
            if capability.output_schema:
                Draft202012Validator.check_schema(capability.output_schema)
        except SchemaError as error:
            raise CatalogError(f"invalid JSON Schema for {capability.id}: {error.message}") from error
