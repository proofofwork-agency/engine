from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .brains import FileStructureBrain, GridNavigationBrain, ModelExecutiveBrain
from .catalog import Catalog, EnginePlugin
from .heart import Heart
from .models import Goal, PluginManifest
from .providers import OpenAICompatibleDecisionModel
from .store import EngineStore
from .worlds import FilesystemTarget, GridTarget


def _catalog(filesystem: FilesystemTarget, grid: GridTarget) -> Catalog:
    catalog = Catalog()
    catalog.register(
        EnginePlugin(
            PluginManifest("engine.filesystem", "Filesystem world and cognition"),
            targets=(filesystem,),
            specialists=(FileStructureBrain(),),
        )
    )
    catalog.register(
        EnginePlugin(
            PluginManifest("engine.spatial-grid", "Spatial simulation and cognition"),
            targets=(grid,),
            specialists=(GridNavigationBrain(),),
        )
    )
    return catalog


def _executive() -> ModelExecutiveBrain:
    return ModelExecutiveBrain(
        OpenAICompatibleDecisionModel(), name="qwen3-4b-local-executive"
    )


def _metrics(store: EngineStore, goal_id: str) -> dict[str, object]:
    events = store.all_events(goal_id)
    model_results = [
        event
        for event in events
        if event.kind == "brain_result"
        and event.source == "engine.model.qwen3-4b-local-executive/v1"
    ]
    return {
        "brain_calls": len(model_results),
        "prompt_tokens": sum(
            int(event.payload.get("usage", {}).get("usage", {}).get("prompt_tokens", 0))
            for event in model_results
        ),
        "completion_tokens": sum(
            int(
                event.payload.get("usage", {})
                .get("usage", {})
                .get("completion_tokens", 0)
            )
            for event in model_results
        ),
        "tool_calls": sum(event.kind == "tool_result" for event in events),
        "specialist_calls": sum(event.kind == "specialist_result" for event in events),
        "partial_invocations": sum(
            event.kind == "invocation" and event.payload.get("state") == "partial"
            for event in events
        ),
    }


def run_live_demo(base: Path) -> dict[str, object]:
    store_path = base / "engine.sqlite3"
    filesystem = FilesystemTarget("workspace", base / "workspace")
    filesystem.seed({"inbox/notes.txt": "notes", "inbox/design.md": "design"})
    grid = GridTarget.default("rover-sim", base / "grid-state.json")
    store = EngineStore(store_path)
    heart = Heart(
        store,
        _executive(),
        _catalog(filesystem, grid),
        experience_window=12,
        require_specialist_first=True,
    )

    fs_goal = Goal(
        id="llm-organize-workspace",
        target_id="workspace",
        instruction="Organize the inbox into typed archive directories",
        success_spec={
            "moves": [
                {"source": "inbox/notes.txt", "destination": "archive/text/notes.txt"},
                {
                    "source": "inbox/design.md",
                    "destination": "archive/markdown/design.md",
                },
            ]
        },
        max_cycles=30,
    )
    heart.register_goal(fs_goal)
    fs_result = heart.run(fs_goal.id)
    fs_metrics = _metrics(store, fs_goal.id)

    grid_goal = Goal(
        id="llm-retrieve-and-arrive",
        target_id="rover-sim",
        instruction="Retrieve the key and arrive at the target position",
        success_spec={"requires": ["key"], "target": [3, 2]},
        max_cycles=40,
    )
    heart.register_goal(grid_goal)
    partial = heart.run(grid_goal.id, step_limit=2)
    events_before_restart = len(store.all_events(grid_goal.id))
    store.close()

    restarted_store = EngineStore(store_path)
    restarted_filesystem = FilesystemTarget("workspace", base / "workspace")
    restarted_grid = GridTarget("rover-sim", base / "grid-state.json")
    restarted_heart = Heart(
        restarted_store,
        _executive(),
        _catalog(restarted_filesystem, restarted_grid),
        experience_window=12,
        require_specialist_first=True,
    )
    grid_result = restarted_heart.run(grid_goal.id)
    grid_metrics = _metrics(restarted_store, grid_goal.id)
    summary = {
        "model": "ggml-org/Qwen3-4B-GGUF:Q4_K_M",
        "condition": "Engine Heart + general LLM + deterministic specialists",
        "filesystem": {
            "status": fs_result.goal.status,
            "oracle": filesystem.goal_satisfied(fs_goal, filesystem.observe()),
            "metrics": fs_metrics,
        },
        "grid": {
            "status_before_restart": partial.goal.status,
            "events_before_restart": events_before_restart,
            "status": grid_result.goal.status,
            "oracle": restarted_grid.goal_satisfied(grid_goal, restarted_grid.observe()),
            "metrics": grid_metrics,
        },
    }
    restarted_store.close()
    return summary


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="engine-live-llm-") as directory:
        print(json.dumps(run_live_demo(Path(directory)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
