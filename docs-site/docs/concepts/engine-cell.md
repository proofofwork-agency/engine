---
title: Engine Cell
description: The evidence gate for a future bounded local specialist and the first honest no-go.
sidebar_position: 8
---

# Engine Cell

An Engine Cell is a possible local implementation of one bounded specialist
skill. It is not another Heart, general executive, scheduler, model-owned state
store, permission system, tool user, or effect oracle. Being local, small or
learned grants it no authority.

## Current status: no Cell is registered

The first candidate was evaluated after generic plugin autonomy in
EXP-2026-003. It classified repository-authored English and Dutch warehouse
utterances into one installed goal-template identifier or `DEFER`. The candidate
used a deterministic unsupported-scope gate followed by a 16-unit quantized
MLP. Its allowed output was a non-operational `SuggestionV1` only.

The held-out result was a **no-go**:

| Macro-F1 | English | Dutch |
| --- | ---: | ---: |
| Best deterministic/classical baseline | 0.6875 | 0.8989899 |
| Cell | 0.8989899 | 0.8989899 |
| Improvement | +0.2114899 | 0.0 |

The frozen gate required at least `+0.03` in each language. Dutch tied the
classical baseline, so Engine did not register the adapter or package the model
with the reference-world plugin. `DEFER` recall, template precision and the
resource envelope all passed; they do not override the failed comparative gate.

The complete negative result is retained in
[EXP-2026-003](https://github.com/proofofwork-agency/engine/tree/main/artifacts/experiments/EXP-2026-003-engine-cell-intent)
and the decision is recorded in
[ADR-0010](https://github.com/proofofwork-agency/engine/blob/main/docs/adr/ADR-0010-first-engine-cell-candidate.md).

## Permanent integration boundary

If a later Cell earns deployment, the shape remains:

```text
bounded typed projection
        -> local specialist runner
        -> INFERRED advice / non-operational suggestion
        -> Heart-owned validation and lifecycle, if separately authorized
```

The Cell never receives executor, authorization, policy, registry or direct tool
handles. It never declares an effect observed. A future actionable proposal
would still require the normal observe → validate → policy → authorize →
dispatch → observe → oracle sequence.

## What is required next

A second attempt needs a newly measured task-level deficit, a new experiment
identifier and held-out set, exact provenance, deterministic and classical
baselines, equal budgets, resource limits, defer behavior, rollback and an
authority-free shadow. The consumed EXP-2026-003 set cannot be used to tune the
next claim.
