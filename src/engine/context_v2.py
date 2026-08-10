from __future__ import annotations

from typing import Any

from engine_sdk import GoalSpecV2, WorldSnapshotV2, artifact_sha256

from .conditions_v2 import ConditionResult, select_entities


class BoundedContextProjector:
    """Projects a bounded, local subset; the full world never becomes model state."""

    def __init__(self, *, max_entities: int = 64, max_observations: int = 128):
        if max_entities < 1 or max_observations < 1:
            raise ValueError("context bounds must be positive")
        self.max_entities = max_entities
        self.max_observations = max_observations

    def project(
        self,
        goal: GoalSpecV2,
        snapshot: WorldSnapshotV2,
        effect_results: dict[str, ConditionResult],
        *,
        capabilities: tuple[dict[str, Any], ...],
        specialists: tuple[dict[str, Any], ...],
    ) -> dict[str, object]:
        selected_ids: set[str] = set()
        for effect in goal.desired_effects:
            selected_ids.update(
                item.id for item in select_entities(snapshot, effect.entity_selector)
            )
        scope_targets = {str(item) for item in goal.entity_scope.get("target_ids", ())}
        for entity in snapshot.entities:
            if "*" in scope_targets or (scope_targets and entity.target_id in scope_targets):
                selected_ids.add(entity.id)
        # Include one-hop relation neighbours so the brain can reason about
        # location/containment without receiving the unrelated world.
        for relation in snapshot.relations:
            if relation.source_entity_id in selected_ids:
                selected_ids.add(relation.target_entity_id)
            if relation.target_entity_id in selected_ids:
                selected_ids.add(relation.source_entity_id)
        entities = tuple(
            item for item in snapshot.entities if item.id in selected_ids
        )[: self.max_entities]
        bounded_ids = {item.id for item in entities}
        observations = tuple(
            item for item in snapshot.observations if item.entity_id in bounded_ids
        )[: self.max_observations]
        relations = tuple(
            item
            for item in snapshot.relations
            if item.source_entity_id in bounded_ids and item.target_entity_id in bounded_ids
        )
        projection: dict[str, object] = {
            "contract": "engine.brain-context/v2",
            "goal": goal.to_dict(),
            "world": {
                "snapshot_id": snapshot.id,
                "revision": snapshot.revision,
                "observed_at": snapshot.observed_at,
                "target_revisions": snapshot.target_revisions,
                "entities": [item.to_dict() for item in entities],
                "relations": [item.to_dict() for item in relations],
                "observations": [item.to_dict() for item in observations],
                "coverage": {
                    "selected_entities": len(entities),
                    "selected_observations": len(observations),
                    "truncated_entities": len(selected_ids) > len(entities),
                },
            },
            "effect_results": {
                key: {
                    "value": item.value,
                    "grade": item.grade.value,
                    "evidence_ids": list(item.evidence_ids),
                    "reason": item.reason,
                }
                for key, item in effect_results.items()
            },
            "capabilities": list(capabilities),
            "specialists": list(specialists),
        }
        projection["projection_sha256"] = artifact_sha256(projection)
        return projection
