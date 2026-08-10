from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any

from .interfaces import StructuredDecisionModel
from .models import (
    BrainContext,
    BrainDecision,
    BrainManifest,
    DecisionKind,
    SpecialistAdvice,
    ToolCall,
)


class RuleExecutiveBrain:
    """A strong deterministic fixture for the general-brain slot.

    It contains no target-specific branches. It selects specialists by their
    declared capability affinity, then turns their persisted advice into a world
    tool request. A model-backed executive can replace it without changing Heart.
    """

    manifest = BrainManifest(
        name="rule-executive",
        description="General executive that selects specialists and world tools",
        id="engine.core.rule-executive/v1",
    )

    def decide(self, context: BrainContext) -> BrainDecision:
        raw_results = context.working_memory.get("specialist_results", [])
        fresh_results = [
            item
            for item in raw_results
            if isinstance(item, dict)
            and item.get("snapshot_revision") == context.snapshot.revision
        ]
        for raw_advice in fresh_results:
            advice = SpecialistAdvice.from_dict(raw_advice["advice"])
            specialist_name = str(raw_advice["specialist"])
            if advice.suggested_action is not None:
                return BrainDecision(
                    kind=DecisionKind.USE_TOOL,
                    name=advice.suggested_action.capability,
                    arguments=advice.suggested_action.arguments,
                    rationale=f"Use persisted advice from {specialist_name}: {advice.summary}",
                    based_on=(str(raw_advice["brain_request_id"]),),
                )
            if advice.complete:
                return BrainDecision(
                    kind=DecisionKind.COMPLETE,
                    rationale=f"{specialist_name} reports no remaining plan step",
                    based_on=(str(raw_advice["brain_request_id"]),),
                )

        available = {item.id for item in context.capabilities}
        candidates: list[tuple[int, float, float, str]] = []
        for specialist in context.specialists:
            overlap = len(available.intersection(specialist.supported_capabilities))
            performance = context.specialist_performance.get(
                specialist.qualified_id, {}
            )
            effect_score = float(performance.get("effect_score", 0.5))
            latency = float(performance.get("mean_latency_ms", 0.0))
            candidates.append(
                (overlap, effect_score, latency, specialist.qualified_id)
            )
        candidates.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
        if not candidates or candidates[0][0] == 0:
            return BrainDecision(
                kind=DecisionKind.ABANDON,
                rationale="No specialist matches the target capabilities",
            )
        return BrainDecision(
            kind=DecisionKind.CONSULT_BRAIN,
            name=candidates[0][3],
            arguments={"goal_id": context.goal.id},
            rationale=(
                "Consult the best capability match using observed utility and latency "
                "as transparent tie-breakers"
            ),
        )


class ModelExecutiveBrain:
    """Adapter for an actual structured-output LLM or another general model."""

    def __init__(self, model: StructuredDecisionModel, name: str = "model-executive"):
        self._model = model
        self.manifest = BrainManifest(
            name=name,
            description="Provider-neutral model-backed general executive brain",
            id=f"engine.model.{name}/v1",
        )

    @property
    def last_usage(self) -> dict[str, object]:
        value = getattr(self._model, "last_usage", {})
        return dict(value) if isinstance(value, dict) else {}

    def decide(self, context: BrainContext) -> BrainDecision:
        return BrainDecision.from_dict(self._model.decide(context.to_payload()))


class FileStructureBrain:
    manifest = BrainManifest(
        name="file-structure-brain",
        description="Plans declarative file-layout goals",
        supported_capabilities=(
            "engine.fs.make-directory/v1",
            "engine.fs.move-file/v1",
        ),
        plugin_id="engine.filesystem",
        id="engine.filesystem.structure-brain/v1",
    )

    def advise(self, context: BrainContext) -> SpecialistAdvice:
        entries = dict(context.snapshot.state.get("entries", {}))
        moves = list(context.goal.success_spec.get("moves", []))
        for move in moves:
            source = str(move["source"])
            destination = str(move["destination"])
            if destination in entries and source not in entries:
                continue
            parent = destination.rsplit("/", 1)[0] if "/" in destination else ""
            if parent and parent not in entries:
                return SpecialistAdvice(
                    summary=f"Create destination directory {parent}",
                    suggested_action=ToolCall(
                        "engine.fs.make-directory/v1", {"path": parent}
                    ),
                )
            if source in entries:
                return SpecialistAdvice(
                    summary=f"Move {source} to its desired location",
                    suggested_action=ToolCall(
                        "engine.fs.move-file/v1",
                        {"source": source, "destination": destination},
                    ),
                )
            return SpecialistAdvice(
                summary=f"Expected source {source} is missing",
                metadata={"missing_source": source},
            )
        return SpecialistAdvice(summary="Desired filesystem layout is present", complete=True)


class GridNavigationBrain:
    def __init__(
        self,
        name: str = "grid-navigation-brain",
        neighbor_order: tuple[str, ...] = ("east", "north", "west", "south"),
    ):
        self.manifest = BrainManifest(
            name=name,
            description="Plans navigation and item pickup in discrete spatial worlds",
            supported_capabilities=(
                "engine.spatial.step/v1",
                "engine.spatial.pick-up/v1",
            ),
            plugin_id="engine.spatial-grid",
            id=f"engine.spatial-grid.{name}/v1",
        )
        self._neighbor_order = neighbor_order

    def advise(self, context: BrainContext) -> SpecialistAdvice:
        state = context.snapshot.state
        position = tuple(state["position"])
        inventory = set(state.get("inventory", []))
        required = list(context.goal.success_spec.get("requires", []))
        items = {name: tuple(location) for name, location in state.get("items", {}).items()}

        missing = next((item for item in required if item not in inventory), None)
        if missing is not None:
            if missing not in items:
                return SpecialistAdvice(
                    summary=f"Required item {missing} is not observable",
                    metadata={"missing_item": missing},
                )
            target = items[missing]
            if position == target:
                return SpecialistAdvice(
                    summary=f"Pick up required item {missing}",
                    suggested_action=ToolCall(
                        "engine.spatial.pick-up/v1", {"item": missing}
                    ),
                )
        else:
            target = tuple(context.goal.success_spec["target"])
            if position == target:
                return SpecialistAdvice(summary="Target state is reached", complete=True)

        direction = self._next_direction(state, position, target)
        if direction is None:
            return SpecialistAdvice(
                summary=f"No known route from {position} to {target}",
                metadata={"route_unavailable": True},
            )
        return SpecialistAdvice(
            summary=f"Move {direction} toward {target}",
            suggested_action=ToolCall(
                "engine.spatial.step/v1", {"direction": direction}
            ),
            metadata={"planned_target": list(target)},
        )

    def _next_direction(
        self,
        state: dict[str, Any],
        start: tuple[int, int],
        target: tuple[int, int],
    ) -> str | None:
        width, height = state["bounds"]
        blocked = {tuple(item) for item in state.get("known_blocked", [])}
        deltas = {
            "east": (1, 0),
            "north": (0, 1),
            "west": (-1, 0),
            "south": (0, -1),
        }
        queue: deque[tuple[tuple[int, int], list[str]]] = deque([(start, [])])
        seen = {start}
        while queue:
            current, path = queue.popleft()
            if current == target:
                return path[0] if path else None
            for direction in self._neighbor_order:
                dx, dy = deltas[direction]
                candidate = (current[0] + dx, current[1] + dy)
                in_bounds = 0 <= candidate[0] < width and 0 <= candidate[1] < height
                if in_bounds and candidate not in blocked and candidate not in seen:
                    seen.add(candidate)
                    queue.append((candidate, [*path, direction]))
        return None


class AxisNavigationBrain:
    """Independent specialist implementation used to prove brain replaceability."""

    manifest = BrainManifest(
        name="axis-navigation-brain",
        description="Greedy axis planner with observed-obstacle avoidance",
        supported_capabilities=(
            "engine.spatial.step/v1",
            "engine.spatial.pick-up/v1",
        ),
        plugin_id="engine.spatial-grid",
        id="engine.spatial-grid.axis-navigation-brain/v1",
    )

    def advise(self, context: BrainContext) -> SpecialistAdvice:
        state = context.snapshot.state
        position = tuple(state["position"])
        inventory = set(state.get("inventory", []))
        required = list(context.goal.success_spec.get("requires", []))
        items = {name: tuple(location) for name, location in state.get("items", {}).items()}
        missing = next((item for item in required if item not in inventory), None)
        if missing is not None:
            target = items[missing]
            if position == target:
                return SpecialistAdvice(
                    summary=f"Pick up {missing}",
                    suggested_action=ToolCall(
                        "engine.spatial.pick-up/v1", {"item": missing}
                    ),
                )
        else:
            target = tuple(context.goal.success_spec["target"])
            if position == target:
                return SpecialistAdvice(summary="Target state is reached", complete=True)

        known = {tuple(item) for item in state.get("known_blocked", [])}
        width, height = state["bounds"]
        candidates: list[tuple[str, tuple[int, int]]] = []
        if target[0] > position[0]:
            candidates.append(("east", (position[0] + 1, position[1])))
        elif target[0] < position[0]:
            candidates.append(("west", (position[0] - 1, position[1])))
        if target[1] > position[1]:
            candidates.append(("north", (position[0], position[1] + 1)))
        elif target[1] < position[1]:
            candidates.append(("south", (position[0], position[1] - 1)))
        candidates.extend(
            [
                ("north", (position[0], position[1] + 1)),
                ("east", (position[0] + 1, position[1])),
                ("south", (position[0], position[1] - 1)),
                ("west", (position[0] - 1, position[1])),
            ]
        )
        for direction, candidate in candidates:
            if (
                0 <= candidate[0] < width
                and 0 <= candidate[1] < height
                and candidate not in known
            ):
                return SpecialistAdvice(
                    summary=f"Greedy move {direction} toward {target}",
                    suggested_action=ToolCall(
                        "engine.spatial.step/v1", {"direction": direction}
                    ),
                )
        return SpecialistAdvice(summary="No available greedy step")
