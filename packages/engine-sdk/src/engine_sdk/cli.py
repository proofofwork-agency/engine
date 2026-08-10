from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .manifest import load_static_manifest
from .models import ContractError, canonical_data
from .scaffold import scaffold_plugin


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine-plugin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init", help="create a v2 plugin skeleton")
    init.add_argument("name")
    init.add_argument("--template", choices=("world", "specialist", "full"), default="world")
    init.add_argument("--destination", default=".")
    for name in ("validate", "inspect", "test"):
        command = subparsers.add_parser(name)
        command.add_argument("path", nargs="?", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            created = scaffold_plugin(args.destination, args.name, args.template)
            print(created)
            return 0
        root = Path(args.path).resolve()
        manifest = load_static_manifest(root)
        if args.command == "validate":
            print(f"valid: {manifest.id}@{manifest.version}")
            return 0
        if args.command == "inspect":
            print(json.dumps(canonical_data(manifest), indent=2, sort_keys=True))
            return 0
        if args.command == "test":
            print(f"valid: {manifest.id}@{manifest.version}")
            environment = dict(os.environ)
            source_path = str(root / "src")
            environment["PYTHONPATH"] = os.pathsep.join(
                item for item in (source_path, environment.get("PYTHONPATH", "")) if item
            )
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=root,
                env=environment,
                check=False,
            )
            return result.returncode
    except ContractError as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
