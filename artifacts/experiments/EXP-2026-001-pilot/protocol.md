# EXP-2026-001 — exploratory cognition conditions

Status: `PREFLIGHTED/CONSUMED`, exploratory only. This protocol records what the
current pilot means and freezes the design required before any decisive claim.
It does not redefine the owner milestones M1/M2 in `GOAL.md`; condition labels
are C0/C1/C2.

## Current pilot question

Can the same local executive model traverse the two existing Engine 0.1
fixtures under three context/orchestration conditions, and does the measurement
plumbing preserve enough evidence to design a controlled benchmark?

| Condition | Contract |
| --- | --- |
| C0 bounded monolith | Favorable external harness: fresh authoritative snapshot and GoalSpec each turn, last two model turns, last eight outcomes, direct world tools |
| C1 durable single | Engine Heart and durable state/receipts with the same general model, no specialists |
| C2 Engine multi | C1 plus one deterministic task-solving specialist per world and mandatory specialist-first phases |

C2−C1 is deliberately **not** a clean architecture-only contrast: it combines
specialist competence with Heart-managed orchestration. C0 has no intrinsic
goal/state continuity; the external harness re-supplies those inputs. These
differences are part of the recorded baseline contracts, not hidden assumptions.

## Frozen exploratory instrumentation

- Local model: `ggml-org/Qwen3-4B-GGUF:Q4_K_M`.
- Artifact SHA-256: `ab27b9bfa375a178d6cba48f3ad892b94b7739659dcc7aae8058ce0ffed6b328`.
- Temperature: 0; server seed remains default/unknown.
- Server context: 8192 tokens with 640 requested output tokens requested. A
  consumed four-turn baseline overflowed this window; a later two-turn run still
  produced two context overflows and one truncated answer. Both are retained.
  A decisive C0 requires token-aware oldest-turn eviction with a measured output
  reserve, not a byte limit or fixed turn count.
- Restart boundary: after exactly one terminal world invocation in each grid condition.
- Primary endpoint: independent final-state oracle within the existing condition budget.
- Caller-side `perf_counter` latency is comparable; provider-reported prediction timing is separate.
- Every executive attempt is counted, including failed projection/provider/schema attempts.
- C1/C2 preserve SQLite plus raw event exports; C0 preserves a causal trace.
- Initial/final state hashes exclude `observed_at`.
- Fixed condition order makes latency comparisons uninterpretable.

## Interpretation gate

The current single run per hand-built task may establish only:

- integration works or fails;
- a contract/instrument is missing;
- a concrete task exposes a need for specialist competence;
- event links, restart continuity and metrics are present.

It may not establish general success rates, average savings, multi-brain
superiority, learned routing, or physical-world validity. Negative runs are kept.

## Decisive follow-up (not yet run)

Hypothesis H1: durable Heart state improves recovery across forced process loss
on long-horizon tasks relative to a bounded monolith under equal model/tool
budgets. Null: no improvement.

Hypothesis H2: Heart-managed specialists improve final-oracle success or reduce
model cost on hard tasks relative to durable-single under a competence-matched
baseline. Null: specialists add cost without operational benefit.

Design to seal before execution:

- at least 30 generated filesystem and 30 generated grid instances;
- strata: trivial, long-horizon, hidden failure + forced restart, and toolsets
  with 0/8/32 decoys;
- at least five repeats per instance, paired seeds, counterbalanced condition order;
- sealed layouts and final-state oracles; no debugging against protected cases;
- exact same executive artifact, temperature, action budget, token budget,
  world tools and oracle per paired case;
- a competence-matched condition that separates specialist algorithm value from
  orchestration value;
- primary: final-state oracle success and pass^k;
- secondary: recovery, invalid calls, cycles, tool invocations, tokens, caller
  latency, cost, specialist selection/usefulness;
- paired confidence intervals and McNemar/paired-bootstrap analysis;
- preregistered gates: on trivial cases Engine may be at most 5 percentage points
  worse; on hard restart cases C1 must improve recovery over C0; C2 must improve
  success/recovery or reduce cost over C1, otherwise multi-brain benefit is not shown.

## Mini-brain follow-up

Do not train first. Collect exact hashed BrainRequests, candidate sets, model and
specialist identities, decisions, invocation IDs, observed effects and oracle
outcomes. Compare a transparent score/router and a simple classifier before a
small fine-tune/LoRA. Labels come from independent effects/oracles, never model
rationales alone. Hold out target profiles and retain a rollback to deterministic
routing.
