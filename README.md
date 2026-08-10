# Engine

> An experimental, local-first runtime that turns durable goals into typed, bounded, and auditable actions across software and physical worlds.

Engine explores one central question: can a single living runtime combine human intent, durable world state, replaceable intelligence, and controlled execution without turning an LLM into the state store, authority boundary, or source of truth?

Engine consists of a **Heart**, exactly one active **general executive brain**, zero or more **specialist brains**, and installable **world plugins**. The Heart keeps goals and state alive. Brains choose or advise. Policy and authorization determine what may happen. Executors act. Fresh observations and effect oracles determine what actually happened.

> **Status:** experimental. The v2 contracts, SDK, runtime, reference world, context plugin, and a simulated Homey path are implemented and tested. This is not a production platform, safety certification, or evidence of broad physical autonomy.

## Why Engine exists

Many agents can call tools. Engine makes the harder boundary explicit:

```text
intent
  → durable GoalSpec
  → observe
  → brain/specialist proposes an effect
  → schema + preconditions
  → policy + risk
  → exact authorization
  → dispatch
  → fresh observation
  → effect oracle + durable receipt
```

Core invariants:

- model context is not authoritative world state;
- a proposal is not permission to execute;
- an acknowledgement is not proof of effect;
- software policy does not replace physical safety systems;
- deliberative AI does not belong in hard-realtime control loops;
- state and experience are not model weights.

## Heart and brains

```text
ENGINE
├── Heart
│   ├── goals, snapshots, and continuity
│   ├── context projection and event/poll loop
│   ├── policy, execution, and receipt coordination
│   └── durable experience and reconstruction
├── exactly one general executive brain
│   ├── deterministic, or
│   └── model-backed with strict structured output
├── zero or more specialist brains
└── world plugins
    ├── providers and capabilities
    ├── domain controllers and executors
    ├── effect oracles
    └── optional experience and routine providers
```

The general brain chooses the next cognitive step. A specialist returns bounded, typed advice. Neither can grant authorization or declare its own action successful.

Multiple specialist brains and multiple plugins/targets are supported. Multiple concurrent general brains, voting, swarms, and automatic provider failover are not implemented.

## What exists today?

| Area | Status |
| --- | --- |
| Durable goals, snapshots, mandates, receipts, and reconstruction | Implemented and tested |
| `ACHIEVE` and `MAINTAIN` goals | Implemented and tested |
| Deterministic and OpenAI-compatible general-brain slot | Implemented; a live model requires explicit configuration |
| Multiple plugins, targets, and specialists in one world snapshot | Implemented and tested |
| `IMMEDIATE` lifecycle | Implemented and fake-tested |
| Durable `TASK` start/poll/cancel/restart | Implemented in the reference world |
| `STREAM` lifecycle | Contract and storage scaffolding; no end-to-end reference proof |
| Bounded preference and routine learning | Implemented and tested; no weight training |
| Homey | Live read-only observation; mutations are fake-tested only |
| Physical safety, hard realtime, and certification | Outside the current evidence boundary |

See [Status and evidence](docs-site/docs/reference/status-and-evidence.md) for the full claim matrix.

## Quickstart

Requirements:

- Python 3.12 or newer;
- [`uv`](https://docs.astral.sh/uv/);
- Node.js 20 or newer, only for the documentation site.

Install every workspace package:

```bash
uv sync --all-packages --locked
source .venv/bin/activate
```

Inspect the included plugins and observe the composed world:

```bash
engine plugins list
engine plugins inspect engine.reference-world
engine world observe
engine status --json
```

`engine world observe` may require plugin configuration. Imports and plugin factories are expected to be inert; network, database, or device work starts only when a provider is used.

Run the deterministic test suite:

```bash
uv run --with pytest pytest -q
```

The publication gate for this repository is `131 passed, 2 skipped, 34 subtests passed`. The skips are explicitly configured live-model canaries; core correctness does not require a live model.

## Create a plugin

The public plugin interface lives in `engine-sdk` and is independent of the runtime:

```bash
source .venv/bin/activate

engine-plugin init my-world --template full
engine-plugin validate my-world
engine-plugin inspect my-world
engine-plugin test my-world

uv pip install --python .venv/bin/python -e my-world
engine plugins list
```

Templates:

- `world`: provider, controller, executor, oracle, and experience provider;
- `specialist`: a bounded specialist brain only;
- `full`: world plus specialist.

A v2 plugin provides a static `engine-plugin.toml` and a Python entry point in the `engine.plugins` group. Dynamically discovered but undeclared capabilities become opaque/read-only; Engine does not trust them for mutation.

Continue with the [Plugin interface](docs-site/docs/developers/plugin-interface.md), [SDK reference](docs-site/docs/developers/sdk.md), and [Plugin checklist](docs-site/docs/developers/plugin-checklist.md).

## CLI overview

```text
engine plugins list|inspect
engine world observe
engine setup [--activate]
engine run
engine status [--json]
engine learning status|correct|rollback
engine routines list|inspect|approve|reject|rollback
engine yolo enable|status|disable
engine model canary
```

`engine setup` is a preview by default. Only `--activate` writes a goal and standing mandate. `engine model canary` performs a real network call when a provider is configured.

## Run the documentation locally

The complete English documentation lives in `docs-site/`:

```bash
cd docs-site
npm ci
npm run start
```

Build the production site with:

```bash
npm run build
```

Documentation includes:

- [what Engine is](docs-site/docs/concepts/what-is-engine.md) and [what it is not](docs-site/docs/concepts/what-engine-is-not.md);
- [Heart and brains](docs-site/docs/concepts/heart-and-brains.md);
- [all modes and state machines](docs-site/docs/concepts/modes.md);
- [how Engine learns—and how it does not](docs-site/docs/concepts/learning.md);
- [plugin interface, SDK, and CLI](docs-site/docs/developers/plugin-interface.md);
- [an honest comparison with other projects](docs-site/docs/reference/comparison.md);
- [the end goal and evidence boundaries](docs-site/docs/concepts/end-goal.md).

Published site: [proofofwork-agency.github.io/engine](https://proofofwork-agency.github.io/engine/).

## Repository layout

```text
src/engine/               Heart, world store, brains, policy, and learning
packages/engine-sdk/      Public plugin contracts and engine-plugin CLI
packages/engine-runtime/  Composition root, discovery, lease, and engine CLI
plugins/                  Reference world, context, and Homey plugins
tests/                    Core, lifecycle, reconstruction, and fault tests
docs/adr/                 Architecture Decision Records
docs-site/                Docusaurus documentation site
artifacts/                Experiment protocols and selected evidence
```

## Explicit non-claims

- Not a universal autonomous agent that can control every device.
- Not a replacement for Home Assistant, openHAB, ROS 2, target drivers, or safety hardware.
- Not a hard-realtime control loop.
- No physical safety certificate derived from simulation.
- No self-training model, online weight updates, or self-writing skill operating system.
- No evidence that multiple general brains are better; that composition does not exist.
- No public plugin marketplace, cryptographic signing, or enforced plugin sandbox yet.

## Contributing

Read [AGENTS.md](AGENTS.md), [RULES.md](RULES.md), and [GOAL.md](GOAL.md) first. A non-trivial change must identify the affected invariants, contracts, tests, and physical or external side effects before implementation. Never move a safety, oracle, metric, or acceptance boundary to make an outcome pass.

The short checksum:

```text
LLM proposal != authority
prediction != observation
policy != physical safety
deliberation != realtime control
simulation evidence != real-world certification
state != weights
imagine != execute
```
