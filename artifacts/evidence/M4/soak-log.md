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

## 2026-08-14

### Discarded preflight sealed off the official path

The Aug-11 isolated daemon was still running at `00:47:57Z` (launchd pid
3923, `runs=1`, never exited). It had been exploratory evidence only. After
~53 h the three-store aggregate was `352,641,208` bytes (~160 MB/day),
dominated by the Homey plugin store (`285,966,336` main + WAL). Engine
retention had begun (`prune_runs` present) but HomeOps prune remained 0, as
required while H2 stays unwired. Compression on that discarded store was
`409,849,112` raw → `37,155,295` stored (9.07%). Dispatch attempts remained
0. Mode remained `observe`.

The owner asked to run the 14-day handoff. The discarded preflight was
stopped with `launchctl bootout` and archived read-only with SQLite
`.backup` (not `cp`) to
`/Users/danillofelanso/engine-m4/discarded-preflight-2026-08-11/`:

- `engine.sqlite3` `58,142,720` bytes
  `sha256=c94a019fe9a2e809173719cf8b73fb1bd10585fb07ba1d4c7df87a3be41b563f`
- `homeops.local.db` `286,949,376` bytes
  `sha256=d0b97326dff26e24182c7ec480e06c7ddc20207e6c40c200a117f230a89b2394`
- `context.sqlite3` `8,192` bytes
  `sha256=84c509b0b4f919d09cb3041044fa1649b12dc1a3ab03abd6ad9aa10e79ac09d0`

Those files are `chmod 444`. They do not count toward the official window.

### Fresh isolated runtime and burn-in 0 h

- Soak commit actually installed into
  `/Users/danillofelanso/engine-m4/runtime-venv/`: `46dbd7470486f90e6193cf725f38a9e1e3d37800`
- Installs are non-editable wheels in the venv. `import engine` resolves
  inside the venv, not the workspace. Plugin entry points: `context`,
  `homey`, `ntfy`. `engine.reference-world` is absent.
- Live stores wiped and recreated under `engine-m4/live/`. Homey config
  copy retained: `mode=observe`, `events=false`, no
  `poll_interval_seconds` (frozen 30 s default), `ENGINE_HOMEY_ARMED`
  unset.
- `00:51:18Z`: launchd bootstrapped. pid `74836`, `runs=1`, lease
  generation 1, one `runtime_started`, one `runtime_heartbeat`.
- Homey poll is live: target `home` available, zones/devices `complete`.
  An early `home` revision 0/1 pair is retained. Context location and sun
  are `UNKNOWN` (no coordinates configured). Dispatch attempts: 0.
- H2 remains unwired: HomeOps `snapshot_prune_runs=0`.

`checkpoint=2026-08-14T00:52:42Z aggregate_bytes=2158848`

```text
engine.sqlite3         main=4096         wal=683952     total=688048
context.sqlite3        main=8192         wal=0          total=8192
homeops.local.db       main=4096         wal=1458512    total=1462608
```

HomeOps counters at 0 h: `snapshot_rows_written=3`,
`snapshot_raw_body_bytes_written=371568`,
`snapshot_stored_body_bytes_written=33556` (9.03% of raw on this tiny
sample), `snapshot_deduplications=0`, `snapshot_prune_runs=0`.

Engine `store status`: `auto_vacuum=incremental`, `prune_runs=1`,
`target_observation_rows_written=5`, `dispatch_attempts_v1=0`.

This timestamp is the **burn-in 0 h** mark, not the official fourteen-day
start. 24 h and 48 h measurements, then the sleep/wake gate, are still
required. ADR-0011 Amendment 1 and H2 enablement remain unsigned. The
existing local read-only PAT was reused from the LaunchAgent plist at the
owner's "run the 14-day handoff" instruction; the token value is not
recorded here. Rotating it is still the safer credential hygiene.

### Meter-identity restart (A1.6)

The owner ordered watt/kWh ticks to stop minting a new house, while
keeping current watts on the snapshot after a real change (a light
flip). That sampling decision is ADR-0011 A1.6.

The ~7 h burn-in above was still on the old identity rule (a new house
every 30 s). It was stopped at `07:59:50Z` and archived read-only to
`/Users/danillofelanso/engine-m4/discarded-burnin-2026-08-14-pre-meter-identity/`:

- `engine.sqlite3` `16,830,464` bytes
  `sha256=f66936a81c255aac58bb0accb0639ebea943c3ca62ce6e1be4332312d81b490f`
- `homeops.local.db` `10,600,448` bytes
  `sha256=53418f053c8891499f78014eba4ed2b14b716e6c0c9f55d9c3254bd194a67579`
- `context.sqlite3` `8,192` bytes
  `sha256=69380d4616e228acde43e82ebe1907caae6c94afe71f50680a37b6de341993ab`

Those files are `chmod 444`. They are not the official window.

A first restart on `d8c81a9` (meters only) still minted a house every
poll. Diffing those rows showed the leftover identity signals were P1
`rssi` and `net_load_phase1_pct`, not lights. `9f123c8` added those to
the same exclusion set. That probe was wiped, not archived.

Isolated runtime reinstalled from `9f123c8`. Fresh stores under
`engine-m4/live/`. Mode `observe`, unarmed, 30 s poll.

`08:05:30Z`: launchd pid `52721`, `runs=1`, lease generation 1.

At `08:08:09Z` (~2.5 min / five extra polls):

```text
engine.sqlite3         main=4096         wal=811672     total=815768
context.sqlite3        main=8192         wal=0          total=8192
homeops.local.db       main=4096         wal=1425552    total=1429648
aggregate_bytes=2253608
```

HomeOps: `snapshot_rows_written=1`, `snapshot_deduplications=5`,
revision still `0`. Engine `home`: 2 rows / max revision 1,
`target_observation_deduplications=4`. Dispatch attempts: 0.

`checkpoint=2026-08-14T08:08:09Z aggregate_bytes=2253608`

This is the new **burn-in 0 h**. Official fourteen-day clock is still
off. 24 h / 48 h and sleep/wake remain required.
