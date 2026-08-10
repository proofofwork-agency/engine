from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from .brains import GridNavigationBrain, RuleExecutiveBrain
from .catalog import Catalog, EnginePlugin
from .heart import Heart
from .models import Goal, GoalMode, PluginManifest
from .runtime import LiveEngine
from .store import EngineStore
from .worlds import GridTarget


def _catalog(target: GridTarget) -> Catalog:
    catalog = Catalog()
    catalog.register(
        EnginePlugin(
            PluginManifest("engine.spatial-grid", "Spatial grid plugin"),
            targets=(target,),
            specialists=(GridNavigationBrain(),),
        )
    )
    return catalog


def run_live_heart_demo(base: Path) -> dict[str, object]:
    """Prove achieve -> monitor -> external drift -> autonomous repair."""
    store = EngineStore(base / "engine.sqlite3")
    target = GridTarget.default("live-grid", base / "grid-state.json")
    heart = Heart(store, RuleExecutiveBrain(), _catalog(target))
    goal = Goal(
        id="maintain-ready-rover",
        target_id="live-grid",
        instruction="Keep the rover at the ready point with the key",
        success_spec={"requires": ["key"], "target": [3, 2]},
        mode=GoalMode.MAINTAIN,
        max_cycles=40,
    )
    heart.register_goal(goal)
    runtime = LiveEngine(heart, poll_interval=0.01)
    drift_injected = threading.Event()
    timed_out = threading.Event()

    def world_changes_outside_engine() -> None:
        deadline = time.monotonic() + 5.0
        phase = "await-initial-state"
        while time.monotonic() < deadline:
            state = json.loads(target.state_path.read_text(encoding="utf-8"))
            satisfied = (
                state["position"] == [3, 2]
                and "key" in state.get("inventory", [])
            )
            if phase == "await-initial-state" and satisfied:
                time.sleep(0.03)
                state = json.loads(target.state_path.read_text(encoding="utf-8"))
                state["position"] = [0, 2]
                state["revision"] += 1
                target.state_path.write_text(
                    json.dumps(state, sort_keys=True, indent=2), encoding="utf-8"
                )
                drift_injected.set()
                runtime.wake({"target_id": target.manifest.id})
                phase = "await-repair"
            elif phase == "await-repair" and satisfied:
                runtime.stop()
                return
            time.sleep(0.01)
        timed_out.set()
        runtime.stop()

    world_thread = threading.Thread(
        target=world_changes_outside_engine,
        name="external-grid-world",
        daemon=True,
    )
    world_thread.start()
    runtime.run_forever()
    world_thread.join(timeout=1.0)

    events = store.all_events(goal.id)
    final_goal = store.get_goal(goal.id)
    final_snapshot = target.observe()
    summary: dict[str, object] = {
        "goal_mode": final_goal.mode.value,
        "status": final_goal.status,
        "oracle": target.goal_satisfied(final_goal, final_snapshot),
        "drift_injected": drift_injected.is_set(),
        "timed_out": timed_out.is_set(),
        "brain_requests": sum(event.kind == "brain_request" for event in events),
        "world_invocations": sum(event.kind == "tool_result" for event in events),
        "goal_drift_events": sum(event.kind == "goal_drifted" for event in events),
        "monitoring_transitions": sum(
            event.kind == "goal_monitoring" for event in events
        ),
        "goal_completed_events": sum(
            event.kind == "goal_completed" for event in events
        ),
        "runtime_events": [event["kind"] for event in store.system_events()],
        "final_state": final_snapshot.state,
    }
    store.close()
    return summary


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="engine-live-heart-") as directory:
        print(
            json.dumps(
                run_live_heart_demo(Path(directory)),
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
