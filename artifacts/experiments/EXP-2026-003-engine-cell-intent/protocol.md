# EXP-2026-003 — bounded Engine Cell intent routing

Status: preregistered, not consumed. Frozen on 2026-08-11. Negative results,
partial runs, and failed gates must be retained.

## Decision under test

The first Engine Cell candidate is a reference-world specialist for one bounded
task: classify a short English or Dutch operator utterance as the installed
`warehouse.reserve-minimum/v1` goal-template identifier or `DEFER`.

The Cell is not an intent-to-action agent. Its only integration output is a
non-operational `SuggestionV1`. It receives no executor, policy, authorization,
store, plugin registry, network, or tool handle. It cannot create a `GoalSpec`,
`GoalCandidateV1`, `ProposedAction`, request, mandate, or dispatch. The existing
Heart remains the only lifecycle owner.

## Claim and null

Claim: under the same 512-byte input limit and local CPU budget, one frozen
int8 MLP improves macro-F1 by at least `0.03` over both a conservative typed
rule baseline and a word-unigram bag-of-words baseline on the sealed held-out
set, separately for English and Dutch, while preserving out-of-domain `DEFER`
recall of at least `0.95` and staying inside its resource envelope.

Null: the best baseline reaches macro-F1 `>= 0.90` in either language, the Cell
margin is below `0.03` in either language, `DEFER` recall is below `0.95`, or a
resource/safety gate fails. Under the null, no model artifact or Cell adapter is
registered in the plugin. The negative result remains evidence.

This experiment supports only the repository-authored paraphrase grammar. It
does not establish open-domain intent understanding, physical safety, correct
parameter extraction, or permission to execute a template.

## Frozen implementations and budgets

- deterministic baseline: conservative language-specific action/entity tokens,
  a decimal count in `[1, 10]`, and explicit rejection of negation, query,
  simulation, cancellation, removal, disablement, and other-target markers;
- classical baseline: Laplace-smoothed word-unigram multinomial naive Bayes;
- Cell candidate: the same deterministic unsupported-scope marker gate as the
  conservative baseline, followed by stable hashed word unigrams/bigrams plus
  character 3-5 grams, a 16-unit `tanh` hidden layer, deterministic SGD seed
  `20260811`, then symmetric per-layer int8 quantization;
- training epochs: 240; learning rate: 0.04; L2: 0.0001; positive-class
  training weight: 2.0;
- the confidence threshold is selected once from
  `[0.50, 0.55, ..., 0.90]` using only the development set, maximizing the
  minimum language macro-F1 subject to development `DEFER` recall `>= 0.95`;
- each implementation gets the same UTF-8 utterance and language tag, a maximum
  of 512 input bytes, one local CPU thread, no network, and no external model;
- runtime limits: artifact `<= 131072` bytes, p95 latency `<= 5 ms` on the
  recorded host, and peak traced inference allocation `<= 8 MiB`.

No architecture, feature family, baseline, threshold grid, metric, or gate may
change after the first held-out consumption.

## Data and provenance

All examples are authored for this repository and licensed CC0-1.0. No user,
production, private, model-generated, or externally downloaded data is used.
Each semantic paraphrase family has a stable `group_id`; English and Dutch
counterparts of one family always remain in the same split.

- `data/train.jsonl`: weight fitting only;
- `data/dev.jsonl`: frozen threshold selection and allowed pre-consumption
  diagnosis only;
- `data/heldout.jsonl`: sealed final evaluation, consumed exactly once.

The held-out SHA-256 and frozen source commit are recorded below before the
first consumption:

```text
heldout_sha256 = e9a92f500cb40db16a92e0ba85fbf7bcd0e4656b39f00ffe735c7e4a0ee3a5ed
frozen_source_commit = b3274d0794791f27dc479a7f6401f39974fb5c68
```

Splits are audited for duplicate normalized text, duplicate group identifiers,
language/class balance, valid labels, and cross-split group leakage before any
training. The evaluator refuses a held-out run unless the file hash matches the
frozen value supplied on the command line.

## Metrics and gates

For English and Dutch separately, record:

- accuracy and macro-F1;
- template precision and recall;
- `DEFER` precision and recall;
- confusion counts for both baselines and the Cell;
- Cell improvement over the better baseline.

Also record model bytes, input limit, p50/p95/max inference latency,
`tracemalloc` peak allocation, Python/platform identity, source commit, dataset
hashes, model hash, training configuration hash, and the exact consumption
timestamp.

Release of this Cell candidate requires every gate:

1. best baseline macro-F1 `< 0.90` in both languages;
2. Cell macro-F1 improvement `>= 0.03` in both languages;
3. Cell `DEFER` recall `>= 0.95` in both languages;
4. Cell template precision `>= 0.90` in both languages;
5. all resource limits pass;
6. a shadow integration test produces a durable `SuggestionV1` and exactly
   zero goals, proposals, authorizations, attempts, or executor calls;
7. malformed, oversized, unknown-language, low-confidence, missing-artifact,
   and artifact-hash-mismatch inputs deterministically defer.

## Consumption and remediation

Training and development evaluation may be repeated without changing the
frozen design. The held-out set may be consumed once. The first complete output
is canonical even if it fails. After consumption, fixes may only correct an
evaluator bug that invalidates the run; the invalid run is retained and a new
owner-approved experiment identifier is required.

## Stop and abort conditions

Stop without shipping the Cell if any null condition or safety gate holds.
Abort and retain the run on split leakage, hash mismatch, unequal budgets,
unrecorded manual intervention, nondeterministic model bytes, metric-code
failure, or inability to reconstruct the result from saved artifacts.

Any path from Cell output directly to `GoalSpec`, `GoalCandidateV1`,
`ProposedAction`, policy, authorization, dispatch, or effect verification is a
design failure, not an experiment failure to be tuned away.
