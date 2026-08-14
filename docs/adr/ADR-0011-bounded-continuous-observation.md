# ADR-0011 — Bounded continuous live observation with durable retention

- Status: accepted by explicit owner implementation direction
- Owner: project owner
- Date: 2026-08-11

## Context

Engine 0.2 (GOAL-0.2.md, M4 "Ogen open") requires the Heart to observe the
real Homey house continuously for weeks in `OBSERVE` mode. The daemon path
exists (`engine run` → `WorldHeartV2.run_forever` with a fenced runtime
lease and event-driven wakes), but a measured six-hour live run produced a
13.7 GB store (~2.3 GB/hour): a full multi-target `WorldSnapshotV2` body was
written every cycle, the Homey provider consumed a new provider revision on
every observe so observation dedupe never fired, and the configured poll
interval was parsed but never wired. There is no retention code. One
unhandled exception in a cycle, learner, provider or subscription kills the
process, and lifecycle-observer cursors live only in memory.

Continuous observation retains more behavioral data for longer than any prior
run. That widens the local data boundary, which under `AGENTS.md` §14
requires an ADR. Nothing here changes the action lifecycle, authority
semantics, or the physical evidence boundary of ADR-0008/0009.

## Decision

1. A target observation carries a `semantic_fingerprint` computed from
   values, sources, evidence grades, quality, coverage, units and artifact
   identity — never from timestamps or observation ids. The autonomy world
   fingerprint delegates to the same computation.
2. A provider consumes a new target revision only when the semantic
   fingerprint changes. Re-observing an unchanged world updates a
   `confirmed_at` column on the stored latest observation and writes no new
   row. Freshness and staleness decisions use `confirmed_at` when present.
   The invariant "the same target revision cannot describe different state"
   becomes semantic: same revision with a different fingerprint is an error.
3. Sensor observations are quantized in the plugin provider before
   fingerprinting, with steps frozen here: power `1 W`, illuminance `5 lux`,
   temperature `0.1 °C`, battery `1 %`. Rounding modes follow gate-direction
   conservatism so storage rounding can never weaken a frozen oracle bound:
   illuminance rounds down (floor — a stored value satisfying a lower lux
   bound implies the true value does), power rounds up (ceiling — a stored
   value within a watt budget implies the true value is), temperature and
   battery round half-up (no gated direction). The residual lux
   anti-conservatism at an upper comfort-band edge (at most `4.9 lux`) is
   accepted and documented; oracle-side guard-band comparison is explicitly
   out of scope here. Quantization is target-semantic plugin code, never
   Engine-core code.
4. `poll_interval_seconds` and `freshness_seconds` come from plugin
   configuration; the Homey observe-mode default is `30 s`. Event wakes
   (Socket.IO) remain the low-latency path; polling is the fallback.
5. A world snapshot is stored as a reference body — target revisions plus
   coverage — and reconstructed on read by loading the referenced target
   observations, re-applying the recorded STALE regrades, and verifying the
   stored `artifact_sha256`. Legacy full-body rows remain readable.
   Observation bodies are stored zlib-compressed with prefix detection;
   legacy uncompressed rows remain readable.
6. Retention prunes with pinning. Never pruned: the most recent 24 hours of
   snapshots; snapshots referenced by an open dispatch attempt; snapshots
   referenced by an unscored autonomy shadow outcome or a pending approval;
   autonomy evaluations, bindings, receipts, effects, behavior signals and
   world events (audit records). Target observation rows prune only below
   the minimum revision any retained snapshot references, so reconstruction
   can never dangle. Evidence-id strings inside closed audit records may
   outlive the raw rows they name; that is accepted and documented, not
   hidden.
7. The continuous-store growth budget is frozen: target < `50 MB/day`,
   hard fail > `150 MB/day` for the M4 house (16 zones, 33 devices). The
   soak starts on a fresh store; the existing 13.7 GB store is archived
   read-only as evidence and never migrated.
8. The daemon survives faults: the cycle body runs under isolation with
   exponential backoff (initial `1 s`, doubling, cap `60 s`, reset on
   success) and a durable `runtime_circuit_open` event after five
   consecutive failures; the routine learner and lifecycle observers are
   isolated the same way; an entity-identity collision demotes to a durable
   `entity_identity_collision` event with deterministic exclusion of the
   later provider's colliding entities for that snapshot, instead of killing
   the process; failed provider subscriptions are retried every five
   minutes with `subscription_failed`/`subscription_restored` events.
9. Lifecycle-observer cursors are durable (`lifecycle_cursors_v1`), so a
   restart never silently drops the notification backlog. The runtime
   appends typed events: `runtime_started`, `runtime_stopped`,
   `runtime_lease_lost`, `runtime_circuit_open`, and a daily
   `runtime_heartbeat` carrying counts only (cycles, rows written versus
   confirmed, store bytes, open attempts).
10. The ntfy lifecycle observer accepts exactly these new runtime kinds as a
    bounded amendment to ADR-0007's accept list. Projections carry counts
    and statuses only — never lux, watt, presence, coordinates, images or
    raw observations.
11. Supervision is process-level: launchd (`KeepAlive`) restarts the
    process; lease loss stops the process cleanly and the restarted process
    acquires a fresh lease after expiry. There is no in-process lease
    re-acquire. Mac sleep gaps are accepted for M4 and logged, not hidden.
12. Every observation claim produced under this ADR is evidence class
    `PRODUCTION_OBSERVATIONAL` (`RESEARCH_PROTOCOL.md` §3). It supports no
    actuation, safety or certification claim.

## Alternatives

- Write full snapshot bodies and rely on disk: rejected because measured
  growth (~380 GB/week) makes a multi-week soak impossible on the target
  host.
- Skip snapshot persistence when unchanged instead of confirming: rejected
  because `confirmed_at` must advance for honest freshness; silence is
  indistinguishable from a dead observer (missing ≠ false).
- Deduplicate by hashing raw payloads without quantization: rejected because
  real sensors jitter continuously (watt decimals, lux flicker); dedupe
  would never fire and the store would still grow unbounded.
- Prune by age alone without pinning: rejected because scoring and recovery
  need the exact snapshots that shadow outcomes and open attempts reference;
  age-based pruning would corrupt evidence.
- In-process lease re-acquire after loss: rejected because exclusive
  ownership is simpler to prove through process restart; a second acquire
  path widens the fencing surface.
- External time-series database: rejected; no measured need beyond SQLite
  once dedupe, compression and retention exist (`CLAUDE.md` no-nos).

## Consequences

- An idle house writes near-zero rows; a busy house writes proportional to
  real transitions. The 24-hour and 48-hour burn-ins measure the budget in
  Decision 7 before the M4 soak starts.
- The autonomy stable-world skip gate, condition evaluation, oracle reads
  and learner all see reconstructed snapshots identical to stored bodies;
  a reconstruction defect is a correctness bug, guarded by fingerprint
  round-trip tests and a verification pass against a copy of the archived
  13.7 GB store.
- Quantization steps are part of the frozen observation contract; changing
  them later changes fingerprints and requires a documented revision, not a
  silent tweak.
- Pruning interacts with Phase B scoring by construction: an unscored shadow
  outcome pins its snapshots until scored.

## Safety and scientific impact

No authority surface changes. Proposals, policy, authorization, dispatch,
receipts and oracles are untouched. Mutation paths remain fail-closed and
`OBSERVE` mode still dispatches nothing. Retained behavioral data stays in
the local store and never leaves the machine; outbound ntfy projections are
count-only per Decision 10 and ADR-0007. The physical Homey evidence
boundary of ADR-0008 does not move: fourteen days of observation prove
observation, not actuation. A failed growth budget or an unexplained daemon
death fails M4; the gate is not moved afterwards.

## Migration and reversibility

Store migrations are additive (`semantic_sha256`, `confirmed_at`,
`lifecycle_cursors_v1`); legacy rows and legacy full-body snapshots remain
readable forever. The M4 soak uses a fresh database; the prior 13.7 GB store
is archived unchanged. Rolling back the code re-enables full-body writes and
unconditional revisions but leaves all written data readable; retention can
be disabled by simply not invoking prune. Stopping the daemon requires no
reconciliation: `OBSERVE` mode has no in-flight mutations by construction.

## Amendment 1 — M4 day-0 preflight corrections

- Status: **proposed, awaiting owner signature**. Nothing in this amendment
  is in force until the owner accepts it. The decisions above stay exactly
  as written and are not edited retroactively.
- Date: 2026-08-12
- Trigger: a live preflight run of ~2 hours on the real house, started
  2026-08-11T19:35Z. That run is **exploratory preflight evidence and is
  discarded**; it is never promoted to the frozen M4 soak, and no scored
  window began.

### A1.1 — The growth budget covers every store the soak writes

Decision 7 says "the continuous-store growth budget" without naming which
store. `docs/RUNBOOK_M4.md` measured the Engine store, while `14days.md`
already asked for all three databases. The preflight exposed the gap: the
Engine store held ~5 MB while the Homey plugin store held ~30 MB after the
same two hours.

The budget covers **every mutable local store the soak writes**: the Engine
database, the Homey plugin database and the context database, each counted
as main file plus write-ahead log, reported per store **and** as an
aggregate. The numeric gates are unchanged: target `< 50 MB/day`, hard fail
`> 150 MB/day`.

This clarification can only make the gate harder to pass. It is stricter
than the Engine-only reading, the thresholds are untouched, it is agreed
before a fresh burn-in on fresh stores, and the run that exposed the
ambiguity is discarded rather than scored. Recording it here is what keeps
it a clarification instead of a metric reinterpretation after seeing
results, which `RULES.md` MUST NOT 22 forbids.

The `runtime_heartbeat` payload's `store_bytes` field stays Engine-only: it
is a cheap in-process page-count read and must not reach across into plugin
storage. The aggregate is an operational measurement performed by the
runbook, not a new runtime contract.

### A1.2 — "An idle house writes near-zero rows" is falsified for this house

The Consequences section claims an idle house writes near-zero rows. The
preflight falsified it: 374 observation rows written and **zero**
deduplications, with every Homey revision (249/249) carrying a distinct
semantic fingerprint.

The cause is not a defect in the fingerprint. `semantic_fingerprint`
correctly excludes timestamps and observation ids from both observations and
relations, exactly as Decision 1 requires. The cause is physical: this house
has P1 and Homey Energy meters whose cumulative registers
(`meter_power.consumed`, `meter_power.daily`, `meter_power.imported`,
`energy_kwh`) increase on every poll by construction, joined by
`voltage.phaseN` at 0.1 V, `current.lN` at 0.01 A and `rssi`, none of which
fall under Decision 3's frozen quantization set of power, illuminance,
temperature and battery.

Honest restatement: rows follow canonical transitions, and on an
installation with cumulative energy metering a canonical transition occurs
every poll. Deduplication stays correct and useful wherever semantics are
genuinely unchanged, but it is not itself the M4 gate — the growth budget
is. The context plugin's row-per-observe behavior is by design and was never
in the A1 change-only scope.

No quantization bins are added by this amendment. Cumulative energy is real
semantic change and bucketing it would destroy meaning. If the compressed
and retained stores still miss the unchanged budget in a fresh burn-in, a
separate unit-aware sampling decision is preregistered **before** another
fresh burn-in, and never tuned against an official window.

### A1.3 — The frozen fixture does not match the observed house

Decision 7 freezes the budget "for the M4 house (16 zones, 33 devices)". The
observed house is materially larger: 95 entities, 471 observations and 239
relations per revision. This is recorded, not normalized away, and the
numeric budget is **not** raised to accommodate it. If the house cannot meet
the frozen budget, that is a recorded M4 failure with cuts, not a new number.

### A1.4 — Plugin-store encoding, and retention as a pending decision

Snapshot bodies in the Homey plugin store are stored zlib-compressed behind
a versioned prefix, with legacy rows readable forever and the state hash
still computed on the raw body so deduplication stays valid across the
encoding change (landed in `bd86078`; verified against 284 real preflight
rows, all decoding and round-tripping, compressing to 9.11% of raw).
Encoding discards no evidence and needs no signature.

**Retention for the plugin store is the open decision.** Deleting
observation history is an evidence boundary and needs the same explicit
signature Decision 6 received for the Engine store. The proposal is: keep
the newest snapshot unconditionally, keep a 24-hour horizon, prune only the
`snapshots` table, leave preference evidence, aliases, charters and the
projection and revision ledgers untouched, preserve revision monotonicity,
and reclaim pages verifiably. Production reads only `latest_snapshot`;
`snapshot_history` has one caller repo-wide and it is a test. Until this is
signed, the capability may exist but is wired to nothing.

### A1.5 — Additional durable diagnostics

The runtime records two further durable events, deliberately outside the
`runtime_*` namespace and outside Decision 10's outbound accept list:
`heartbeat_failed` when a heartbeat payload cannot be built, and
`durable_wake_failed` once per outage when the scheduled-wake read fails and
the loop degrades to polling. Both follow the existing convention for
isolated-failure diagnostics (`cycle_failed`, `prune_failed`,
`subscription_failed`). `runtime_stopped.reason` additionally admits
`crashed`, which outranks a simultaneous lease loss, so a fault escaping the
loop can no longer be recorded as a clean bounded-run completion. The
outbound ntfy accept list remains exactly the five kinds of Decision 10.

### A1.6 — Volatile electrical metering is not house identity

- Status: **accepted by explicit owner implementation direction on 2026-08-14**.
- Trigger: the 2026-08-14 burn-in was minting a new Homey snapshot and Engine
  target revision every 30 s because P1 / Homey Energy registers
  (`measure_power*`, `meter_power*`, `voltage*`, `current*`, `power_w`,
  `energy_kwh`, `house_power_w`) tick by construction. A1.2 recorded this
  honestly and required a separate unit-aware sampling decision to be
  preregistered **before** another fresh burn-in. This is that decision.

House identity — Homey `state_hash` and Engine `semantic_fingerprint` —
omits volatile electrical metering **values**. Homey identity also omits
capability `observed_at` timestamps, matching Decision 1 (timestamps are
not identity). The capability's existence, the rest of the house (on/off,
dim, lux, presence, temperature, availability), and obligation
status/reason stay in the identity. A watt or kWh tick therefore does not
consume a revision.

When a non-metering transition does consume a revision (a light change,
presence, lux bucket, obligation status), the **stored body still includes
the current watts/kWh** as of that transition. Oracles and later reads can
use those readings after a light change. They cannot reconstruct a
watt-resolution time series between transitions.

This is not a new quantization bin and does not change Decision 3. It is
an identity-sampling rule. `rssi` and other non-metering jitter remain in
identity; they are a separate decision if they still dominate a later
burn-in. Existing stores computed fingerprints including meters; this
rule requires a fresh-store restart so the same-revision fingerprint
invariant is not violated by the contract change.
