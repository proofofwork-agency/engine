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

    yolo = top.add_parser("yolo")
    yolo_sub = yolo.add_subparsers(dest="yolo_command", required=True)
    enable = yolo_sub.add_parser("enable")
    enable.add_argument("--plugin", default="engine.homey")
    enable.add_argument("--target")
    enable.add_argument("--entity", action="append", default=[])
    enable.add_argument("--maximum-brightness", type=float, default=0.70)
    enable.add_argument("--maximum-power-w", type=float, default=20.0)
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
                with app.lease(on_lost=stop.set):
                    app.heart.run_forever(stop)
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
            if args.command == "yolo":
                if args.yolo_command == "status":
                    _print(canonical_data(app.yolo_status()))
                    return 0
                with app.lease():
                    if args.yolo_command == "enable":
                        _print(
                            canonical_data(
                                app.yolo_enable(
                                    plugin_id=args.plugin,
                                    target_id=args.target,
                                    entity_ids=tuple(args.entity),
                                    maximum_brightness=args.maximum_brightness,
                                    maximum_power_w=args.maximum_power_w,
                                )
                            )
                        )
                    else:
                        _print(
                            canonical_data(
                                app.yolo_disable(profile_id=args.profile)
                            )
                        )
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
