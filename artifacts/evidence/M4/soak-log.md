# M4 continuous-observation soak log

Evidence class: `PRODUCTION_OBSERVATIONAL`. This log supports observation and
runtime-continuity claims only; it does not support actuation, safety, or
certification claims.

- Runtime commit: `7918f06bd2de2725e7f4784e0160eb60b125fbbc`
- Frozen mode: Homey `observe`, unarmed, authoritative 30-second polling
- Engine store: `/Users/danillofelanso/engine-m4/live/engine.sqlite3`
- Context store: `/Users/danillofelanso/engine-m4/live/context.sqlite3`
- Homey store: `/Users/danillofelanso/engine-m4/live/homeops.local.db`
- Installed plugin scope: `engine.context`, `engine.homey`, and `engine.ntfy`.
  The synthetic `engine.reference-world` test provider is deliberately absent
  from the M4 runtime so it cannot contaminate the real-house growth metric.
- Pre-soak archive: `engine-pre-soak-13.7g.sqlite3`, read-only, 13,711,667,200
  bytes; reconstruction verifier result `verified=30123 legacy=30123
  reference=0 failures=0`
- Official 14-day clock: **not started** until the day-one sleep/wake gate
  passes.

## 2026-08-11

### Preflight runtime (excluded from the official growth window)

- `19:27:27Z`: launchd service bootstrapped against fresh stores. Initial
  state was running, launch count 1, lease generation 1. Runtime recorded one
  `runtime_started` and one daily `runtime_heartbeat`.
- Homey read attempts at snapshot revisions 1, 16, and 32 recorded
  `HomeyHTTPError`/`URLError` in snapshot coverage. The local endpoint remained
  reachable, and an authenticated read-only transport check returned 21 zones
  and 73 devices. Observation recovered without restarting: the first durable
  Homey target row was recorded at `19:28:57Z`; subsequent 30-second polls
  continued successfully. The transient gap remains visible in the store.
- Configuration deliberately retains `events = false`; polling is
  authoritative. The initial `subscription_failed` event is retained as
  operational evidence rather than hidden.
- `19:30:19Z`: supervised hard-kill baseline: lease generation 1,
  `runtime_started=1`, `runtime_stopped=0`, `runtime_lease_lost=0`, world
  snapshot revision 90.
- The Python `engine run` child was sent `SIGKILL`. launchd attempted an early
  replacement while the 15-second lease was still current; that process failed
  closed with `LeaseHeldError`. The throttled subsequent replacement acquired
  lease generation 2 and was running at `19:30:57Z`.
- Hard-kill result: `runtime_started=2`, `runtime_stopped=0`,
  `runtime_lease_lost=0`. The durable `ntfy-engine-milestones` lifecycle cursor
  advanced to event sequence 4 without backlog loss or duplicate runtime
  events. **Kill/restart gate passed.**
- This first preflight used the workspace environment, which also discovered
  the synthetic `engine.reference-world` provider. It was stopped cleanly and
  its stores were retained outside `engine-m4/live/`; none of its rows or bytes
  count toward the official M4 window.

### Final isolated runtime

- A dedicated runtime environment was built from commit `7918f06` with only
  the context, Homey, and ntfy plugin entry points. Fresh stores were created
  under `engine-m4/live/` and launchd was pointed directly at that environment.
- `19:35:01Z`: final service bootstrapped. Snapshot revision 1 preserved a
  transient Homey `URLError`; the second authoritative poll succeeded at
  `19:35:31Z` without restart. Coverage and target freshness show the gap and
  recovery explicitly.
- `19:36:04Z`: final supervised hard-kill baseline: lease generation 1,
  `runtime_started=1`, `runtime_stopped=0`, `runtime_lease_lost=0`, snapshot
  revision 3, and zero dispatch attempts.
- The launchd-managed daemon was sent `SIGKILL`. The immediate replacement
  failed closed on the still-current lease. The throttled next replacement was
  running at `19:36:45Z` with lease generation 2.
- Final hard-kill result: `runtime_started=2`, `runtime_stopped=0`,
  `runtime_lease_lost=0`, zero dispatch attempts, and lifecycle cursor sequence
  4. **Kill/restart gate passed in the definitive runtime.**
- `19:37:21Z` pre-sleep baseline: process 67385 running, lease generation 2,
  latest Homey confirmation `19:37:15Z`, latest snapshot revision 5.
- Remaining day-one gate: sleep the Mac for at least two minutes, wake it, and
  verify that the process survives and observation resumes with the gap left
  visible. The official soak clock starts only after this passes.

### Day-0 storage preflight — clock deliberately not started

Independent read-only verification of the running preflight, at
`21:42Z` after 2 h 07 min. Two agents measured the same store separately and
reached the same conclusion: this configuration cannot pass its own growth
gate, so the frozen fourteen-day window was not opened.

- Deduplication never fired: `target_observation_rows_written=374`,
  `target_observation_deduplications=0`. Per target: `home` 249 rows with 249
  distinct semantic fingerprints, `engine.context.local` 126/126.
- The fingerprint is not at fault. A hypothesis that relation timestamps leaked
  into `semantic_fingerprint` was tested and disproved: the semantic projection
  strips `observed_at` from both relations and observations, so Decision 1
  holds as implemented.
- The churn is physical. Diffing consecutive `home` revisions showed 18 changed
  values per poll, dominated by cumulative energy registers
  (`meter_power.consumed` 77398.101 → 77398.107, `meter_power.daily`,
  `meter_power.imported`, `energy_kwh`) that rise every poll by construction,
  plus `voltage.phaseN` at 0.1 V, `current.l1` at 0.01 A and `rssi`, none of
  which fall under the frozen quantization set of Decision 3.
- Store sizes after 2 h 07 min: Engine `5,148,672` bytes (initial fill rate,
  retention horizon not yet crossed — `prune_runs=4`, `pruned=0`, correct);
  Homey plugin store `30,142,464` bytes across 252 snapshot rows averaging
  ~120 KB, with no compression and no retention, i.e. roughly `346 MB/day`
  unbounded and ~4.8 GB over fourteen days.
- The plugin store was outside every mechanism ADR-0011 defined; A1 to A3 only
  ever covered the Engine store.
- The observed house (95 entities, 471 observations, 239 relations per
  revision) is materially larger than the fixture the budget was frozen
  against ("16 zones, 33 devices"). Recorded, not normalized; the budget was
  not raised.
- Credential incident: the installed LaunchAgent plist was read with an
  inadequate redaction pattern and the read-only Homey PAT was exposed in an
  agent transcript. The token must be rotated and reinstalled locally before
  any decisive run. No token value appears in this repository.

Actions taken, none of them a gate change: snapshot bodies in the plugin store
are now zlib-compressed with permanent legacy readability, and the daemon can
no longer die from an unguarded scheduled-wake read or record a crash as a
clean stop (`bd86078`). Compression measured against 284 real preflight rows:
`35,184,077` raw → `3,204,310` stored, 9.11% of raw. Retention for the plugin
store remains unimplemented and unwired pending owner signature on ADR-0011
Amendment 1.

This preflight run is exploratory evidence and is discarded. The official
window starts only after PAT rotation, fresh stores on the committed runtime,
a passing 24 h/48 h burn-in per `docs/RUNBOOK_M4.md` §5a, and the sleep/wake
gate.
