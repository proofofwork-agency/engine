from __future__ import annotations

import fnmatch
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from engine_sdk import (
    ActionRequestV1,
    AuthorizationV1,
    CapabilitySpecV2,
    PolicyDecisionV1,
    PolicyOutcome,
    PrivacyClass,
    RiskClass,
    StandingMandateV1,
)


class MandatePolicyV1:
    version = "engine.mandate-policy/v1"

    def evaluate(
        self,
        request: ActionRequestV1,
        capability: CapabilitySpecV2,
        mandate: StandingMandateV1 | None,
        *,
        manifest_version: str,
        now: datetime | None = None,
    ) -> PolicyDecisionV1:
        reasons: list[str] = []
        outcome = PolicyOutcome.ALLOW
        boundary = now or datetime.now(UTC)
        if mandate is None:
            return self._decision(request, PolicyOutcome.DENY, ("no standing mandate is bound",), None)
        if mandate.revoked:
            reasons.append("mandate is revoked")
        valid_from = _parse(mandate.valid_from)
        valid_until = _parse(mandate.valid_until)
        if boundary < valid_from:
            outcome = PolicyOutcome.DEFER
            reasons.append("mandate is not active yet")
        if boundary >= valid_until:
            outcome = PolicyOutcome.DENY
            reasons.append("mandate is expired")
        if mandate.revoked:
            outcome = PolicyOutcome.DENY
        if not _scoped(request.plugin_id, mandate.plugin_ids):
            outcome = PolicyOutcome.DENY
            reasons.append("plugin is outside mandate scope")
        if not _scoped(request.target_id, mandate.target_ids):
            outcome = PolicyOutcome.DENY
            reasons.append("target is outside mandate scope")
        if not _scoped(request.entity_id, mandate.entity_ids):
            outcome = PolicyOutcome.DENY
            reasons.append("entity is outside mandate scope")
        if not _scoped(request.capability_family, mandate.capability_families):
            outcome = PolicyOutcome.DENY
            reasons.append("capability family is outside mandate scope")
        expected_version = mandate.manifest_versions.get(request.plugin_id)
        if expected_version != manifest_version:
            outcome = PolicyOutcome.DENY
            reasons.append("plugin manifest version changed since enrollment")
        if capability.opaque:
            outcome = PolicyOutcome.DENY
            reasons.append("opaque capability is read-only")
        if capability.privacy_class not in {PrivacyClass.PUBLIC, PrivacyClass.LOCAL}:
            if not _scoped(capability.privacy_class.value, mandate.privacy_permissions):
                outcome = PolicyOutcome.DENY
                reasons.append("privacy class lacks explicit permission")
        if capability.risk_class is RiskClass.HIGH and mandate.limits.get("allow_high_risk") is not True:
            if outcome is PolicyOutcome.ALLOW:
                outcome = PolicyOutcome.REQUIRE_APPROVAL
            reasons.append("high-risk family is not activated by this mandate")
        limit_error = _limits_error(request.parameters, capability.limits, mandate.limits)
        if limit_error:
            outcome = PolicyOutcome.DENY
            reasons.append(limit_error)
        if not reasons:
            reasons.append("request is inside enrolled manifest and mandate scope")
        return self._decision(request, outcome, tuple(reasons), mandate.id)

    def authorize(
        self,
        request: ActionRequestV1,
        decision: PolicyDecisionV1,
        mandate: StandingMandateV1,
    ) -> AuthorizationV1:
        if decision.outcome is not PolicyOutcome.ALLOW:
            raise PermissionError(f"cannot authorize {decision.outcome}")
        request_deadline = _parse(request.deadline_at)
        mandate_deadline = _parse(mandate.valid_until)
        return AuthorizationV1(
            id="authorization:" + uuid4().hex,
            request_id=request.id,
            request_sha256=request.sha256,
            policy_decision_id=decision.id,
            mandate_id=mandate.id,
            target_id=request.target_id,
            entity_id=request.entity_id,
            capability_id=request.capability_id,
            parameter_limits=dict(mandate.limits),
            snapshot_id=request.snapshot_id,
            issued_at=datetime.now(UTC).isoformat(),
            expires_at=min(request_deadline, mandate_deadline).isoformat(),
        )

    def _decision(
        self,
        request: ActionRequestV1,
        outcome: PolicyOutcome,
        reasons: tuple[str, ...],
        mandate_id: str | None,
    ) -> PolicyDecisionV1:
        return PolicyDecisionV1(
            id="policy:" + uuid4().hex,
            request_id=request.id,
            outcome=outcome,
            reasons=reasons,
            policy_version=self.version,
            mandate_id=mandate_id,
        )


def _scoped(value: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern == "*" or fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _limits_error(
    parameters: dict[str, Any], capability_limits: dict[str, Any], mandate_limits: dict[str, Any]
) -> str | None:
    merged: dict[str, Any] = {}
    for source in (capability_limits, mandate_limits.get("parameters", {})):
        if isinstance(source, dict):
            merged.update(source)
    for name, limits in merged.items():
        if name not in parameters or not isinstance(limits, dict):
            continue
        value = parameters[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if limits.get("min") is not None and value < limits["min"]:
            return f"parameter {name} is below enrolled minimum"
        if limits.get("max") is not None and value > limits["max"]:
            return f"parameter {name} exceeds enrolled maximum"
    return None

