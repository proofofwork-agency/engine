---
title: CLI reference
description: Current engine and engine-plugin commands in the repository.
sidebar_position: 4
---

# CLI reference

The workspace provides two command-line interfaces:

- `engine`: the plugin-neutral runtime and operational CLI;
- `engine-plugin`: scaffolding, manifest inspection, and plugin tests.

From this repository, use `uv run engine ...` and
`uv run engine-plugin ...`. The tables below follow the current `argparse`
parsers; unimplemented roadmap commands are not included.

## `engine plugins`

```console
uv run engine plugins list
uv run engine plugins inspect <plugin-id>
```

`list` returns a JSON array of static manifests found for installed
`engine.plugins` entry points. `inspect` returns the canonically serialized
manifest. An unknown ID exits with code 2.

This is local Python discovery, not a marketplace or registry client.

## `engine world observe`

```console
uv run engine world observe
```

Asks every registered target for an observation, materializes one
`WorldSnapshotV2`, and writes it to the Engine store. The command acquires the
runtime lease, so a concurrent mutating or observing runtime may block it. A
provider failure is represented in coverage so missing state is not presented
as `false`.

## `engine setup`

```console
uv run engine setup \
  --plugin engine.reference-world \
  --target engine.reference-world.warehouse \
  --entity warehouse:bin:reserve \
  --capability warehouse.transfer-bin \
  --learning engine.reference-world.preference.reserve-target-band/v1 \
  --intent "Keep sufficient inventory available"
```

Required options:

| Option | Meaning |
| --- | --- |
| `--plugin` | Exact plugin ID |
| `--target` | Observed target belonging to that plugin |
| `--entity` | Observed entity under that target |
| `--capability` | Non-opaque declared capability family |
| `--learning` | Namespaced preference bound to the family |
| `--intent` | Free text for GoalSpec compilation |
| `--activate` | Actually persist the mandate and goal |

Without `--activate`, setup is a preview and writes no goal or mandate. With
`--activate`, it stores a one-year mandate scoped to the selected plugin,
target, entity, capability, limits, and manifest version.

The current setup route requires a configured structured-output model; its
result is then schema-validated and may not escape the selected family or entity.
The CLI does not yet provide a generic approval workflow for high-risk authority.

## `engine run`

```console
uv run engine run
```

Starts the living loop until it receives `SIGINT` or `SIGTERM`. The runtime:

- holds one SQLite lease with a heartbeat;
- subscribes where plugins provide events;
- polls each target at its own interval;
- processes durable wakes and task handles;
- observes, evaluates routines and goals, and runs the mutation lifecycle when needed.

A second runtime on the same store fails closed on the lease. If the active
runtime loses its lease, the lease watcher asks the loop to stop.

## `engine status`

```console
uv run engine status
uv run engine status --json
```

Both forms currently produce JSON. The result includes:

- `store`, `plugins`, `targets`, and `plugin_failures`;
- the latest `snapshot`;
- active `goals`;
- preference-learning candidates;
- routines and routine candidates;
- autonomy profiles;
- autonomy mode, enrollments, evaluations, proposals, and dispatch attempts;
- the executive brain ID.

`status` does not acquire the mutating runtime lease and reads durable state.

## `engine learning`

```console
uv run engine learning status
uv run engine learning correct \
  --goal <goal-id> \
  --preference <preference-id> \
  --value '<json-value>'
uv run engine learning rollback --candidate <candidate-id>
```

`status` shows candidates. `correct` is an explicit owner correction: the JSON
value is validated against the preference schema and produces a new GoalSpec
version. `rollback` operates only on the exact candidate and reverses a promoted
change through the stored patch.

Unexplained behavior is not simulated through `correct`; it follows the slower
evidence → candidate → shadow route.

## `engine routines`

```console
uv run engine routines list
uv run engine routines inspect <candidate-or-routine-id>
uv run engine routines approve <candidate-id>
uv run engine routines reject <candidate-id>
uv run engine routines rollback <routine-id>
```

`approve` accepts only a candidate with status `ready_for_approval`, never an
untested or still-shadowing candidate. `rollback` makes the linked routine
inoperative while retaining the audit trail.

## `engine autonomy`

```console
uv run engine autonomy mode observe|supervised|delegated|paused
uv run engine autonomy status
uv run engine autonomy strategies list
uv run engine autonomy strategies inspect <strategy-id>
uv run engine autonomy enroll \
  --plugin <plugin-id> \
  --strategy <strategy-id> \
  --target <target-id> \
  --entity <entity-id> \
  --capability <family> \
  [--template <template-id>] \
  [--context-plugin <plugin-id>] \
  [--privacy public|local|sensitive|camera] \
  [--cognition-route deterministic|executive|specialist|hybrid] \
  [--limits '<json>'] [--budget '<json>'] [--expires-hours 24] \
  [--control-existing-goals] [--instantiate-goal-templates] \
  [--promote-proven-routines]
uv run engine autonomy list
uv run engine autonomy inspect <enrollment-id>
uv run engine autonomy disable <enrollment-id>
uv run engine autonomy proposals list
uv run engine autonomy proposals inspect <evaluation-id>
uv run engine autonomy proposals approve <evaluation-id>
uv run engine autonomy proposals reject <evaluation-id> [--reason <text>]
```

Mode changes do not acquire the active runtime lease and therefore take effect
while Heart is running. They grant no scope. `enroll` requires fresh exact
targets and entities, declared v3 strategy/capability/template identities, a
matching cognition route, at most low risk, explicit privileges, fingerprints,
and non-overlapping conflict resources. Wildcards fail closed.

`observe` is true shadow with zero dispatch. `supervised` stores a pending
proposal and approval reobserves and reevaluates it. `delegated` admits only an
enabled exact enrollment. `paused` allows observation, learning, and recovery
but no new strategy, brain, or dispatch activity.

## `engine yolo`

```console
uv run engine yolo enable
uv run engine yolo status
uv run engine yolo disable
```

`yolo` is only a global alias: enable selects `delegated`, disable selects
`paused`, and status returns `engine autonomy status`. It creates no enrollment.
The parser still recognizes old target-specific flags only to return a migration
instruction; use `engine autonomy enroll` for exact plugin scope.

## `engine model canary`

```console
uv run engine model canary
```

Makes one real structured-output decision through the configured provider and
shows the decision plus usage. The command fails without model configuration.

Supported runtime variables:

| Variable | Purpose |
| --- | --- |
| `ENGINE_DATABASE` | Store path; default `.engine/engine.sqlite3` |
| `ENGINE_MODEL_BASE_URL` | OpenAI-compatible endpoint |
| `ENGINE_MODEL_API_KEY` | Key for a remote endpoint |
| `ENGINE_MODEL_ID` | Model ID |
| `ENGINE_MODEL_PROVIDER` | Provider audit ID |
| `ENGINE_LOCAL_MODEL_BASE_URL` | Alias for a local endpoint |
| `ENGINE_LOCAL_MODEL_ID` | Alias for a local model |
| `META_MODEL_API_BASE_URL` | Meta provider alias |
| `META_MODEL_API_KEY` | Meta provider key |
| `META_MODEL_ID` | Meta model ID |

Only `localhost` and numeric loopback hosts may omit an API key. Engine does not
start or download a local model process.

## `engine-plugin`

```console
uv run engine-plugin init <name> \
  [--template world|specialist|full] \
  [--destination <directory>]

uv run engine-plugin validate [<plugin-directory>]
uv run engine-plugin inspect [<plugin-directory>]
uv run engine-plugin test [<plugin-directory>]
```

`init` refuses a non-empty destination. `validate` reads only the static
manifest; `inspect` prints the canonical form. `test` validates first and then
runs `python -m unittest discover -s tests -v` with the generated `src` on
`PYTHONPATH`.

## Exit codes and error output

Both CLIs return 0 on success and 2 for handled contract or runtime errors.
`engine` prints `error: <Type>: <message>` to stderr; `engine-plugin` prints
manifest contract errors as `invalid: <message>`.
