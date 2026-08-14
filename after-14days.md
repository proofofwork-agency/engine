# Engine 0.2 after M4: the road from open eyes to earned hands

This is the continuation handoff for whoever picks Engine 0.2 up once the
fourteen-day M4 observation window closes. It is written for an agent or a
human starting cold. Read it together with [`GOAL-0.2.md`](GOAL-0.2.md),
[`AGENTS.md`](AGENTS.md), [`RULES.md`](RULES.md) and the accepted ADRs. The
stricter source wins wherever these documents disagree.

Everything below is **planned work, not implemented work**. Nothing here may
be described as measured, proven or done until its own gate has actually run.

For the window itself and how to start it, see [`14days.md`](14days.md).

## 0. Start here: did M4 actually close?

M4 is closed only when the fourteen days have elapsed **and** the criteria in
`GOAL-0.2.md` have been evaluated in writing: continuity across restarts and
sleep gaps, durable behavior and manual-override signals, and storage growth
inside the frozen budget as clarified by ADR-0011 Amendment 1.

- **M4 passed.** Record the evidence under `artifacts/evidence/M4/`, then
  start Phase B below.
- **M4 failed.** Record the failure with the same care as a pass. Do not move
  the budget, do not extend the window to make the numbers work, and do not
  quietly restart the clock. Decide explicitly between narrowing the claim,
  fixing the cause and running a *new* window, or stopping. `RULES.md`
  MUST NOT 22 and 25 both apply here.
- **The window was interrupted.** A soak that lost days to a dead daemon or an
  unexplained gap is not a fourteen-day soak. Say so, fix the cause, start a
  new window with a new start timestamp, and never backdate.

Phase B development may begin while M4 is still running. The EXP-2026-004
scored window may not: it starts only after the B3 freeze.

## 1. Phase B — judgment: shadow scoring and EXP-2026-004 (→ M5)

The question: can the organism's shadow decisions match real household
behavior well enough to be worth trusting later? Nothing in Phase B dispatches
anything; `OBSERVE` mode holds throughout.

### B0 — close the override-visibility holes

The scorer can only be honest if the runtime can see a human overriding it.

- `plugins/engine-homey/src/engine_homey/target.py`, `_controlled_changes`
  (currently line 682): detect actuator capabilities (`onoff`, `dim`,
  `target_temperature`, `windowcoverings_set`) regardless of the write
  allowlist. This is detection only — do not touch `execute` gating, and leave
  engine-dispatch suppression exactly as it is.
- `plugins/engine-homey/src/engine_homey/v2.py`: the experience provider must
  also emit zone on/off signals, not only lights and brightness.

*Gate:* existing Homey suites stay green; new tests prove an override is
visible for each actuator family.

### B1 — the shadow outcome scorer

- New `AutonomyShadowOutcomeV1` mirroring `RoutineShadowEventV1`
  (`packages/engine-sdk/src/engine_sdk/models.py:601`), and a new
  `autonomy_shadow_outcomes_v1` table with `UNIQUE(enrollment_id,
  opportunity_key)`, shaped like `routine_shadow_events_v1`
  (`src/engine/world_store.py:279`).
- New plugin-neutral `src/engine/autonomy_shadow.py`, called from `run_cycle`
  after `autonomy.evaluate_cycle` (`src/engine/autonomy_v3.py:52`) and inside
  the A4 isolation boundary, so a scorer fault can never kill the daemon.
- Opportunity key: a hash of enrollment, entity, canonical parameters and a
  30-minute bucket, so fingerprint-gated re-evaluations deduplicate.
- Closure by timestamps, not by wall-clock waiting, so sleep gaps cannot
  corrupt it: predicted state observed inside window `W` is agreement, window
  expiry is disagreement, an opposing change or override is strict
  disagreement. Assert `dispatch_count == 0` on every outcome.
- Follow the `RoutineLearnerV1.advance` pattern
  (`src/engine/routines_v1.py:519`).

**Trap, and it is load-bearing.** ADR-0011 Decision 6 promises that snapshots
referenced by an *unscored shadow outcome* are never pruned. That pin does not
exist in code yet — `WorldStore.retention_pinned_snapshot_ids` currently pins
only open dispatch attempts and pending approvals, because the shadow-outcome
table does not exist. B1 must extend it in the same commit that creates the
table. Ship the table without the pin and retention will silently delete the
snapshots M5's evidence rests on, and the loss will not be visible until
scoring runs.

*Gate:* new scorer tests including a sleep-gap case; full suite green.

### B2 — baselines and report

Three comparators under equal budgets: always-defer, an hour-of-week schedule
mimic over a trailing seven days (deterministic — this is the primary
comparator), and persistence. Add `engine autonomy shadow-report` emitting
counts and rates only; thresholds live in the protocol, never in the code.

*Gate:* byte-reproducible output on a fixed store fixture.

### B3 — freeze the protocol (owner signature required)

Write `artifacts/experiments/EXP-2026-004-shadow-lighting/protocol.md` from the
EXP-2026-003 template: claim and null as a disjunction, frozen implementations
and budgets, a seal block with the frozen commit and fingerprints, consumption
rules, and the design-failure clause.

Frozen numbers, which came from the plan and must not drift: `W = 45 minutes`;
at least three zone enrollments in `OBSERVE`; the claim is agreement `≥ 60%`
absolute **and** `≥` best baseline `+ 10` points **and** strict
false-intervention `≤ 10%`, over at least 50 closed opportunities across at
least 10 days. Burn-in data is excluded. Fewer than 50 opportunities in
fourteen days is a **sampling design failure**, which means a new experiment
id and an honest rescope — not a lowered threshold.

*Gate:* owner signs the seal before any scored data exists.

### B4 — the scored window, then decide

Run it once. Consume it once. Record go or an honest no-go in `decision.md`
either way. A negative result is a result; EXP-2026-003 is the precedent and
its no-go stands.

An Engine Cell is considered **only** if M5 exposes a preregistered deficit
that a bounded specialist could plausibly close, and then only as a new
experiment with a new held-out set. EXP-2026-003 may never be reused as
training or tuning data.

## 2. Phase C — the cross-body brain (→ M6)

The question: can an action in one body be justified by typed, durable
evidence from another, without cross-plugin mutation and without evidence
degenerating into prompt glue?

### C1 — sun in `engine.context`

A pure-function NOAA solar elevation module in
`plugins/engine-context/src/engine_context/`, emitting `DERIVED` observations
`sun.elevation_deg`, `sun.above_horizon` and `sun.phase`
(day/civil_twilight/night), falling back to `UNKNOWN` without coordinates.
Update the manifest's observation types. No new dependency: this is roughly
forty lines of arithmetic.

*Gate:* within `±0.5°` of ephemeris fixtures.

### C2 — quotas, freshness and privacy derivation (the core slice)

In `autonomy_v3._context` (`src/engine/autonomy_v3.py:616`), replace global
truncation with per-source budgets: own entities exact, foreign sources capped
at 16 entities and 32 observations in deterministic order with per-source
truncation flags. This fixes the verified vanishing-evidence bug where a
128-observation cap silently dropped context evidence.

`STALE` foreign observations stay in the projection but lose evidence
eligibility — visible, not deleted.

Privacy derivation closes a verified audit HIGH: optional
`[[observation_privacy]]` manifest declarations map property to class, and
anything undeclared inherits the provider capability's `privacy_class`,
failing closed. `engine.context` declares `time.*` public, `sun.*` and
`weather.*` local, `location.*` sensitive. `_context` then filters foreign
observations to granted classes, so a `local` grant can never expose latitude.
Add an enroll-time required-grant check, and close the unchecked
`request.goal_id` while you are in this file.

*Gate:* the full autonomy suite green, plus explicit tests that latitude never
leaks and that context survives a 442-observation projection.

### C3 — `EvidenceRefV1` and provenance validation

Freeze `EvidenceRefV1` in the SDK. In `_validate_proposal`
(`src/engine/autonomy_v3.py:545`), resolve every `evidence_ids` entry inside
the evaluation's own projection: grade must be `OBSERVED` or `DERIVED`, within
source freshness, source within enrollment plus context plugins, and for
context-declaring strategies at least one own-plugin reference **and** at
least one context reference. Anything unresolvable or stale defers the
binding. Persist resolved references in the binding body for audit.

M6 uses `cognition_route="deterministic"`. The executive-model route is a
declared stretch: `DeterministicExecutiveBrainV2` cannot serve autonomy
projections and no shipped specialist implements `advise_autonomy`.

*Gate:* fabricated or stale evidence can never dispatch, in any mode.

### C4 — a context-reading Homey strategy, in simulation

`HomeyContextLightingStrategyV1` (`homey.context-lighting-state/v1`) reads its
own zone `lighting.any_on` and presence plus foreign `sun.above_horizon` and
`sun.phase`, reusing the existing template so the compiler stays untouched.
Manifest entry declares `context_plugin_ids=["engine.context"]` and
`privacy_classes=["local","public"]`. A new cross-body lifecycle test drives
the real `engine.context` plugin on a fixed clock plus a fake-transport Homey
through the full lifecycle.

*Gate:* five of five simulated loops including one injected no-effect run;
zero brain calls; no plugin ids leaking into core.

### C5 — the first live cross-body decision = M6

Only after D1. Enroll one real zone, observe for at least three days as an
exploratory annex, then approve exactly one real proposal under `SUPERVISED`
through to a verified effect. `ENGINE_HOMEY_MODE=act` and `ARMED=1` for that
session only. Archive the evidence under `artifacts/evidence/M6/`.

## 3. Phase D — earned hands: hardening and the physical gate (→ M7)

Nothing in this phase happens without the owner physically present.

### D1 — authority hardening (ADR-0013, before any live act)

- Transactional admission: `BEGIN IMMEDIATE` around the final gates and the
  `PREPARED` write in `src/engine/world_heart.py` (the attempt is written
  around line 1617). Semantics to state explicitly: a mode change invalidates
  future admissions and never recalls in-flight I/O.
- CLI `autonomy mode` and `autonomy disable`
  (`packages/engine-runtime/src/engine_runtime/cli.py:225`) become audited and
  serialized with that transaction.
- Reject non-empty `budget` and unenforced limit keys at enroll time rather
  than accepting something the runtime cannot honor.
- A `CLOSED_UNKNOWN` closure path, automatic after a one-hour horizon plus
  `engine autonomy attempts list|close`, so an ambiguous attempt cannot
  deadlock a zone for weeks.
- An explicit enrollment-owns-resource conflict rule, with a cross-concern
  test proving a live goal and an enrollment on one zone resolve to a single
  deterministic owner.

*Gate:* all hardening tests green, extending the existing crash and lease
patterns.

### D2 — the physical gate

Per `plugins/engine-homey/DEPLOYMENT.md`: one zone with a lamp, an independent
lux sensor and power measurement, with competing Homey Flows disabled. Five
`SUPERVISED` closed loops, one of them with a physically injected no-effect
disturbance — an acknowledgement without a sensor change must record as a
failure, which is the entire point. Zero brain calls while stable, collateral
zones unchanged in all five, per-loop evidence recorded, instrumentation
read-only.

*Gate:* five of five. Four of five is a failure, not a near-pass.

### D3 — delegated soak = M7 seal

Seven days `DELEGATED` for the proven zone and that zone only. Every dispatch
receipted and oracle-verified. Outbound notifications stay milestone and
count-only. Rollback is `engine yolo disable` plus un-arming. Then evaluate the
`GOAL-0.2.md` criteria table and either seal 0.2 or record an honest failure
with cuts.

## 4. Standing rules, several of them learned the hard way

- **Verify against the real thing.** The A2 reconstruction check ran against
  all 30,123 archived snapshots. The compression ratio was confirmed against
  284 real production rows, not a benchmark. Fixtures prove code; production
  data proves claims.
- **Never relay a peer's verdict as your own.** Both agents reviewed A5
  independently and each found a defect the other missed. An accepted claim
  that was not independently checked is a claim, not a verification.
- **Disprove your own finding before shipping it.** Two dramatic hypotheses
  died this way: relation timestamps leaking into the fingerprint, and a
  malformed-wake poison row. Both were wrong, and saying so cost nothing.
- **A gate never moves after data.** Clarify scope before a run, in writing,
  and only in the stricter direction. If a number cannot be met, that is a
  recorded failure, not a new number.
- **Storage growth is measured across every store the runtime writes**, main
  file plus write-ahead log, per ADR-0011 Amendment 1. The Engine store is not
  the whole picture; that mistake cost a fourteen-day window once already.
- **Latent traps we know about and chose not to fix yet.** `schedule_wake`
  does not validate its timestamp, and `HomeOpsStore.prune_snapshots` parses
  `observed_at` from every row inside its transaction — a malformed value
  would abort every future prune. Both are harmless while their callers are
  controlled. Fix them the moment either becomes reachable from untrusted or
  automatic input.
- **ADRs 0011 Amendment 1, 0012 and 0013 are accepted.** Homey plugin
  retention (H2) keeps only the newest snapshot. EXP-2026-004 is parked
  unsealed until someone wants the M5 exam.
