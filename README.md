# Engine

> An experimental, local-first runtime that turns durable goals into typed, bounded, and auditable actions across software and physical worlds.

A command lasts for a moment. Intent can last much longer. “Turn off the downstairs lights” is a command. “Keep the downstairs quiet and dark after everyone leaves” is a continuing desired state. “Reconcile these files once” and “keep this inventory above its reserve level” are different kinds of work, even when both begin as a sentence.

Engine turns those instructions into durable goals:

- `ACHIEVE`: make a stated outcome true once, then complete;
- `MAINTAIN`: keep a stated outcome true, monitor it, and reactivate when observed drift occurs.

A model or agent can help interpret the instruction and choose what to try. It remains replaceable cognition. Engine is the durable operational runtime: it owns the goal, current world state, lifecycle, authority checks, receipts, and measured effects outside any model session.

```text
interaction  ->  intelligence  ->  Engine  ->  target / world
chat or API      model/planner     durable     software, home,
                                  runtime      business system,
                                               energy or machine
```

The boundaries between these layers are deliberate. An interaction product can collect intent. A general model, classical planner, or specialist can propose a next step. Engine determines whether the exact action is valid and authorized against a fresh view of the world. The target-specific executor and controller perform it.

> **Status:** experimental. The v2 contracts, SDK, runtime, reference world, and context plugin are **Implemented**; their closed software loops and the Homey mutation path are **Fake/simulation-tested**. Homey observation is also **Live read-only**. This is not a production platform, a safety certification, or evidence of broad physical autonomy.

## A living cycle, not a longer model session

Engine keeps a **current world**—typed observations with source, time, quality, and coverage—and compares it with the **desired world** described by a goal. The Heart runs the cycle:

```text
durable intent
  -> fresh observation
  -> compare current world with desired world
  -> general brain or specialist proposes an effect
  -> validate schema and preconditions
  -> evaluate policy and risk
  -> authorize the exact request, or deny/defer
  -> dispatch to the target
  -> observe again
  -> reconcile measured effect
  -> record receipt and continue, monitor, or complete
```

Events are wake-up hints, not facts. A motion event, webhook, file notification, or task callback can wake the Heart, but Engine observes again before reasoning or acting. This matters because events may be duplicated, delayed, incomplete, or stale.

The same separation holds after execution. An API `200 OK`, device ACK, or accepted task means that a request reached an execution stage. It does not prove that a light changed, a file landed in the right place, or inventory moved. Only a fresh observation and a target-specific effect oracle can establish the result within their documented coverage. Otherwise the outcome remains `UNKNOWN`, `STALE`, or `CONFLICTING`.

## One Heart, replaceable cognition

```text
ENGINE
├── Heart
│   ├── durable goals, snapshots, and continuity
│   ├── event/poll wake loop and bounded context projection
│   ├── validation, policy, authorization, and dispatch coordination
│   └── receipts, effects, experience, and reconstruction
├── exactly one active general executive brain
│   ├── deterministic/classical planner, or
│   └── model-backed implementation with structured output
├── zero or more specialist brains
└── world plugins
    ├── providers and typed capabilities
    ├── domain controllers and executors
    ├── effect oracles
    ├── optional experience and routine providers
    └── optional lifecycle observers
```

The general executive chooses the next cognitive step. Specialists provide bounded domain advice. A Claude model, GPT model, local model, or classical planner could fill a brain role behind the relevant typed interface; none becomes operational state or authority by doing so. The current runtime selects exactly one active general executive. It does not implement a council, vote, swarm, or automatic multi-model failover. Multiple plugins, targets, and specialists are supported.

## Learning stays inside the boundary

Engine uses “learning” narrowly. Explicit corrections can update a declared preference. Repeated behavior can produce a candidate preference or routine, which must pass fixed evidence and shadow gates. Discovery creates candidates only: it cannot add a target, invent a capability, raise a risk ceiling, extend a mandate, or grant execution authority.

This is durable, reversible preference and routine promotion—not online model training. Learned or model-backed specialists receive the same authority as any other proposal provider: none.

## Five example applications

| World | Example | Evidence label |
| --- | --- | --- |
| Smart home | Observe a composed Homey house; maintain lighting while checking lux and power instead of trusting an ACK | **Live read-only** observation; mutation is **Fake/simulation-tested** |
| Software | Reach a filesystem goal after multiple steps, record partial failure, and reconstruct after restart | **Fake/simulation-tested** |
| Business operations | Maintain a warehouse reserve through an asynchronous transfer task, polling, cancellation, and an independent oracle | **Fake/simulation-tested** |
| Energy | Coordinate live loads, tariffs, solar, and battery constraints across enrolled systems | **Roadmap** |
| Robotics | Request a high-level tabletop pick-and-place task while a validated local controller retains realtime authority | **Roadmap** |

These labels are not maturity grades. **Implemented** means the contract or code path exists. **Fake/simulation-tested** proves deterministic software behavior, not physical safety. **Live read-only** proves observation against a real target without mutation. **Roadmap** is vision, not an available feature.

The powerful part is not that these worlds pretend to be identical. Each plugin keeps its own entities, units, limits, controller, and effect oracle, while one Heart supplies the durable goal cycle, replaceable cognition, authority boundary, recovery, and audit trail. A new world should add domain semantics without creating a second Engine.

See [five plugin and application examples](docs-site/docs/concepts/end-goal.md#five-plugin-and-application-examples) for the worked-through versions, and [Status and evidence](docs-site/docs/reference/status-and-evidence.md) for the full claim matrix and oracle limits.

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

The optional `engine.ntfy` plugin publishes a deliberately narrow set of
durable lifecycle milestones: a GoalSpec was added, a learning or routine
candidate was created or promoted, a RoutineSpec was added or activated, or a
model-backed brain produced a real `ProposedAction`. Raw Homey motion, light,
sensor, lux, power, snapshot, and behavior-signal events are never forwarded to
ntfy. Delivery is best-effort and non-authoritative; notifier failure cannot
affect observation, policy, authorization, execution, or effect verification.

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
plugins/                  Reference world, context, Homey, and ntfy plugins
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
