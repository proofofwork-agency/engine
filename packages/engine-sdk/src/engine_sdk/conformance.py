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
    experience_providers = tuple(getattr(plugin, "experience_providers", ()))
    routine_compilers = tuple(getattr(plugin, "routine_compilers", ()))
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
