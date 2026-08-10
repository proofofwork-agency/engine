from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .charter import HomeCharterCompiler, PreferenceLearner
from .config import HomeyConfigError, load_config
from .store import HomeOpsStore
from .transport import CLIHomeyTransport, HomeyTransportError
from .v2 import _build_target_v2


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="engine-homey",
        description="Whole-house Homey application plugin for Engine",
    )
    result.add_argument(
        "--config",
        help="TOML path (otherwise ENGINE_HOMEY_CONFIG)",
    )
    commands = result.add_subparsers(dest="command", required=True)
    connect = commands.add_parser(
        "connect", help="Verify an already-authorized official Homey CLI session"
    )
    connect.add_argument(
        "--from-cli",
        action="store_true",
        help="Use `homey select` and the CLI OAuth session without exporting a token",
    )
    commands.add_parser("discover", help="Read and print the projected whole house")
    compile_parser = commands.add_parser(
        "compile-charter",
        help="Compile natural-language charter text into HomeCharterV1",
    )
    compile_parser.add_argument("path", type=Path)
    commands.add_parser("show-charter", help="Print the active typed charter")
    correct = commands.add_parser(
        "correct", help="Apply an explicit user correction as a versioned preference"
    )
    correct.add_argument("text")
    correct.add_argument("--zone")
    correct.add_argument("--brightness", type=float)
    manual = commands.add_parser(
        "record-override",
        help="Record an unexplained manual override as INFERRED evidence only",
    )
    manual.add_argument("alias")
    manual.add_argument("capability")
    manual.add_argument("value")
    commands.add_parser(
        "run", help="Deprecated: use the plugin-neutral `engine run` command"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "connect":
            if not arguments.from_cli:
                raise ValueError("connect currently requires --from-cli")
            transport = CLIHomeyTransport()
            selected = transport.selected_homey()
            zones, devices = transport.read_house()
            _print(
                {
                    "connected": True,
                    "homey": {
                        "id": selected.get("id"),
                        "name": selected.get("name"),
                    },
                    "inventory": {"zones": len(zones), "devices": len(devices)},
                    "auth": "official_homey_cli_session",
                    "credential_persisted_by_engine": False,
                    "transport": "polling",
                }
            )
            return 0
        config = load_config(arguments.config)
        return _run(arguments, config)
    except (HomeyConfigError, HomeyTransportError, ValueError, OSError) as error:
        print(f"engine-homey: {error}", file=sys.stderr)
        return 2


def _run(arguments: argparse.Namespace, config: object) -> int:
    # The annotation stays local to keep argparse error paths import-light.
    from .config import HomeyConfig

    assert isinstance(config, HomeyConfig)
    store = HomeOpsStore(config.plugin_database)
    try:
        if arguments.command == "compile-charter":
            text = arguments.path.read_text(encoding="utf-8")
            charter = HomeCharterCompiler().compile(
                text,
                zone_aliases=tuple(item.alias for item in config.zones),
                devices=config.devices,
            )
            store.save_charter(charter, text)
            _print(charter)
            return 0
        if arguments.command == "show-charter":
            charter = store.active_charter()
            if charter is None:
                raise ValueError("no active charter; run compile-charter first")
            _print(charter)
            return 0
        if arguments.command == "correct":
            context = (
                {"brightness": arguments.brightness}
                if arguments.brightness is not None
                else {}
            )
            result = PreferenceLearner(store).apply_correction(
                arguments.text, zone=arguments.zone, context=context
            )
            _print(result)
            return 0
        if arguments.command == "record-override":
            evidence_id = PreferenceLearner(store).record_manual_override(
                {
                    "alias": arguments.alias,
                    "capability": arguments.capability,
                    "value": arguments.value,
                }
            )
            _print({"evidence_id": evidence_id, "grade": "INFERRED", "patched": False})
            return 0

        if arguments.command == "discover":
            target = _build_target_v2(
                config, store, transport=None, event_source=None
            )
            _print(target.observe().to_dict())
            return 0
        if arguments.command == "run":
            raise ValueError(
                "engine-homey run was retired; enroll the Homey plugin with "
                "`engine setup` and start the generic runtime with `engine run`"
            )
        raise AssertionError(f"unhandled command: {arguments.command}")
    finally:
        store.close()


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
