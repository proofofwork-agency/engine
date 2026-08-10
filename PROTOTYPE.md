# Engine 0.1 implementation status

> Experimental evidence for `GOAL.md`, not a rewrite of Engine and not a
> production, universal-plugin, or physical-safety claim.

## What exists

The shared Engine core owns:

- durable goals, priority/cycle state, working memory, snapshots and experience;
- an autonomous Heart that continues without a human action per cycle;
- an always-on `LiveEngine` driver with target-event wakeups and polling fallback;
- one-shot `ACHIEVE` goals and continuing `MAINTAIN` goals that return to quiet
  monitoring after every verified repair;
- bounded fresh context construction for every brain call;
- interchangeable deterministic and local-LLM general brains;
- first-class specialist brains, targeted queries and snapshot-bound advice;
- one versioned catalog for target, capability, brain and plugin contracts;
- requested/terminal invocation receipts, post-action observation and effect records;
- strict target-owned boolean completion oracles;
- process-restart reconstruction from SQLite plus newly observed target state;
- durable causal IDs from executive request through specialist advice, invocation,
  tool result and brain outcome.

The Heart is target-agnostic. Filesystem and grid semantics occur only in target
adapters and specialists.

Stable maintained goals are observed without calling the general or specialist
brain. Observed drift reactivates cognition; target events only wake the Heart and
are never trusted as world truth. `WAIT` is durable and quiet until observation
changes. This is a live deliberative loop, not a hard-realtime motor/controller
loop. Restart remains secondary recovery evidence, not Engine's operating model.
Adapters can declare which snapshot changes matter to a goal so unrelated sensor
telemetry does not wake cognition. Oracle failure moves a goal to durable
`uncertain` rather than treating missing truth as failure. Brain/provider errors
use persisted exponential backoff and a `degraded` circuit state instead of a hot
retry loop. A background runtime opens its own SQLite connection and cleans up
subscriptions on every exit path.

## Two deliberately heterogeneous fixtures

| Plugin | Unique semantics | Shared Engine path |
| --- | --- | --- |
| sandbox filesystem | directories, files, moves and content hashes | goal → executive → specialist → capability → observation → experience |
| discrete spatial simulator | position, hidden obstacles, pickup and navigation | the same path, Heart and persistence schema |

The grid fixture includes one hidden-obstacle partial effect. Its observed
`known_blocked` state changes the next plan. The demo restarts the process during
the grid goal. Filesystem, browser/API, desktop, robot, drone and vehicle are
intended target classes; the two current worlds prove the 0.1 loop, not its final
scope.

## Brain topology

`RuleExecutiveBrain` is a transparent deterministic routing fixture. It is not a
strong general intelligence: it ranks specialists by capability overlap and a
durable observed-effect heuristic, then consumes typed advice.

`ModelExecutiveBrain` accepts any `StructuredDecisionModel`. The live adapter is
explicitly llama.cpp-compatible and was exercised with local
`ggml-org/Qwen3-4B-GGUF:Q4_K_M`. Goals, state, execution and truth never move into
the provider session.

Typed cognitive phases constrain the valid operator set. When advice is ready,
the local model must cite its `brain_request_id` and choose a visible world
capability; it cannot silently reconsult the same specialist. Heart validates
the choice again. The model still decides—Heart does not auto-execute advice.

The consumed before/after live runs retained both final-state oracles and the
grid partial/restart path while prompt tokens fell 61.46% on filesystem and
35.15% on grid (47.13% combined). Those are observed protocol-efficiency changes
on two fixtures, not a general intelligence or superiority claim. Evidence:

- `artifacts/evidence/live-llm-baseline.json`
- `artifacts/evidence/live-llm-typed-phases.json`

## Plugin/tool maturity

Engine has a coherent native alpha kernel, not yet a mature universal plugin
ecosystem.

Present:

- namespaced/versioned plugin, brain and capability identities; explicit target
  binding IDs plus adapter/contract versions; and JSON Schema inputs/outputs;
- capability refresh on already registered targets with canonical order/fingerprint;
- target-scoped specialist projection;
- honest incomplete-retrieval evidence;
- `IMMEDIATE`, `TASK` and `STREAM` vocabulary, with non-immediate dispatch
  explicitly rejected until its lifecycle exists;
- malformed/contradictory adapter results converted to terminal `UNKNOWN` rather
  than leaving an invocation at `REQUESTED`;
- lost acknowledgements, wrong-target observations, revision drift, partial
  results and non-boolean/failed oracles covered by tests.

Still needed before “universal plugin system”:

- a durable `ActionRequest` carrying invocation ID, snapshot precondition,
  deadline and idempotency/retry key;
- task/stream feedback, cancellation and reconciliation;
- provider factories for configuration, sessions, reconnect and target discovery;
- typed observation/state schemas and large artifact references;
- an actual separately installed `engine.plugins` package plus a reusable
  third-party conformance suite;
- catalog search/pagination as a cognition capability for very large toolsets;
- multi-target goals/world views.

The next flagship falsification target is bounded HomeOps on Home Assistant demo
or low-risk light entities, installed separately and added with no `Heart` branch.
AppWorld/LifeOps remains the stronger controlled research benchmark; a local App
Doctor is the technical fallback.

## Run

```bash
uv run python -m unittest discover -s tests -v
uv run python -m engine.demo
uv run python -m engine.live_heart_demo  # maintain -> monitor -> drift -> repair
uv run python -m engine.live_demo   # requires llama.cpp server on loopback
uv run python -m engine.experiment  # exploratory, persists raw artifacts
```

The deterministic suite currently contains 33 tests. `engine.demo` runs both
worlds through the same Heart. The pilot protocol and limitations are recorded
under `artifacts/experiments/EXP-2026-001-pilot/`.

## Explicitly not claimed

- no production daemon supervisor, distributed scheduler or guaranteed event QoS;
- no claim that the deliberative Heart is a hard-realtime device controller;
- no learned mini-brain or general experience learning (only a transparent
  negative-outcome routing heuristic);
- no proof that multiple brains outperform a monolith;
- no implemented TASK/STREAM or production plugin loading/configuration path;
- no remote or physical target evidence;
- no production authority, security, safety or certification conclusion.
