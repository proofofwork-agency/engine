# Engine 0.1 — research findings and implementation choices

> This note supports the owner-defined Engine. It does not replace or narrow
> `GOAL.md`. Filesystem and grid are falsification fixtures, not the boundary of
> Engine's intended worlds.

## Finding 1 — the Heart is a real architectural object

Engine now separates a durable decision cycle from the model session: goal and
snapshot → bounded cognition context → executive choice → specialist or world
capability → observed result → durable experience → next cycle. This resembles
the state/operator cycle in the established [Soar architecture](https://soar.eecs.umich.edu/soar_manual/02_TheSoarArchitecture/)
and the memory/action/decision decomposition in
[CoALA](https://arxiv.org/abs/2309.02427), while keeping Engine's own identity:
one living Heart owns continuity and brains are replaceable organs.

The implementation is not merely a ReAct transcript. ReAct establishes the
value of interleaving reasoning, action and environment feedback
([paper](https://arxiv.org/abs/2210.03629)); Engine additionally makes goal,
world state, brain requests, invocations and receipts reconstructible outside
the model context.

## Finding 1b — restart is recovery; life is maintain → monitor → react

The original proof emphasized process restart because it cleanly falsified
prompt-owned state. That is a fault test, not Engine's operating model. Engine
now distinguishes one-shot `ACHIEVE` goals from continuing `MAINTAIN` goals.
A maintained goal whose target oracle is true remains in quiet `monitoring`.
Target events or polling wake Heart; Engine observes authoritative state again,
and only observed drift reactivates cognition. Stable observations invoke no
general or specialist brain.

Noisy targets may expose a goal-scoped relevance filter: the full versioned
snapshot is still recorded, but unrelated telemetry cannot repeatedly wake a
waiting/degraded goal. Oracle errors enter `uncertain` and block action until an
exact boolean returns. Model/provider errors are separately governed by durable
exponential backoff and a degraded circuit state.

This preserves the realtime boundary: Engine is always-on and event-driven at
the deliberative level, while stabilization and other hard-realtime loops remain
inside target controllers. `WAIT` likewise sleeps until the observation changes
instead of consuming model calls. The decision and migration are recorded in
`docs/adr/ADR-0001-live-heart-goal-lifecycle.md`.

## Finding 2 — multiple brains are plausible, but “more” is not automatically better

[HuggingGPT](https://arxiv.org/abs/2303.17580) demonstrates a controller selecting
and executing specialist models. Routing research such as
[RouteLLM](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5503a7c69d48a2f86fc00b3dc09de686-Abstract-Conference.html)
shows that quality/cost-aware model choice can pay off in evaluated settings.
These support the topology, not a claim that Engine's current multi-brain path is
superior.

Engine's live Qwen run exposed a useful failure: the model could state in its
rationale that advice was ready yet emit another consult operator. A larger
prompt did not solve the semantic protocol. The Heart now projects a typed phase,
the provider schema narrows the allowed operator set, and Heart independently
rejects stale or redundant choices. The executive still chooses the world action;
there is no hidden auto-execution.

On the consumed FS/grid runs, this reduced prompt tokens by 61.46% and 35.15%
respectively (47.13% combined) while retaining both oracles and the grid
partial-failure/restart path. This is evidence of protocol efficiency in those
two runs, not a general reasoning or multi-brain result. Raw summaries are in
`artifacts/evidence/live-llm-baseline.json` and
`artifacts/evidence/live-llm-typed-phases.json`.

The later C0/C1/C2 pilot is intentionally `INCONCLUSIVE` as a controlled
comparison. C0 and C1 did not close the grid oracle within 40 attempts; C2 did in
18 executive attempts and 9 invocations, but C0 still suffered three
token-context/output failures and C2 adds both deterministic specialist
competence and orchestration. This is a concrete need-signal for the navigation
organ on this fixture, not multi-brain superiority. See
`artifacts/experiments/EXP-2026-001-pilot/runs/20260810T010432Z/INTERPRETATION.md`.

## Finding 3 — the plugin seam is coherent, but it is an alpha kernel

The native catalog now has qualified/versioned plugin, brain and capability
identities; explicit target binding IDs plus adapter/contract versions; real JSON
Schemas; capability refresh on already registered targets; explicit retrieval
evidence; invocation modes; and durable catalog fingerprints. Python entry
points are reserved as discovery transport, consistent with the
[PyPA plugin guidance](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/).
That path has not yet been proven with a separately installed package.

The capability contract deliberately borrows proven distinctions rather than
pretending every domain is identical:

- W3C WoT distinguishes properties, actions and events and describes typed data
  affordances ([Thing Description 2.0](https://www.w3.org/TR/wot-thing-description-2.0/)).
- ROS 2 separates streams, short request/response and long-running actions with
  feedback/cancellation ([ROS 2 interfaces](https://docs.ros.org/en/ros2_documentation/rolling/Concepts/Basic/Interfaces-Topics-Services-Actions.html)).
- MAVLink commands explicitly include acknowledgement, in-progress feedback,
  final result and cancellation ([command protocol](https://mavlink.io/en/services/command.html)).
- WebDriver BiDi is asynchronous and event-oriented
  ([specification](https://www.w3.org/TR/webdriver-bidi/)).

Therefore the current Heart executes only `IMMEDIATE` calls and rejects TASK or
STREAM before dispatch. That is honest incompleteness. A mature universal plugin
system still needs a durable `ActionRequest` (invocation ID, snapshot
precondition, deadline and idempotency key), task/stream/cancel lifecycle,
provider/session discovery and configuration, observation schemas, artifact
references and reusable third-party conformance tests.

## Finding 4 — capability retrieval must be visible and measured

Large tool universes cannot simply be dumped into every prompt. ToolRet reports
that tool retrieval over tens of thousands of heterogeneous tools remains hard
and that retrieval quality affects end-to-end pass rate
([ACL Findings 2025](https://aclanthology.org/2025.findings-acl.1258/)). T-Eval
separates tool use into instruction following, planning, reasoning, retrieval,
understanding and review
([ACL 2024](https://aclanthology.org/2024.acl-long.515/)).

Engine therefore persists the catalog generation, candidate universe, shortlist,
selector identity, score/reason, completeness and omitted count. The current
lexical selector fails closed when a zero-score truncated result would otherwise
silently hide tools. It is a transparent baseline, not a claim that lexical
matching will scale.

## Finding 5 — mini-brains are a measured growth path

Tool use and compact task models are trainable in bounded settings:
[Toolformer](https://proceedings.neurips.cc/paper/2023/hash/d842425e4bf79ba039352da0f658a906-Abstract-Conference.html)
and [GPT4Tools](https://proceedings.neurips.cc/paper_files/paper/2023/hash/e393677793767624f2821cec8bdd02f1-Abstract-Conference.html)
train tool-use behavior, while
[Distilling Step-by-Step](https://aclanthology.org/2023.findings-acl.507/) shows
that rationale-assisted distillation can produce strong smaller task models in
its evaluated domains. None proves automatic universal mini-brains.

The highest-value first learned organ is likely a router/ranker, not another
general LLM. Engine's sequence is: deterministic specialist → outcome history →
transparent router → offline shadow dataset → simple classifier baseline → only
then small fine-tune/LoRA → held-out target profiles and rollback. Ground truth
comes from observed effects and final-state oracles.

## Finding 6 — the next target should falsify both plugin and live-Heart layers

The two 0.1 worlds prove the living loop but do not prove an installable
ecosystem. Seven parallel research lanes compared browser/casework, operations,
AppWorld/LifeOps, Home Assistant and embodied candidates. Their useful split is:

- **flagship:** bounded HomeOps on a local Home Assistant demo/low-risk light
  setup, because a desired physical state makes continuous Heart, event wake,
  independent sensor truth and specialist substitution immediately legible;
- **scientific benchmark:** LifeOps on AppWorld, because its state-based task and
  collateral-damage evaluators make cross-app results reproducible;
- **technical fallback/first contract slice:** Verified App Doctor, because a
  local unhealthy service is quick to package and has strong black-box oracles.

The GLM Order Desk proposal remains a useful HTTP adapter/conformance fixture,
but it is not the flagship: a one-shot shop transaction makes Engine look like a
restartable workflow and can be closely imitated by existing tool agents.

Whichever plugin lands first must be separately installed through
`engine.plugins`, add no branch to `Heart`, and pass the same malformed-result,
wrong-target, lost-ack, same-revision, catalog-refresh and oracle conformance
tests. HomeOps begins only with whitelisted demo lights/switches and read-only
lux/power sensors; no locks, climate, cameras or broad physical autonomy.

After that, desktop and device bridges can follow. Drone/vehicle/robot adapters
remain in Engine's intended scope, but LLM deliberation must select high-level
capabilities while flight stabilization, steering and other hard-realtime loops
stay in target-native controllers. That preserves the concept rather than
reducing Engine to either a chat harness or raw actuator model.

## Competitive reading

`threath.md` remains useful: OpenClaw/Hermes validate demand for persistent local
agent runtimes and reusable skills. Engine loses if it becomes a late clone of a
chat/session gateway. Its differentiating claim is the one now exercised by
`GOAL.md`: durable world state, one Heart, general plus specialist cognition, and
heterogeneous world action with effect truth independent of model self-report.
