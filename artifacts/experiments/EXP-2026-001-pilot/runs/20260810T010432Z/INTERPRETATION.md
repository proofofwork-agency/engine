# INCONCLUSIVE as a controlled C0/C1/C2 comparison

Evidence lifecycle: `CONSUMED → INTERPRETED`. Environment: filesystem is a
bounded sandbox target; grid is simulation. This is one fixed-order run per
hand-built fixture and supports no statistical inference or latency comparison.

## Observed outcomes

| Condition | Filesystem | Grid |
| --- | --- | --- |
| C0 bounded monolith | oracle PASS; 6 executive attempts; 6 invocations | oracle not reached; 40 attempts; 37 invocations; 36 partial; 3 provider failures |
| C1 durable single | oracle PASS; 7 attempts/invocations | oracle not reached; 40 valid attempts/invocations; 23 partial and 17 failed results |
| C2 Engine multi | oracle PASS; 8 attempts, 4 specialist calls, 4 invocations | oracle PASS; 18 attempts, 9 specialist calls, 9 invocations; one partial plus process restart |

All grid restart boundaries occurred after exactly one terminal invocation and
reported canonical pre/post continuity. C2's first terminal invocation was the
hidden-obstacle partial; goal, event boundary and state hash survived restart.

## Why the comparison is inconclusive

1. C0 still exceeded llama.cpp's 8192-token context twice and returned one
   length-truncated JSON object despite a two-turn history. The 64 kB byte guard
   does not guarantee token/output reserve. C0-grid is therefore not a clean
   comparator.
2. C2−C1 combines a deterministic BFS/file-structure algorithm with
   Heart-managed orchestration. It is evidence that these organs were useful on
   these tasks, not that multi-brain architecture generally wins.
3. One case per world and fixed condition order provide no success-rate or
   latency inference.

## Defensible findings

- The live local model integration is real in all conditions.
- Durable Heart alone does not make this Qwen model solve the grid fixture; C1
  repeatedly failed against observed world state.
- Heart-managed deterministic specialists closed both fixtures with no provider
  failures, and C2-grid preserved causal/state continuity across a partial and
  process restart.
- A future controlled benchmark needs token-aware C0 truncation, a
  competence-matched baseline, paired generated tasks/seeds and counterbalanced
  order. No further post-outcome remediation was run here.

`prompt_sha256` in `summary.json` covers only the static system prompt. Dynamic
schema family, provider configuration and source are recorded separately; exact
per-call projections and usage are in C1/C2 events and the C0 trace.
