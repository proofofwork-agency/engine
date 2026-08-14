# EXP-2026-004 — shadow lighting competence

Status: drafted, **not sealed**. No scored window may open until the owner
signs the seal block below. Burn-in and M4 observation data are excluded.
Negative results, partial runs, and failed gates must be retained.

This protocol implements `GOAL-0.2.md` §2.2 and `after-14days.md` §B3. It does
not dispatch, authorize, or actuate. `dispatch_count` on every scored outcome
must remain `0`.

## Decision under test

Can Engine's OBSERVE-mode autonomy proposals match later household lighting
behavior well enough to beat equal-budget deterministic baselines, without
moving a gate after seeing the data?

The scorer is Heart-owned and plugin-neutral (`AutonomyShadowScorerV1`). It
opens an opportunity when a strategy proposes an effect or goal candidate, and
closes it from timestamps: agreement if the desired effect is observed inside
window `W`, disagreement if `W` expires, strict disagreement if an opposing
change arrives first.

## Claim and null

Claim, as a conjunction that must all hold on the single consumed window:

- Engine agreement `>= 60%` absolute;
- Engine agreement `>=` best equal-budget baseline `+ 10` percentage points;
- strict false-intervention `<= 10%`;
- at least `50` closed opportunities across at least `10` distinct UTC days;
- at least three zone enrollments in `OBSERVE`;
- every closed outcome has `dispatch_count == 0`.

Null / no-go: any of the above fails. A sampling design failure (fewer than 50
closed opportunities in fourteen calendar days) is also a no-go and requires a
new experiment id plus an honest rescope. Thresholds are not lowered.

The three equal-budget baselines, computed by `engine autonomy shadow-report`
and never encoded as product gates, are:

1. always-defer (status quo at the trigger snapshot);
2. hour-of-week mimic over the trailing seven days (primary comparator);
3. persistence (previous snapshot values).

## Frozen implementations and budgets

- scorer: `src/engine/autonomy_shadow.py` `AutonomyShadowScorerV1`;
- opportunity key: SHA-256 of enrollment, entity, canonical parameters, and a
  30-minute UTC bucket;
- closure window `W = 45 minutes`;
- retention pin: unscored outcomes pin `trigger_snapshot_id` so pruning cannot
  delete M5 evidence;
- report: `engine autonomy shadow-report` emits counts and rates only;
- mode throughout: `OBSERVE`; zero dispatch attempts;
- burn-in and any pre-seal rows are excluded from the scored set.

No threshold, baseline definition, window length, or opportunity-key rule may
change after the owner signs the seal.

## Data and provenance

The scored window uses only the live house OBSERVE stream after the seal
timestamp. It does not use:

- M4 exploratory preflight stores;
- EXP-2026-003 Cell data;
- synthetic, model-generated, or imported household traces.

The seal records the frozen source commit, scorer/report fingerprints, and the
UTC instant after which new outcomes may be scored.

## Metrics and gates

Record, once, from the sealed store:

- closed / open / enrollments / spanned UTC days;
- Engine agreement count, disagreement count, strict-disagreement count, and
  rates;
- the same counts and rates for each of the three baselines;
- `dispatch_count` sum, which must be `0`;
- reconstruction of every pinned trigger snapshot.

Go requires the claim conjunction above. An honest no-go is a valid result and
is recorded in `decision.md` the same way EXP-2026-003 was.

## Consumption and remediation

The scored window is consumed exactly once. The first complete `decision.md` is
canonical even if it fails. After consumption, fixes may only correct an
evaluator bug that invalidates the run; the invalid run is retained and a new
owner-approved experiment identifier is required.

## Stop and abort conditions

Stop without treating the window as M5 evidence if:

- any dispatch attempt is recorded;
- the official M4 clock was never started or the soak is not the declared
  source of the stream;
- an unexplained daemon death or backdated clock is detected;
- sealed burn-in or pre-seal rows are mixed into the scored set;
- a gate is moved after seeing rates.

## Seal

Unsigned. Owner must fill and sign before any scored outcome exists.

```text
owner_signed = no
sealed_at_utc =
frozen_source_commit =
scorer_sha256 =
report_cli_sha256 =
excluded_before_utc =
minimum_zones = 3
W_minutes = 45
opportunity_bucket_minutes = 30
agreement_absolute = 0.60
agreement_margin_over_best_baseline = 0.10
strict_false_intervention_max = 0.10
minimum_closed_opportunities = 50
minimum_days = 10
```
