# EXP-2026-003 decision — no-go

The sealed held-out run was consumed once on 2026-08-11 from frozen source
commit `b3274d0794791f27dc479a7f6401f39974fb5c68`. The canonical result is
`heldout-result.json`.

## Decision

Do not register or ship the warehouse intent Cell, its model artifact, or its
specialist adapter. Keep Engine on the existing deterministic and classical
paths for this task.

The English result cleared the quality gates. The Dutch result did not: the
int8 Cell and the word-unigram baseline both reached macro-F1 `0.8989899`, so
the preregistered improvement gate of `>= 0.03` failed. Pooling the languages,
lowering the margin, moving the baseline ceiling, or debugging against the
consumed held-out examples is forbidden.

| Held-out metric | English | Dutch |
| --- | ---: | ---: |
| best baseline macro-F1 | 0.6875 | 0.8989899 |
| Cell macro-F1 | 0.8989899 | 0.8989899 |
| Cell improvement | 0.2114899 | 0.0 |
| Cell template precision | 1.0 | 1.0 |
| Cell `DEFER` recall | 1.0 | 1.0 |

The resource envelope passed: the artifact was 21,387 bytes, p95 inference was
1.408 ms over 1,600 local samples, and peak traced inference allocation was
86,326 bytes on the recorded Apple arm64 host. Passing resource and safety
gates does not compensate for a failed comparative-quality gate.

## Retained evidence

- `protocol.md`: immutable claim, null, split and stop conditions;
- `development-attempt-01.json` and `development-attempt-02.json`: failed
  development configurations retained rather than overwritten;
- `development-attempt-03.json`: final pre-freeze development result;
- `model.json`: exact rejected candidate artifact, retained only with the
  experiment and not installed by a plugin;
- `heldout-result.json`: canonical consumed result;
- `tools/cell_candidate.py` and `tools/run_cell_experiment.py`: reconstructible
  experimental runner and harness. The exact consumed implementation remains
  available at the frozen commit even if later tooling evolves.

A future Cell requires a new task claim, experiment identifier, unconsumed
held-out set, and owner-approved preregistration. EXP-2026-003 cannot be reused
as a tuning set.
