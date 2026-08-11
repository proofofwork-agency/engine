from __future__ import annotations

from .models import (
    AuthorizationV1,
    ContractError,
    EvidenceGrade,
    ExecutionStateV2,
    PluginManifestV2,
    TargetObservationV2,
    artifact_sha256,
)
from .protocols import WorldPluginV2


def check_plugin(plugin: WorldPluginV2) -> tuple[str, ...]:
    """Run dependency-free structural checks used by generated plugin tests."""
    failures: list[str] = []
    manifest: PluginManifestV2 = plugin.manifest
    lifecycle_observers = tuple(getattr(plugin, "lifecycle_observers", ()))
    experience_providers = tuple(getattr(plugin, "experience_providers", ()))
    routine_compilers = tuple(getattr(plugin, "routine_compilers", ()))
    autonomy_strategies = tuple(getattr(plugin, "autonomy_strategies", ()))
    goal_template_compilers = tuple(
        getattr(plugin, "goal_template_compilers", ())
    )
    if manifest.contract_version == "engine.plugin/v3":
        _check_v3_roles(plugin, manifest, failures)
    if {str(item.id) for item in lifecycle_observers} != set(
        manifest.lifecycle_observers
    ):
        failures.append("loaded lifecycle observers differ from manifest")
    for observer in lifecycle_observers:
        if observer.plugin_id != manifest.id:
            failures.append(f"lifecycle observer {observer.id} has wrong plugin_id")
    if {str(item.id) for item in experience_providers} != set(
        manifest.experience_providers
    ):
        failures.append("loaded experience providers differ from manifest")
    for provider in experience_providers:
        if provider.plugin_id != manifest.id:
            failures.append(f"experience provider {provider.id} has wrong plugin_id")
        try:
            batch = provider.read(None, 1)
        except Exception as exc:
            failures.append(f"experience provider {provider.id} read failed: {exc}")
            continue
        if any(item.plugin_id != manifest.id for item in batch.signals):
            failures.append(f"experience provider {provider.id} returned another plugin")
    if {str(item.id) for item in routine_compilers} != set(manifest.routine_compilers):
        failures.append("loaded routine compilers differ from manifest")
    declared_templates = {item.id for item in manifest.routine_templates}
    for compiler in routine_compilers:
        if compiler.plugin_id != manifest.id:
            failures.append(f"routine compiler {compiler.id} has wrong plugin_id")
        if not set(compiler.supported_templates) <= declared_templates:
            failures.append(f"routine compiler {compiler.id} exposes undeclared templates")
    declared_strategies = {item.id: item for item in manifest.autonomy_strategies}
    if {str(item.id) for item in autonomy_strategies} != set(declared_strategies):
        failures.append("loaded autonomy strategies differ from manifest")
    for strategy in autonomy_strategies:
        if strategy.plugin_id != manifest.id:
            failures.append(f"autonomy strategy {strategy.id} has wrong plugin_id")
        declared = declared_strategies.get(str(strategy.id))
        if declared is not None and strategy.spec.to_dict() != declared.to_dict():
            failures.append(f"autonomy strategy {strategy.id} spec differs from manifest")
    if {str(item.id) for item in goal_template_compilers} != set(
        manifest.goal_template_compilers
    ):
        failures.append("loaded goal template compilers differ from manifest")
    declared_goal_templates = {item.id for item in manifest.goal_templates}
    compiled_goal_templates: list[str] = []
    for compiler in goal_template_compilers:
        if compiler.plugin_id != manifest.id:
            failures.append(f"goal template compiler {compiler.id} has wrong plugin_id")
        if not set(compiler.supported_templates) <= declared_goal_templates:
            failures.append(
                f"goal template compiler {compiler.id} exposes undeclared templates"
            )
        compiled_goal_templates.extend(str(item) for item in compiler.supported_templates)
    if (
        set(compiled_goal_templates) != declared_goal_templates
        or len(compiled_goal_templates) != len(set(compiled_goal_templates))
    ):
        failures.append(
            "goal template compilers must cover every declared template exactly once"
        )
    if not plugin.providers and manifest.world_providers:
        failures.append("manifest declares providers but plugin loaded none")
    provider_targets: set[str] = set()
    for provider in plugin.providers:
        if provider.plugin_id != manifest.id:
            failures.append(f"provider {provider.target_id} has wrong plugin_id")
        if provider.target_id in provider_targets:
            failures.append(f"duplicate target_id: {provider.target_id}")
        provider_targets.add(provider.target_id)
        try:
            observed: TargetObservationV2 = provider.observe()
        except Exception as exc:  # conformance must report adapter failures honestly
            failures.append(f"provider {provider.target_id} observe failed: {exc}")
            continue
        if observed.target_id != provider.target_id:
            failures.append(f"provider {provider.target_id} returned another target")
        if any(item.evidence_grade is EvidenceGrade.INFERRED for item in observed.observations):
            # Inference is allowed, but the fake/reference provider should disclose it.
            if "inferred" not in observed.coverage:
                failures.append("inferred observations lack explicit coverage")
        discovered = {item.family for item in provider.discover()}
        declared = {item.family for item in manifest.capabilities}
        if not discovered <= declared:
            failures.append(
                f"provider exposes undeclared mutable families: {sorted(discovered - declared)}"
            )
    return tuple(failures)


def _check_v3_roles(
    plugin: WorldPluginV2,
    manifest: PluginManifestV2,
    failures: list[str],
) -> None:
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
            failures.append(f"loaded {label} differ from manifest")
        for item in loaded:
            if getattr(item, "plugin_id", None) != manifest.id:
                failures.append(
                    f"{label.removesuffix('s')} {getattr(item, 'id', '')} has wrong plugin_id"
                )


def assert_authorization_matches(
    authorization: AuthorizationV1, request_sha256: str
) -> None:
    if authorization.request_sha256 != request_sha256:
        raise ContractError("authorization is bound to another request")


def assert_receipt_terminal(state: ExecutionStateV2) -> None:
    if state not in {
        ExecutionStateV2.SUCCEEDED,
        ExecutionStateV2.PARTIAL,
        ExecutionStateV2.FAILED,
        ExecutionStateV2.CANCELLED,
        ExecutionStateV2.UNKNOWN,
    }:
        raise ContractError(f"receipt is not terminal: {state}")


def observation_fingerprint(observation: TargetObservationV2) -> str:
    return artifact_sha256(observation)
