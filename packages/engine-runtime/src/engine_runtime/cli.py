from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from typing import Any

from engine_sdk import canonical_data

from .application import EngineApplication, RuntimeConfig
from .discovery import installed_manifests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine")
    top = parser.add_subparsers(dest="command", required=True)

    plugins = top.add_parser("plugins")
    plugins_sub = plugins.add_subparsers(dest="plugins_command", required=True)
    plugins_sub.add_parser("list")
    inspect = plugins_sub.add_parser("inspect")
    inspect.add_argument("plugin_id")

    world = top.add_parser("world")
    world_sub = world.add_subparsers(dest="world_command", required=True)
    world_sub.add_parser("observe")

    store = top.add_parser("store")
    store_sub = store.add_subparsers(dest="store_command", required=True)
    store_sub.add_parser("status")
    store_prune = store_sub.add_parser("prune")
    store_prune.add_argument("--vacuum", action="store_true")

    setup = top.add_parser("setup")
    setup.add_argument("--plugin", required=True)
    setup.add_argument("--target", required=True)
    setup.add_argument("--entity", required=True)
    setup.add_argument("--capability", required=True)
    setup.add_argument("--learning", required=True)
    setup.add_argument("--intent", required=True)
    setup.add_argument("--activate", action="store_true")

    top.add_parser("run")
    status = top.add_parser("status")
    status.add_argument("--json", action="store_true")

    learning = top.add_parser("learning")
    learning_sub = learning.add_subparsers(dest="learning_command", required=True)
    learning_sub.add_parser("status")
    correct = learning_sub.add_parser("correct")
    correct.add_argument("--goal", required=True)
    correct.add_argument("--preference", required=True)
    correct.add_argument("--value", required=True, help="JSON preference value")
    rollback = learning_sub.add_parser("rollback")
    rollback.add_argument("--candidate", required=True)

    autonomy = top.add_parser("autonomy")
    autonomy_sub = autonomy.add_subparsers(dest="autonomy_command", required=True)
    autonomy_mode = autonomy_sub.add_parser("mode")
    autonomy_mode.add_argument(
        "mode", choices=("observe", "supervised", "delegated", "paused")
    )
    autonomy_sub.add_parser("status")
    strategies = autonomy_sub.add_parser("strategies")
    strategies_sub = strategies.add_subparsers(
        dest="autonomy_strategies_command", required=True
    )
    strategies_sub.add_parser("list")
    strategy_inspect = strategies_sub.add_parser("inspect")
    strategy_inspect.add_argument("id")
    enroll = autonomy_sub.add_parser("enroll")
    enroll.add_argument("--plugin", required=True)
    enroll.add_argument("--strategy", required=True)
    enroll.add_argument("--target", action="append", required=True)
    enroll.add_argument("--entity", action="append", required=True)
    enroll.add_argument("--capability", action="append", required=True)
    enroll.add_argument("--template", action="append", default=[])
    enroll.add_argument("--context-plugin", action="append", default=[])
    enroll.add_argument("--privacy", action="append", default=[])
    enroll.add_argument(
        "--cognition-route",
        choices=("deterministic", "executive", "specialist", "hybrid"),
    )
    enroll.add_argument("--risk-ceiling", default="low", choices=("read_only", "low"))
    enroll.add_argument("--limits", default="{}", help="JSON parameter/action limits")
    enroll.add_argument("--budget", default="{}", help="JSON evaluation budget")
    enroll.add_argument("--expires-hours", type=float, default=24.0)
    enroll.add_argument("--control-existing-goals", action="store_true")
    enroll.add_argument("--instantiate-goal-templates", action="store_true")
    enroll.add_argument("--promote-proven-routines", action="store_true")
    autonomy_sub.add_parser("list")
    enrollment_inspect = autonomy_sub.add_parser("inspect")
    enrollment_inspect.add_argument("id")
    enrollment_disable = autonomy_sub.add_parser("disable")
    enrollment_disable.add_argument("id")
    proposals = autonomy_sub.add_parser("proposals")
    proposals_sub = proposals.add_subparsers(
        dest="autonomy_proposals_command", required=True
    )
    proposals_sub.add_parser("list")
    proposal_inspect = proposals_sub.add_parser("inspect")
    proposal_inspect.add_argument("id")
    proposal_approve = proposals_sub.add_parser("approve")
    proposal_approve.add_argument("id")
    proposal_reject = proposals_sub.add_parser("reject")
    proposal_reject.add_argument("id")
    proposal_reject.add_argument("--reason", default="local owner rejected proposal")

    yolo = top.add_parser("yolo")
    yolo_sub = yolo.add_subparsers(dest="yolo_command", required=True)
    enable = yolo_sub.add_parser("enable")
    enable.add_argument("--plugin")
    enable.add_argument("--target")
    enable.add_argument("--entity", action="append", default=[])
    enable.add_argument("--maximum-brightness", type=float)
    enable.add_argument("--maximum-power-w", type=float)
    yolo_sub.add_parser("status")
    disable = yolo_sub.add_parser("disable")
    disable.add_argument("--profile")

    routines = top.add_parser("routines")
    routines_sub = routines.add_subparsers(dest="routines_command", required=True)
    routines_sub.add_parser("list")
    routine_inspect = routines_sub.add_parser("inspect")
    routine_inspect.add_argument("id")
    approve = routines_sub.add_parser("approve")
    approve.add_argument("id")
    reject = routines_sub.add_parser("reject")
    reject.add_argument("id")
    routine_rollback = routines_sub.add_parser("rollback")
    routine_rollback.add_argument("id")

    model = top.add_parser("model")
    model_sub = model.add_subparsers(dest="model_command", required=True)
    model_sub.add_parser("canary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plugins":
            manifests = installed_manifests()
            if args.plugins_command == "list":
                print(json.dumps([item.id for item in manifests], indent=2))
                return 0
            manifest = next(
                (item for item in manifests if item.id == args.plugin_id), None
            )
            if manifest is None:
                raise ValueError(f"unknown plugin: {args.plugin_id}")
            _print(canonical_data(manifest))
            return 0

        app = EngineApplication(RuntimeConfig.from_environment())
        try:
            if args.command == "store":
                if args.store_command == "status":
                    _print(canonical_data(app.store_status()))
                else:
                    with app.lease():
                        summary = app.store_prune(vacuum=args.vacuum)
                    _print(canonical_data(summary))
                return 0
            if args.command == "world":
                with app.lease():
                    _print(canonical_data(app.observe()))
                return 0
            if args.command == "setup":
                with app.lease():
                    _print(
                        app.setup(
                            plugin_id=args.plugin,
                            target_id=args.target,
                            entity_id=args.entity,
                            capability_family=args.capability,
                            preference_id=args.learning,
                            intent=args.intent,
                            activate=args.activate,
                        )
                    )
                return 0
            if args.command == "run":
                stop = threading.Event()

                def request_stop(*_args: object) -> None:
                    stop.set()

                signal.signal(signal.SIGINT, request_stop)
                signal.signal(signal.SIGTERM, request_stop)
                with app.lease(on_lost=stop.set) as lease:
                    app.heart.run_forever(stop, lease_lost=lambda: lease.lost)
                return 0
            if args.command == "status":
                _print(app.status())
                return 0
            if args.command == "learning":
                if args.learning_command == "status":
                    _print(
                        [canonical_data(item) for item in app.store.learning_candidates()]
                    )
                    return 0
                with app.lease():
                    if args.learning_command == "correct":
                        _print(
                            canonical_data(
                                app.correct(
                                    goal_id=args.goal,
                                    preference_id=args.preference,
                                    value=json.loads(args.value),
                                )
                            )
                        )
                    else:
                        _print(
                            canonical_data(
                                app.rollback(candidate_id=args.candidate)
                            )
                        )
                return 0
            if args.command == "autonomy":
                if args.autonomy_command == "mode":
                    _print(app.autonomy_mode(args.mode))
                    return 0
                if args.autonomy_command == "status":
                    _print(app.autonomy_status())
                    return 0
                if args.autonomy_command == "strategies":
                    if args.autonomy_strategies_command == "list":
                        _print(
                            [canonical_data(item) for item in app.autonomy_strategies()]
                        )
                    else:
                        _print(app.autonomy_strategy_inspect(args.id))
                    return 0
                if args.autonomy_command == "enroll":
                    with app.lease():
                        value = app.autonomy_enroll(
                            plugin_id=args.plugin,
                            strategy_id=args.strategy,
                            target_ids=tuple(args.target),
                            entity_ids=tuple(args.entity),
                            capability_families=tuple(args.capability),
                            goal_template_ids=tuple(args.template),
                            context_plugin_ids=tuple(args.context_plugin),
                            privacy_grants=tuple(args.privacy),
                            cognition_route=args.cognition_route,
                            risk_ceiling=args.risk_ceiling,
                            limits=json.loads(args.limits),
                            budget=json.loads(args.budget),
                            expires_hours=args.expires_hours,
                            control_existing_goals=args.control_existing_goals,
                            instantiate_goal_templates=args.instantiate_goal_templates,
                            promote_proven_routines=args.promote_proven_routines,
                        )
                    _print(canonical_data(value))
                    return 0
                if args.autonomy_command == "list":
                    _print(
                        [canonical_data(item) for item in app.store.autonomy_enrollments()]
                    )
                    return 0
                if args.autonomy_command == "inspect":
                    _print(app.autonomy_enrollment_inspect(args.id))
                    return 0
                if args.autonomy_command == "disable":
                    _print(canonical_data(app.autonomy_enrollment_disable(args.id)))
                    return 0
                if args.autonomy_command == "proposals":
                    if args.autonomy_proposals_command == "list":
                        _print(app.autonomy_proposals())
                    elif args.autonomy_proposals_command == "inspect":
                        _print(app.autonomy_proposal_inspect(args.id))
                    elif args.autonomy_proposals_command == "approve":
                        with app.lease():
                            _print(canonical_data(app.autonomy_proposal_approve(args.id)))
                    else:
                        _print(
                            app.autonomy_proposal_reject(args.id, reason=args.reason)
                        )
                    return 0
            if args.command == "yolo":
                if args.yolo_command == "status":
                    _print(app.autonomy_status())
                    return 0
                if args.yolo_command == "enable":
                    legacy = (
                        args.plugin is not None
                        or args.target is not None
                        or bool(args.entity)
                        or args.maximum_brightness is not None
                        or args.maximum_power_w is not None
                    )
                    if legacy:
                        raise ValueError(
                            "target-specific YOLO flags were removed; use `engine autonomy enroll` first, then `engine autonomy mode delegated`"
                        )
                    _print(app.yolo_alias_enable())
                else:
                    if args.profile is not None:
                        raise ValueError(
                            "--profile is legacy; use `engine autonomy disable <enrollment-id>`"
                        )
                    _print(app.yolo_alias_disable())
                return 0
            if args.command == "routines":
                if args.routines_command == "list":
                    _print(app.routines_list())
                    return 0
                if args.routines_command == "inspect":
                    _print(app.routine_inspect(args.id))
                    return 0
                with app.lease():
                    if args.routines_command == "approve":
                        _print(canonical_data(app.routine_approve(args.id)))
                    elif args.routines_command == "reject":
                        _print(canonical_data(app.routine_reject(args.id)))
                    else:
                        app.routine_rollback(args.id)
                        _print({"rolled_back": args.id})
                return 0
            if args.command == "model" and args.model_command == "canary":
                if app.model is None:
                    raise RuntimeError("no structured model is configured")
                value = app.model.decide(
                    {
                        "contract": "engine.model-canary/v1",
                        "world": {"snapshot_id": "canary", "revision": 1},
                        "effect_results": {},
                        "specialists": [],
                    }
                )
                _print({"decision": value, "usage": app.model.last_usage})
                return 0
        finally:
            app.close()
    except Exception as exc:  # noqa: BLE001 - CLI composition boundary
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 2


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
