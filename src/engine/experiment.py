from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .brains import FileStructureBrain, GridNavigationBrain, ModelExecutiveBrain
from .catalog import Catalog, EnginePlugin
from .heart import Heart
from .models import BrainDecision, DecisionKind, Goal, PluginManifest, ToolCall
from .providers import LlamaCppDecisionModel
from .store import EngineStore
from .worlds import FilesystemTarget, GridTarget


MODEL_ARTIFACT = "ggml-org/Qwen3-4B-GGUF:Q4_K_M"
MODEL_SHA256 = "ab27b9bfa375a178d6cba48f3ad892b94b7739659dcc7aae8058ce0ffed6b328"
RESTART_AFTER_TOOL_INVOCATIONS = 1


def _sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _source_sha256() -> str:
    source_root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(source_root.rglob("*.py")):
        digest.update(path.relative_to(source_root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _target_and_goal(base: Path, world: str):
    if world == "filesystem":
        target = FilesystemTarget("workspace", base / "workspace")
        target.seed({"inbox/notes.txt": "notes", "inbox/design.md": "design"})
        goal = Goal(
            id="organize-workspace",
            target_id="workspace",
            instruction="Organize the inbox into typed archive directories",
            success_spec={
                "moves": [
                    {
                        "source": "inbox/notes.txt",
                        "destination": "archive/text/notes.txt",
                    },
                    {
                        "source": "inbox/design.md",
                        "destination": "archive/markdown/design.md",
                    },
                ]
            },
            max_cycles=30,
        )
        return target, goal
    if world == "grid":
        target = GridTarget.default("rover-sim", base / "grid-state.json")
        goal = Goal(
            id="retrieve-and-arrive",
            target_id="rover-sim",
            instruction="Retrieve the key and arrive at the target position",
            success_spec={"requires": ["key"], "target": [3, 2]},
            max_cycles=40,
        )
        return target, goal
    raise ValueError(f"unknown world: {world}")


def _catalog(target, with_specialist: bool) -> Catalog:
    if isinstance(target, FilesystemTarget):
        plugin_id = "engine.filesystem"
        specialist = FileStructureBrain()
    else:
        plugin_id = "engine.spatial-grid"
        specialist = GridNavigationBrain()
    catalog = Catalog()
    catalog.register(
        EnginePlugin(
            PluginManifest(plugin_id, f"Pilot {plugin_id}"),
            targets=(target,),
            specialists=(specialist,) if with_specialist else (),
        )
    )
    return catalog


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _terminal_tool_count(store: EngineStore, goal_id: str) -> int:
    return sum(
        event.kind == "invocation" and event.payload.get("state") != "requested"
        for event in store.all_events(goal_id)
    )


def _canonical_snapshot(snapshot) -> dict[str, object]:
    return {
        "target_id": snapshot.target_id,
        "revision": snapshot.revision,
        "state": snapshot.state,
    }


def _drive_heart(
    heart: Heart,
    store: EngineStore,
    goal_id: str,
    stop_after_tool_count: int | None = None,
) -> None:
    """Drive one cognitive cycle at a time and account for provider failures.

    Heart durably records a failed brain result before raising. The exploratory
    harness consumes one cognitive budget unit so every condition can continue
    under the same provider-error policy instead of erasing the whole pilot.
    """
    while store.get_goal(goal_id).status == "active":
        if (
            stop_after_tool_count is not None
            and _terminal_tool_count(store, goal_id) >= stop_after_tool_count
        ):
            return
        before_cycle = store.get_goal(goal_id).cycle
        try:
            heart.run(goal_id, step_limit=1)
        except Exception as error:
            current = store.get_goal(goal_id)
            if current.status != "active":
                return
            store.append_event(
                goal_id,
                current.cycle,
                "experiment_provider_error_consumed",
                "engine.experiment",
                {"error": f"{type(error).__name__}: {error}"},
            )
            if current.cycle == before_cycle:
                store.advance_cycle(goal_id)


def _engine_metrics(
    store: EngineStore,
    goal: Goal,
    target,
    wall_ms: float,
    restart_boundary: dict[str, object] | None,
    initial_snapshot_hash: str,
) -> dict[str, Any]:
    events = store.all_events(goal.id)
    executive_requests = {
        event.payload["id"]
        for event in events
        if event.kind == "brain_request"
        and event.payload.get("purpose") == "select next cognitive operator"
    }
    executive_results = [
        event
        for event in events
        if event.kind == "brain_result"
        and event.payload.get("request_id") in executive_requests
    ]
    succeeded_results = [
        event for event in executive_results if event.payload.get("status") == "succeeded"
    ]
    usage_results = [
        event for event in executive_results if event.payload.get("usage")
    ]
    input_bytes = [
        float(event.payload.get("usage", {}).get("input_bytes", 0))
        for event in usage_results
    ]
    caller_latencies = [
        float(event.payload.get("latency_ms", 0)) for event in executive_results
    ]
    provider_latencies = [
        float(event.payload.get("usage", {}).get("timings", {}).get("predicted_ms", 0))
        for event in usage_results
    ]
    decisions = [
        event.payload["decision"]["kind"]
        for event in events
        if event.kind == "executive_decision"
    ]
    invocation_ids = {
        event.payload["id"]
        for event in events
        if event.kind == "invocation" and event.payload["state"] == "requested"
    }
    terminal_events = [
        event
        for event in events
        if event.kind == "invocation" and event.payload["state"] != "requested"
    ]
    terminal_states = [event.payload["state"] for event in terminal_events]
    tool_results = [event for event in events if event.kind == "tool_result"]
    specialist_request_ids = {
        event.payload["id"]
        for event in events
        if event.kind == "brain_request"
        and event.payload.get("purpose") == "resolve bounded cognitive impasse"
    }
    specialist_results = [
        event
        for event in events
        if event.kind == "brain_result"
        and event.payload.get("request_id") in specialist_request_ids
    ]
    specialist_latencies = [
        float(event.payload.get("latency_ms", 0)) for event in specialist_results
    ]
    capability_validation_errors = sum(
        str(event.payload.get("result", {}).get("error", "")).startswith(
            ("invalid input", "unknown capability", "call target")
        )
        for event in tool_results
    )
    current_goal = store.get_goal(goal.id)
    final_snapshot = target.observe()
    returned_models = {
        str(event.payload.get("usage", {}).get("model"))
        for event in usage_results
        if event.payload.get("usage", {}).get("model")
    }
    return {
        "status": current_goal.status,
        "oracle": target.goal_satisfied(goal, final_snapshot) is True,
        "final_cycle_index": current_goal.cycle,
        "executive_attempts": len(executive_requests),
        "executive_succeeded": len(succeeded_results),
        "executive_failed": len(executive_results) - len(succeeded_results),
        "executive_decisions": len(decisions),
        "usage_coverage": {
            "records": len(usage_results),
            "attempts": len(executive_requests),
        },
        "decisions_by_kind": {
            kind: decisions.count(kind) for kind in sorted(set(decisions))
        },
        "specialist_calls": sum(event.kind == "specialist_result" for event in events),
        "specialist_identities": sorted(
            {event.source for event in events if event.kind == "specialist_result"}
        ),
        "specialist_caller_wall_latency_ms": {
            "total": round(sum(specialist_latencies), 3),
            "p50": round(_percentile(specialist_latencies, 0.50), 3),
            "p95": round(_percentile(specialist_latencies, 0.95), 3),
        },
        "tool_invocation_attempts": len(invocation_ids),
        "tool_dispatches": len(tool_results) - capability_validation_errors,
        "semantic_decision_rejections": sum(
            event.kind == "decision_rejected" for event in events
        ),
        "completion_rejections": sum(
            event.kind == "completion_rejected" for event in events
        ),
        "capability_validation_errors": capability_validation_errors,
        "execution_exceptions": sum(
            "adapter dispatch/result contract failed"
            in str(event.payload.get("result", {}).get("error", ""))
            for event in tool_results
        ),
        "tool_results_failed": terminal_states.count("failed"),
        "tool_results_partial": terminal_states.count("partial"),
        "tool_results_unknown": terminal_states.count("unknown"),
        "invocation_states": {
            state: terminal_states.count(state) for state in sorted(set(terminal_states))
        },
        "prompt_tokens_known": sum(
            int(event.payload.get("usage", {}).get("usage", {}).get("prompt_tokens", 0))
            for event in usage_results
        ),
        "completion_tokens_known": sum(
            int(
                event.payload.get("usage", {})
                .get("usage", {})
                .get("completion_tokens", 0)
            )
            for event in usage_results
        ),
        "provider_input_bytes": {
            "max": int(max(input_bytes, default=0)),
            "p50": int(_percentile(input_bytes, 0.50)),
            "p95": int(_percentile(input_bytes, 0.95)),
        },
        "model_caller_wall_latency_ms": {
            "total": round(sum(caller_latencies), 3),
            "p50": round(_percentile(caller_latencies, 0.50), 3),
            "p95": round(_percentile(caller_latencies, 0.95), 3),
        },
        "provider_reported_prediction_ms": {
            "total": round(sum(provider_latencies), 3),
            "p50": round(_percentile(provider_latencies, 0.50), 3),
            "p95": round(_percentile(provider_latencies, 0.95), 3),
        },
        "condition_wall_ms": round(wall_ms, 3),
        "restart_boundary": restart_boundary,
        "initial_snapshot_sha256": initial_snapshot_hash,
        "final_snapshot_sha256": _sha256(
            {
                "target_id": final_snapshot.target_id,
                "revision": final_snapshot.revision,
                "state": final_snapshot.state,
            }
        ),
        "returned_models": sorted(returned_models),
    }


def _run_engine_condition(
    base: Path, world: str, multi: bool
) -> dict[str, Any]:
    target, goal = _target_and_goal(base, world)
    initial = target.observe()
    initial_hash = _sha256(_canonical_snapshot(initial))
    store_path = base / "engine.sqlite3"
    store = EngineStore(store_path)

    def make_heart(current_store: EngineStore, current_target) -> Heart:
        model = LlamaCppDecisionModel(model=MODEL_ARTIFACT)
        executive = ModelExecutiveBrain(
            model, name="qwen3-4b-multi" if multi else "qwen3-4b-durable-single"
        )
        return Heart(
            current_store,
            executive,
            _catalog(current_target, with_specialist=multi),
            experience_window=12,
            require_specialist_first=multi,
        )

    heart = make_heart(store, target)
    heart.register_goal(goal)
    restart_boundary = None
    started = time.perf_counter()
    if world == "grid":
        _drive_heart(
            heart,
            store,
            goal.id,
            stop_after_tool_count=RESTART_AFTER_TOOL_INVOCATIONS,
        )
        boundary_count = _terminal_tool_count(store, goal.id)
        before_restart = store.get_goal(goal.id)
        if boundary_count < RESTART_AFTER_TOOL_INVOCATIONS:
            restart_boundary = {
                "reached": False,
                "after_terminal_tool_invocations": boundary_count,
                "reason": f"goal status became {before_restart.status}",
            }
        else:
            before_snapshot = target.observe()
            terminal = next(
                event
                for event in reversed(store.all_events(goal.id))
                if event.kind == "invocation"
                and event.payload["state"] != "requested"
            )
            restart_boundary = {
                "reached": True,
                "after_terminal_tool_invocations": boundary_count,
                "at_cycle_index": before_restart.cycle,
                "terminal_invocation_id": terminal.payload["id"],
                "terminal_invocation_state": terminal.payload["state"],
                "pre_restart_snapshot_sha256": _sha256(
                    _canonical_snapshot(before_snapshot)
                ),
                "pre_restart_goal": {
                    "status": before_restart.status,
                    "cycle": before_restart.cycle,
                },
                "pre_restart_last_event_id": store.all_events(goal.id)[-1].id,
            }
            store.close()
            store = EngineStore(store_path)
            target = GridTarget("rover-sim", base / "grid-state.json")
            reconstructed_snapshot = target.observe()
            reconstructed_goal = store.get_goal(goal.id)
            restart_boundary.update(
                {
                    "post_restart_snapshot_sha256": _sha256(
                        _canonical_snapshot(reconstructed_snapshot)
                    ),
                    "post_restart_goal": {
                        "status": reconstructed_goal.status,
                        "cycle": reconstructed_goal.cycle,
                    },
                    "post_restart_last_event_id": store.all_events(goal.id)[-1].id,
                    "continuity_equal": (
                        _sha256(_canonical_snapshot(before_snapshot))
                        == _sha256(_canonical_snapshot(reconstructed_snapshot))
                        and before_restart.status == reconstructed_goal.status
                        and before_restart.cycle == reconstructed_goal.cycle
                    ),
                }
            )
            heart = make_heart(store, target)
    _drive_heart(heart, store, goal.id)
    wall_ms = (time.perf_counter() - started) * 1000
    metrics = _engine_metrics(
        store, goal, target, wall_ms, restart_boundary, initial_hash
    )
    _write_json(
        base / "events.json",
        [asdict(event) for event in store.all_events(goal.id)],
    )
    _write_json(base / "system-events.json", store.system_events())
    store.close()
    return metrics


def _run_monolith(base: Path, world: str) -> dict[str, Any]:
    target, goal = _target_and_goal(base, world)
    initial = target.observe()
    initial_hash = _sha256(_canonical_snapshot(initial))
    catalog = _catalog(target, with_specialist=False)
    model = LlamaCppDecisionModel(
        model=MODEL_ARTIFACT,
        keep_session_history=True,
        history_turn_limit=2,
    )
    outcomes: list[dict[str, object]] = []
    calls: list[dict[str, object]] = []
    failed_usage_records: list[dict[str, object]] = []
    caller_attempt_latencies: list[float] = []
    trace: list[dict[str, object]] = []
    decision_kinds: list[str] = []
    terminal_states: list[str] = []
    last_terminal: dict[str, str] | None = None
    provider_errors = 0
    capability_validation_errors = 0
    execution_exceptions = 0
    completion_rejections = 0
    tool_attempts = 0
    tool_dispatches = 0
    restart_boundary = None
    started = time.perf_counter()
    status = "active"
    cycle = 0
    while cycle < goal.max_cycles:
        snapshot = target.observe()
        if target.goal_satisfied(goal, snapshot) is True:
            status = "completed"
            break
        context = {
            "goal": asdict(replace(goal, cycle=cycle)),
            "snapshot": snapshot.to_dict(),
            "capabilities": [asdict(item) for item in catalog.capabilities(goal.target_id)],
            "specialists": [],
            "pending_advice": [],
            "cognitive_phase": "direct",
            "specialist_performance": {},
            "recent_experience": outcomes[-8:],
            "specialist_query": {},
        }
        executive_attempt_id = uuid.uuid4().hex
        attempt_started = time.perf_counter()
        try:
            decision = BrainDecision.from_dict(model.decide(context))
        except Exception as error:
            caller_wall_ms = (time.perf_counter() - attempt_started) * 1000
            caller_attempt_latencies.append(caller_wall_ms)
            provider_errors += 1
            failure_usage = dict(model.last_usage)
            if failure_usage:
                failure_usage["caller_wall_ms"] = caller_wall_ms
                failed_usage_records.append(failure_usage)
            error_event = {
                "cycle": cycle,
                "kind": "model_error",
                "executive_attempt_id": executive_attempt_id,
                "error": f"{type(error).__name__}: {error}",
                "caller_wall_ms": caller_wall_ms,
                "usage": failure_usage,
            }
            trace.append(error_event)
            outcomes.append({"kind": "model_error", "payload": error_event})
            cycle += 1
            continue
        usage = dict(model.last_usage)
        usage["caller_wall_ms"] = (time.perf_counter() - attempt_started) * 1000
        caller_attempt_latencies.append(float(usage["caller_wall_ms"]))
        calls.append(usage)
        decision_kinds.append(decision.kind.value)
        trace.append(
            {
                "cycle": cycle,
                "kind": "decision",
                "executive_attempt_id": executive_attempt_id,
                "decision": decision.to_dict(),
                "usage": usage,
            }
        )
        if decision.kind is DecisionKind.USE_TOOL:
            tool_attempts += 1
            invocation_id = uuid.uuid4().hex
            call = ToolCall(
                decision.name or "", decision.arguments, target_id=goal.target_id
            )
            try:
                catalog.validate_call(goal.target_id, call)
            except Exception as error:
                capability_validation_errors += 1
                terminal_states.append("failed")
                last_terminal = {"id": invocation_id, "state": "failed"}
                outcome = {
                    "kind": "tool_result",
                    "payload": {
                        "invocation_id": invocation_id,
                        "decision_attempt_id": executive_attempt_id,
                        "call": call.to_dict(),
                        "error_class": "capability_validation",
                        "error": str(error),
                        "pre_snapshot_sha256": _sha256(
                            _canonical_snapshot(snapshot)
                        ),
                    },
                }
                outcomes.append(outcome)
                trace.append({"cycle": cycle, **outcome})
            else:
                tool_dispatches += 1
                try:
                    result = target.execute(call)
                    post = target.observe()
                    if result.succeeded:
                        catalog.validate_output(
                            goal.target_id, call.capability_id, result.output
                        )
                    terminal = (
                        "succeeded"
                        if result.succeeded
                        else "partial"
                        if result.partial
                        else "failed"
                    )
                    terminal_states.append(terminal)
                    last_terminal = {"id": invocation_id, "state": terminal}
                    outcome = {
                        "kind": "tool_result",
                        "payload": {
                            "invocation_id": invocation_id,
                            "decision_attempt_id": executive_attempt_id,
                            "call": call.to_dict(),
                            "result": result.to_dict(),
                            "pre_revision": snapshot.revision,
                            "post_revision": post.revision,
                            "pre_snapshot_sha256": _sha256(
                                _canonical_snapshot(snapshot)
                            ),
                            "post_snapshot_sha256": _sha256(
                                _canonical_snapshot(post)
                            ),
                        },
                    }
                    outcomes.append(outcome)
                    trace.append({"cycle": cycle, **outcome})
                    if target.goal_satisfied(goal, post) is True:
                        status = "completed"
                        cycle += 1
                        break
                except Exception as error:
                    execution_exceptions += 1
                    terminal_states.append("failed")
                    last_terminal = {"id": invocation_id, "state": "failed"}
                    outcome = {
                        "kind": "tool_result",
                        "payload": {
                            "invocation_id": invocation_id,
                            "decision_attempt_id": executive_attempt_id,
                            "call": call.to_dict(),
                            "error_class": "execution",
                            "error": str(error),
                            "pre_snapshot_sha256": _sha256(
                                _canonical_snapshot(snapshot)
                            ),
                        },
                    }
                    outcomes.append(outcome)
                    trace.append({"cycle": cycle, **outcome})
        elif decision.kind is DecisionKind.COMPLETE:
            completion_rejections += 1
        elif decision.kind is DecisionKind.ABANDON:
            status = "abandoned"
            break
        cycle += 1
        if (
            world == "grid"
            and restart_boundary is None
            and len(terminal_states) >= RESTART_AFTER_TOOL_INVOCATIONS
        ):
            before_snapshot = target.observe()
            restart_boundary = {
                "reached": True,
                "after_terminal_tool_invocations": len(terminal_states),
                "at_cycle_index": cycle,
                "terminal_invocation_id": last_terminal["id"] if last_terminal else None,
                "terminal_invocation_state": (
                    last_terminal["state"] if last_terminal else None
                ),
                "pre_restart_snapshot_sha256": _sha256(
                    _canonical_snapshot(before_snapshot)
                ),
                "note": (
                    "provider history cleared; favorable external harness retained "
                    "GoalSpec and in-memory outcomes"
                ),
            }
            model.reset_session()
            after_snapshot = target.observe()
            restart_boundary.update(
                {
                    "post_restart_snapshot_sha256": _sha256(
                        _canonical_snapshot(after_snapshot)
                    ),
                    "continuity_equal": _sha256(_canonical_snapshot(before_snapshot))
                    == _sha256(_canonical_snapshot(after_snapshot)),
                }
            )
    if status == "active":
        status = "budget_exhausted"
    wall_ms = (time.perf_counter() - started) * 1000
    usage_records = [*calls, *failed_usage_records]
    input_bytes = [float(item.get("input_bytes", 0)) for item in usage_records]
    caller_latencies = caller_attempt_latencies
    provider_latencies = [
        float(item.get("timings", {}).get("predicted_ms", 0))
        for item in usage_records
    ]
    final_snapshot = target.observe()
    _write_json(base / "trace.json", trace)
    return {
        "status": status,
        "oracle": target.goal_satisfied(goal, final_snapshot) is True,
        "final_cycle_index": cycle,
        "executive_attempts": len(calls) + provider_errors,
        "executive_succeeded": len(calls),
        "executive_failed": provider_errors,
        "executive_decisions": len(decision_kinds),
        "usage_coverage": {
            "records": len(usage_records),
            "attempts": len(calls) + provider_errors,
        },
        "decisions_by_kind": {
            kind: decision_kinds.count(kind) for kind in sorted(set(decision_kinds))
        },
        "specialist_calls": 0,
        "specialist_identities": [],
        "specialist_caller_wall_latency_ms": {
            "total": 0.0,
            "p50": 0.0,
            "p95": 0.0,
        },
        "tool_invocation_attempts": tool_attempts,
        "tool_dispatches": tool_dispatches,
        "semantic_decision_rejections": 0,
        "completion_rejections": completion_rejections,
        "capability_validation_errors": capability_validation_errors,
        "execution_exceptions": execution_exceptions,
        "tool_results_failed": terminal_states.count("failed"),
        "tool_results_partial": terminal_states.count("partial"),
        "tool_results_unknown": terminal_states.count("unknown"),
        "invocation_states": {
            state: terminal_states.count(state) for state in sorted(set(terminal_states))
        },
        "prompt_tokens_known": sum(
            int(item.get("usage", {}).get("prompt_tokens", 0))
            for item in usage_records
        ),
        "completion_tokens_known": sum(
            int(item.get("usage", {}).get("completion_tokens", 0))
            for item in usage_records
        ),
        "provider_input_bytes": {
            "max": int(max(input_bytes, default=0)),
            "p50": int(_percentile(input_bytes, 0.50)),
            "p95": int(_percentile(input_bytes, 0.95)),
        },
        "model_caller_wall_latency_ms": {
            "total": round(sum(caller_latencies), 3),
            "p50": round(_percentile(caller_latencies, 0.50), 3),
            "p95": round(_percentile(caller_latencies, 0.95), 3),
        },
        "provider_reported_prediction_ms": {
            "total": round(sum(provider_latencies), 3),
            "p50": round(_percentile(provider_latencies, 0.50), 3),
            "p95": round(_percentile(provider_latencies, 0.95), 3),
        },
        "condition_wall_ms": round(wall_ms, 3),
        "restart_boundary": restart_boundary,
        "restart_contract": (
            "favorable external harness baseline, not intrinsic process continuity"
            if restart_boundary is not None
            else None
        ),
        "initial_snapshot_sha256": initial_hash,
        "final_snapshot_sha256": _sha256(
            {
                "target_id": final_snapshot.target_id,
                "revision": final_snapshot.revision,
                "state": final_snapshot.state,
            }
        ),
        "returned_models": sorted(
            {
                str(item.get("model"))
                for item in usage_records
                if item.get("model")
            }
        ),
    }


def run_pilot(base: Path) -> dict[str, Any]:
    conditions: dict[str, Callable[[Path, str], dict[str, Any]]] = {
        "C0_bounded_monolith": _run_monolith,
        "C1_durable_single": lambda path, world: _run_engine_condition(
            path, world, multi=False
        ),
        "C2_engine_multi": lambda path, world: _run_engine_condition(
            path, world, multi=True
        ),
    }
    results: dict[str, Any] = {}
    summary: dict[str, Any] = {
        "status": "exploratory_pilot_running",
        "claim_scope": (
            "Instrumentation and directional comparison only; one consumed run per "
            "hand-built fixture. No statistical or architectural-superiority claim."
        ),
        "model_requested": MODEL_ARTIFACT,
        "model_artifact_sha256": MODEL_SHA256,
        "source_sha256": _source_sha256(),
        "prompt_sha256": hashlib.sha256(
            LlamaCppDecisionModel._system_prompt().encode("utf-8")
        ).hexdigest(),
        "decision_schema_family_sha256": _sha256(
            LlamaCppDecisionModel.base_decision_schema
        ),
        "condition_order": list(conditions),
        "condition_order_warning": "fixed order; latency comparisons are confounded",
        "restart_after_terminal_tool_invocations": RESTART_AFTER_TOOL_INVOCATIONS,
        "baseline_contracts": {
            "C0": (
                "favorable external harness: fresh target snapshot and GoalSpec each "
                "turn, last two provider turns plus recent in-memory outcomes"
            ),
            "C1": "Engine Heart plus same executive model, no specialists",
            "C2": (
                "same Heart/model plus deterministic task-solving specialists; "
                "C2-C1 mixes added competence and orchestration"
            ),
        },
        "provider_config": {
            "base_url": "http://127.0.0.1:18080/v1",
            "temperature": 0.0,
            "max_output_tokens": 640,
            "max_input_bytes": 64000,
            "session_history": "C0 only, bounded to the last two user/assistant turns",
            "server_context_tokens": 8192,
            "requested_output_token_reserve": 640,
            "seed": "server default/unknown; temperature fixed at 0",
        },
        "conditions": results,
    }
    _write_json(base / "partial-summary.json", summary)
    for condition, runner in conditions.items():
        results[condition] = {}
        for world in ("filesystem", "grid"):
            condition_base = base / condition / world
            condition_base.mkdir(parents=True, exist_ok=True)
            try:
                results[condition][world] = runner(condition_base, world)
            except Exception as error:
                results[condition][world] = {
                    "status": "aborted_instrument",
                    "error": f"{type(error).__name__}: {error}",
                }
            _write_json(base / "partial-summary.json", summary)
    summary["status"] = "exploratory_pilot_consumed"
    _write_json(base / "summary.json", summary)
    return summary


def main() -> None:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = Path("artifacts/experiments/EXP-2026-001-pilot/runs") / timestamp
    summary = run_pilot(base)
    print(json.dumps({"artifact_dir": str(base), **summary}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
