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
