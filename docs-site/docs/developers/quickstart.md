---
title: Repository quickstart
description: Install the uv workspace, inspect plugins, and run the contract tests.
sidebar_position: 1
---

# Repository quickstart

Engine is developed in this repository as a Python 3.12+ workspace. The packages
are not yet documented as a general PyPI installation route. Work from a checkout
of the repository and use the locked workspace file.

## Requirements

- Python 3.12 or newer;
- [uv](https://docs.astral.sh/uv/);
- a local checkout of this repository.

## 1. Synchronize the exact workspace

Run this in the repository root:

```console
uv sync --all-packages --locked
```

`--all-packages` includes `engine-heart`, `engine-sdk`, `engine-runtime`, and the
workspace plugins. `--locked` refuses an unintended recalculation of `uv.lock`.

## 2. Check discovery

```console
uv run engine plugins list
uv run engine plugins inspect engine.reference-world
```

The runtime finds installed plugins through the Python entry point group
`engine.plugins`. `plugins inspect` shows the static, validated declaration; it
does not query a marketplace or download anything.

## 3. Observe without mutating

```console
uv run engine world observe
uv run engine status --json
```

`world observe` asks the available providers for a fresh observation and stores
a composed `WorldSnapshotV2`. Missing configuration for an optional plugin is
reported as a discovery failure. Engine does not invent a negative state in that
case: missing or expired coverage remains `UNKNOWN` or `STALE`.

Observation does not mutate a target, but a configured provider may call local
or remote read APIs. Check the plugin declarations and privacy configuration
before using the command against real systems.

`status` shows the local store, plugins, targets, latest snapshot, goals,
learning candidates, routines, autonomy profiles, and selected executive brain.
The current CLI always writes this as JSON; `--json` is accepted to make the
intended output format explicit.

## 4. Run the public contract tests

These suites use only `unittest` and work after the locked sync:

```console
uv run python -m unittest discover -s packages/engine-sdk/tests -v
uv run python -m unittest discover -s packages/engine-runtime/tests -v
```

They check manifest validation, canonical hashing, the generated plugin, CLI
construction, model configuration, and setup preview, among other things. This
is software and contract evidence, not physical-safety certification.

## 5. Create a local example plugin

Choose an empty destination:

```console
uv run engine-plugin init my-world --template world --destination /tmp
cd /tmp/my-world
uv run --project /path/to/engine engine-plugin validate .
uv run --project /path/to/engine engine-plugin inspect .
uv run --project /path/to/engine engine-plugin test .
```

Replace `/path/to/engine` with the absolute repository root. You can also remain
in a shell at the Engine workspace and pass the plugin path as an argument:

```console
uv run engine-plugin validate /tmp/my-world
uv run engine-plugin inspect /tmp/my-world
uv run engine-plugin test /tmp/my-world
```

The templates are `world`, `specialist`, and `full`. `world` contains a warehouse
fake with a provider, controller, executor, and effect oracle; `specialist`
contains only a specialist; `full` combines both.

## No model required for the core

Discovery, observation, the deterministic executive, and contract tests do not
require an LLM. `engine setup` compiles free text into a proposed `GoalSpecV2`
and does require a configured structured-output model in the current runtime.
Without one, the command fails explicitly.

For an OpenAI-compatible endpoint:

```console
export ENGINE_MODEL_BASE_URL=https://provider.example/v1
export ENGINE_MODEL_API_KEY=...
export ENGINE_MODEL_ID=provider-model-id
uv run engine model canary
```

A loopback endpoint may omit an API key when configured through
`ENGINE_LOCAL_MODEL_BASE_URL` and `ENGINE_LOCAL_MODEL_ID`. A remote URL without
a key fails closed. `model canary` makes a real network call; do not run it unless
you intend the external transmission.

## Next steps

- Read the [plugin interface](./plugin-interface.md) before implementing roles.
- Use the [plugin checklist](./plugin-checklist.md) before enrollment.
- See the [CLI reference](./cli.md) for all current subcommands.
- Read [status and evidence](../reference/status-and-evidence.md) before treating
  an acknowledgement or model output as success.
