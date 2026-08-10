# GOAL.md acceptance audit — Engine 0.1

Audit date: 2026-08-10. Scope: the owner-locked Engine 0.1 definition. This is an
implementation audit, not a safety/product-certification claim.

## Result

`IMPLEMENTATION EVIDENCE PASS` for the Engine 0.1 done criteria I1–I5, B1–B4,
W1–W4, H1–H3 and R1–R3. G1–G8 are implemented; only the project owner can close
G9 review. The deterministic proof is the acceptance basis; live-local-LLM
evidence is an additional brain-slot integration result.

## Criterion map

| Criterion | Evidence | Result |
| --- | --- | --- |
| I1 goals survive calls/restart | SQLite goal store; restart test; grid demo closes after Store/Heart reconstruction | PASS |
| I2 world state is durable, not provider memory | versioned snapshots plus independently durable FS/grid target state; provider history is unnecessary | PASS |
| I3 receipts influence later choices | hidden-obstacle observation changes route; negative specialist outcome survives restart and changes next specialist selection; history-cleared control chooses the bad specialist again | PASS |
| I4 Heart continues without human step | `LiveEngine` stays alive, fairly advances active goals, sleeps while stable and wakes through target events or polling; `Heart.run` remains the bounded cognitive worker | PASS |
| I5 executive chooses, Heart invokes/books | durable executive decisions precede specialist/tool requests; Heart owns catalog dispatch, observation and result events | PASS |
| B1 general-brain core slot | deterministic `RuleExecutiveBrain` and live `ModelExecutiveBrain` share the same port | PASS |
| B2 specialist through core | file-structure and two replaceable navigation specialists are catalogued and invoked by Heart | PASS |
| B3 general→specialist→tool→observe→continue | both demo worlds execute the complete chain repeatedly | PASS |
| B4 provenance survives | request/result IDs, parent executive request, advice `based_on`, invocation ID, tool result and brain outcome pass referential-integrity tests | PASS |
| W1 filesystem world | multi-step sandbox layout goal closes on target oracle | PASS |
| W2 discrete simulation | hidden-obstacle/key/navigation goal closes on target oracle | PASS |
| W3 same core contracts | both use `Goal`, `Heart`, `BrainContext`, `Catalog`, `ToolCall/ToolResult`, snapshots, receipts and one SQLite event model | PASS |
| W4 domains stay outside cognition core | `heart.py` contains no filesystem/grid/key/position/capability-name branches; uniqueness is in adapters and specialists | PASS |
| H1 mutation has receipt + post-state/unknown | requested→terminal lifecycle; malformed result/lost ACK become terminal `UNKNOWN`; observations are stored | PASS |
| H2 completion is independent | target oracle must return exact `bool`; non-bool/exception is booked and never completes; premature brain completion is rejected | PASS |
| H3 partial/failure changes loop | grid's blocked move records `PARTIAL`, persists `known_blocked`, then replans successfully | PASS |
| R1 one command runs both worlds | `uv run python -m engine.demo` | PASS |
| R2 shared-vs-unique note | `PROTOTYPE.md` and `RESEARCH_FINDINGS.md` | PASS |
| R3 owner-visible run | `engine.demo` + recorded deterministic evidence show autonomous goal-in→oracle-out; the LAN site visualizes those records and architecture but does not run Engine | PASS |

## Reproduced acceptance evidence

- `uv run python -m unittest discover -s tests -v` → 33/33 pass.
- `uv run python -m compileall -q src tests` → pass.
- `uv run python -m engine.demo` → filesystem completed in 7 cycles; grid
  completed in 17 cycles after a process restart and one observed partial effect.
- `uv run python -m engine.live_heart_demo` → a maintained grid goal reaches its
  oracle, stays in `monitoring`, observes externally injected drift, repairs it
  without human input, and returns to `monitoring`; no completion event is used.
- `artifacts/evidence/deterministic-demo.json` → stable summary of both oracles.
- `artifacts/evidence/live-llm-typed-phases.json` → actual local Qwen general
  brain traverses Heart→specialist→tool in both worlds and closes both oracles.

## Why this is more than dispatch/logging

The shared layer chooses the next active goal, builds a target-scoped and
budgeted cognition phase, invokes and records brain organs, rejects stale or
semantically invalid advice, routes future specialist choices using durable
observed-effect history, owns invocation lifecycle, observes/reconciles target
state, and alone accepts the completion oracle. Replacing it with a logger would
remove the behavior that closes the goals and survives restart.

## Boundaries after PASS

The following are real next work, but were explicitly not required by `GOAL.md`
0.1: production daemon supervision/event QoS, multi-target goals, installed
third-party plugins, durable ActionRequest/idempotency, TASK/STREAM/cancel, learned
mini-brains, physical targets and production safety/authority layers. The plugin
system is an alpha kernel; `PASS` must not be expanded into “universal mature
system” or physical-control evidence.
