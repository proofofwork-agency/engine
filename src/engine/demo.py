from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .brains import FileStructureBrain, GridNavigationBrain, RuleExecutiveBrain
from .catalog import Catalog, EnginePlugin
from .heart import Heart
from .models import Goal, PluginManifest
from .store import EngineStore
from .worlds import FilesystemTarget, GridTarget


def run_demo(base: Path) -> dict[str, object]:
    store_path = base / "engine.sqlite3"
    store = EngineStore(store_path)
    filesystem = FilesystemTarget("workspace", base / "workspace")
    filesystem.seed({"inbox/notes.txt": "notes", "inbox/design.md": "design"})
    fs_goal = Goal(
        id="organize-workspace",
        target_id="workspace",
        instruction="Organize the inbox into typed archive directories",
        success_spec={
            "moves": [
                {"source": "inbox/notes.txt", "destination": "archive/text/notes.txt"},
                {"source": "inbox/design.md", "destination": "archive/markdown/design.md"},
            ]
        },
    )
    grid = GridTarget.default("rover-sim", base / "grid-state.json")
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
    heart = Heart(store, RuleExecutiveBrain(), catalog)

    heart.register_goal(fs_goal)
    fs_result = heart.run(fs_goal.id)

    grid_goal = Goal(
        id="retrieve-key-and-arrive",
        target_id="rover-sim",
        instruction="Retrieve the key and arrive at the target position",
        success_spec={"requires": ["key"], "target": [3, 2]},
    )
    heart.register_goal(grid_goal)

    # Stop after the first failed movement so a fresh Heart instance must resume.
    partial = heart.run(grid_goal.id, step_limit=2)
    events_before_restart = len(store.all_events(grid_goal.id))
    store.close()

    restarted_store = EngineStore(store_path)
    grid_after_restart = GridTarget("rover-sim", base / "grid-state.json")
    restarted_catalog = Catalog()
    restarted_catalog.register(
        EnginePlugin(
            PluginManifest("engine.filesystem", "Filesystem world and cognition"),
            targets=(FilesystemTarget("workspace", base / "workspace"),),
            specialists=(FileStructureBrain(),),
        )
    )
    restarted_catalog.register(
        EnginePlugin(
            PluginManifest("engine.spatial-grid", "Spatial simulation and cognition"),
            targets=(grid_after_restart,),
            specialists=(GridNavigationBrain(),),
        )
    )
    restarted_heart = Heart(restarted_store, RuleExecutiveBrain(), restarted_catalog)
    grid_result = restarted_heart.run(grid_goal.id)
    grid_events = restarted_store.all_events(grid_goal.id)
    summary = {
        "filesystem": {
            "status": fs_result.goal.status,
            "cycles": fs_result.goal.cycle,
            "final_state": fs_result.final_snapshot.state if fs_result.final_snapshot else None,
        },
        "grid": {
            "status_before_restart": partial.goal.status,
            "events_before_restart": events_before_restart,
            "status": grid_result.goal.status,
            "cycles": grid_result.goal.cycle,
            "final_state": grid_result.final_snapshot.state if grid_result.final_snapshot else None,
            "failures": [
                event.payload
                for event in grid_events
                if event.kind == "tool_result"
                and not event.payload["result"]["succeeded"]
            ],
        },
    }
    restarted_store.close()
    return summary


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="engine-0.1-") as directory:
        summary = run_demo(Path(directory))
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
