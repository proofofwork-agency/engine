from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from engine_sdk import (
    BrainDecisionV2,
    DecisionKindV2,
    GoalSpecV2,
    ProposedActionV1,
)


class StructuredWorldDecisionModel(Protocol):
    """Provider-neutral model seam; output is untrusted structured data."""

    @property
    def provider_id(self) -> str: ...

    @property
    def model_id(self) -> str: ...

    def decide(self, context: dict[str, object]) -> dict[str, object]: ...


class ModelExecutiveBrainV2:
    def __init__(self, model: StructuredWorldDecisionModel):
        self.model = model
        self.id = f"engine.brain.model/{model.provider_id}/{model.model_id}"

    def decide(
        self, goal: GoalSpecV2, context_projection: dict[str, object]
    ) -> BrainDecisionV2:
        raw = self.model.decide(context_projection)
        if not isinstance(raw, dict):
            raise ValueError("model output must be an object")
        kind = DecisionKindV2(str(raw.get("kind", "")))
        rationale = str(raw.get("rationale", ""))
        if kind is DecisionKindV2.PROPOSE_EFFECT:
            proposal = raw.get("proposed_action")
            if not isinstance(proposal, dict):
                raise ValueError("PROPOSE_EFFECT requires proposed_action object")
            world = context_projection.get("world")
            if not isinstance(world, dict):
                raise ValueError("brain context lacks world binding")
            return BrainDecisionV2(
                kind,
                proposed_action=ProposedActionV1(
                    id="proposal:" + uuid4().hex,
                    goal_id=goal.id,
                    desired_effect_id=_string(proposal, "desired_effect_id"),
                    capability_family=_string(proposal, "capability_family"),
                    target_id=_string(proposal, "target_id"),
                    entity_id=_string(proposal, "entity_id"),
                    semantic_parameters=_object(proposal, "semantic_parameters"),
                    based_on_snapshot_id=_string(world, "snapshot_id"),
                    based_on_world_revision=int(world["revision"]),
                    proposed_by=self.id,
                    rationale=rationale,
                    evidence_ids=tuple(
                        str(item) for item in proposal.get("evidence_ids", ())
                    ),
                ),
                rationale=rationale,
            )
        if kind is DecisionKindV2.CONSULT_SPECIALIST:
            return BrainDecisionV2(
                kind,
                specialist_id=_string(raw, "specialist_id"),
                query=_object(raw, "query"),
                rationale=rationale,
            )
        if kind is DecisionKindV2.QUERY_WORLD:
            return BrainDecisionV2(kind, query=_object(raw, "query"), rationale=rationale)
        return BrainDecisionV2(kind, rationale=rationale)


def _string(value: dict[str, Any], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{key} must be a non-empty string")
    return raw


def _object(value: dict[str, Any], key: str) -> dict[str, Any]:
    raw = value.get(key, {})
    if not isinstance(raw, dict):
        raise ValueError(f"{key} must be an object")
    return dict(raw)

