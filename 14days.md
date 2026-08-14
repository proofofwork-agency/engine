# Engine 0.2: 14-day M4 observation gate

This is the self-contained handoff for an agent continuing Engine 0.2 Phase A6
from another computer or session. Read it together with
[`GOAL-0.2.md`](GOAL-0.2.md),
[`ADR-0011`](docs/adr/ADR-0011-bounded-continuous-observation.md), and
[`RUNBOOK_M4`](docs/RUNBOOK_M4.md). The stricter source wins if these documents
ever disagree.

## Current state

Last updated: `2026-08-14T08:08Z` (meter-identity restart; official clock still off).

- The discarded Aug-11 preflight and the 2026-08-14 pre-A1.6 burn-in were
  stopped and archived. They are not the official window.
- A fresh isolated runtime is running on the original Mac under launchd
  label `com.proofofworks.engine.observe`, built from commit
  `9f123c8`.
- Mode is Homey `observe`, unarmed. Dispatch attempts are zero.
- Installed plugin entry points: `engine.context`, `engine.homey`,
  `engine.ntfy`. `engine.reference-world` is absent.
- Homey polling is authoritative at 30 seconds (`events = false`).
- House identity now ignores watt/kWh/voltage/current, `rssi` and
  `net_load_phase1_pct`. A real change still stores current watts.
- Burn-in 0 h: `2026-08-14T08:08:09Z`, aggregate `2,253,608` bytes.
  After five extra polls Homey still had **one** snapshot row and five
  deduplications. Next required marks: 24 h and 48 h, then sleep/wake,
  then the official fourteen-day timestamp.
- H2 plugin-store retention remains wired to nothing.
- ADR-0011 Amendment 1 remains unsigned; A1.6 (meter identity) is in
  force by owner implementation direction. Growth is still measured
  across all three stores including WAL.

### Before the clock may start (as of commit `89a99ac`)

1. **Rotate the Homey PAT.** It was exposed in an agent transcript on
   2026-08-11. Create a new read-only token, revoke the old one, and reinstall
   it in the LaunchAgent plist only. Owner-only step.
2. **Sign or reject ADR-0011 Amendment 1** (`docs/adr/ADR-0011-bounded-continuous-observation.md`).
   It is proposed and not in force. It clarifies that the growth budget covers
   all three stores including write-ahead logs with the numeric gates
   unchanged, restates the falsified "idle house writes near-zero rows"
   consequence honestly, records the fixture mismatch without raising the
   budget, and names plugin-store retention as the open decision.
3. **Decide on plugin-store retention (H2).** The capability is being built
   deliberately wired to nothing; enabling it deletes observation history and
   needs the same explicit signature the Engine store's retention received.
4. **Rebuild the runtime and the stores from the committed code.** The daemon
   runs its own virtual environment at `engine-m4/runtime-venv/`; reinstall it
   so the code under test is the committed code, and start from fresh stores.
   A store holding rows written before `bd86078` mixes uncompressed and
   compressed bodies and pollutes the compression evidence.
5. **Run the mandatory 24 h/48 h burn-in** per `docs/RUNBOOK_M4.md` §5a, then
   the sleep/wake gate, and only then start the fourteen days.

What already landed in response: snapshot bodies in the plugin store are
zlib-compressed with permanent legacy readability, measured at 9.11% of raw
against 284 real preflight rows; and the daemon can no longer be killed by an
unguarded scheduled-wake read, nor record a crash as a clean stop
(`bd86078`). Deduplication counters near zero are expected on a house with
cumulative energy metering and are not themselves a failure — the budget is
the gate.

The original Mac's local operational paths are:

- Engine store: `/Users/danillofelanso/engine-m4/live/engine.sqlite3`
- Homey store: `/Users/danillofelanso/engine-m4/live/homeops.local.db`
- Context store: `/Users/danillofelanso/engine-m4/live/context.sqlite3`
- Isolated runtime: `/Users/danillofelanso/engine-m4/runtime-venv/`
- Installed plist:
  `/Users/danillofelanso/Library/LaunchAgents/com.proofofworks.engine.observe.plist`
- Logs: `/Users/danillofelanso/Library/Logs/engine/engine-m4-observe.*.log`
- Dated evidence log: [`artifacts/evidence/M4/soak-log.md`](artifacts/evidence/M4/soak-log.md)

The read-only Homey token exists only in the local `.env` and installed plist.
It must never be printed, copied into evidence, committed, or sent to another
agent. The old 13.7 GB SQLite archive is also local and Git-ignored; its
reconstruction check passed all 30,123 snapshots with zero failures.

## What M4 is proving

M4 is the "eyes open" gate. It tests whether the same Heart can observe the
real house for at least fourteen calendar days with durable state, explicit
gaps, bounded storage, and restart continuity. It is not an intelligence,
actuation, physical-safety, or certification gate.

Fourteen days were frozen before observing results because they include:

- two complete weekly cycles, including two weekends;
- repeated sleep/wake and network-recovery opportunities;
- fourteen daily heartbeat boundaries;
- enough time for 24-hour retention and pruning to reach steady operation;
- a meaningful MB/day storage-growth slope.

A shorter run would mostly prove that the process starts. Fourteen days are
still not enough to claim seasonal behavior, holiday behavior, long-term
safety, or general intelligence.

## What happens during the window

The Homey provider performs read-only polls. Engine normalizes and quantizes
sensor evidence, writes a new target revision only when semantics change, and
otherwise advances `confirmed_at`. World snapshots store target references
rather than duplicating every entity and observation. Target bodies are
compressed. The Heart writes daily counts-only heartbeats and runs retention
at most hourly.

Mac sleep is allowed. Sleep gaps must remain visible in observation timestamps
and `confirmed_at`; they must never be fabricated away. A process crash is also
allowed only when launchd restores observation and the lease prevents two
simultaneous Hearts. An unexplained dead daemon is a failure.

The Homey plugin store retains provider-specific aliases, revision continuity,
projection fingerprints, and Homey change history. The Engine store owns the
canonical typed observations, reconstructed world snapshots, behavior signals,
runtime events, lifecycle cursors, lease, and audit records. The stores remain
separate by design.

## Safety and privacy boundary

Throughout M4:

- `ENGINE_HOMEY_MODE=observe` remains forced;
- `ENGINE_HOMEY_ARMED` remains absent;
- the PAT has zone/device read-only scopes only;
- `dispatch_attempts_v1` must remain empty;
- no device command, approval, or delegated authority is permitted;
- all operational data remains local to the original Mac;
- no LLM or Cell receives raw house data;
- no model is trained and no model weights are changed.

If any of these conditions changes, stop the soak and record the failure.

## Required sleep/wake gate before starting the clock

Run this on the original Mac, not on a second independent machine:

1. Record UTC time, launchd PID/run count, lease generation, maximum world
   revision, latest Homey `confirmed_at`, runtime event counts, and dispatch
   count in the soak log.
2. Sleep the Mac for at least two minutes.
3. Wake it and wait for the next 30-second Homey poll.
4. Verify that the same daemon process survived, the lease generation did not
   change, observation resumed, and the two-minute gap remains visible.
5. Verify that `runtime_started` did not increase and dispatch attempts remain
   zero.
6. Record the passing result and the official UTC start timestamp in
   `artifacts/evidence/M4/soak-log.md`. Only that timestamp starts the fourteen
   calendar days.

If the process dies or observation does not recover, the gate fails. Diagnose
and fix it before starting a new official window; do not backdate the clock.

## Daily monitoring

Do not use `engine status --json` for routine monitoring because it materializes
the complete private world snapshot. Prefer counts-only SQLite queries and
filtered launchd output.

```bash
launchctl print gui/$UID/com.proofofworks.engine.observe \
  | awk '/state =|runs =|pid =|last exit code =/{print}'

sqlite3 /Users/danillofelanso/engine-m4/live/engine.sqlite3 \
  "SELECT kind, COUNT(*) FROM world_events_v2 GROUP BY kind ORDER BY kind;"

sqlite3 /Users/danillofelanso/engine-m4/live/engine.sqlite3 \
  "SELECT target_id, COUNT(*), MAX(revision), MAX(confirmed_at)
     FROM target_observations_v2 GROUP BY target_id ORDER BY target_id;"

sqlite3 /Users/danillofelanso/engine-m4/live/engine.sqlite3 \
  "SELECT COUNT(*) AS dispatch_attempts FROM dispatch_attempts_v1;"

sqlite3 /Users/danillofelanso/engine-m4/live/engine.sqlite3 \
  "SELECT created_at, payload_json FROM world_events_v2
     WHERE kind='runtime_heartbeat' ORDER BY id DESC LIMIT 1;"
```

Once per UTC day, append one dated line to the evidence log containing:

- daemon state, PID/run count, and lease generation;
- latest Homey confirmation time and snapshot revision;
- runtime heartbeat counts;
- Engine, Homey, and context database byte sizes, including active WAL files;
- rows written versus rows confirmed;
- dispatch-attempt count, which must remain zero;
- any sleep, crash, network outage, or unexplained gap.

Storage target: less than 50 MB/day. Between 50 and 150 MB/day is not a pass and
must be investigated. More than 150 MB/day is a hard M4 failure. Never move
these bounds after seeing the data.

## Pass/fail decision after fourteen days

M4 passes only if all of the following are true:

- elapsed time from the recorded official start is at least fourteen days;
- observation recovered after expected sleep/restart events;
- there was no unexplained daemon death;
- gaps and failures remain visible rather than rewritten;
- behavior and manual-override signals are durable;
- reconstruction and target-revision continuity remain valid;
- storage growth is within the frozen budget;
- no device dispatch occurred.

At the end, stop launchd with `launchctl bootout`, checkpoint/archive the live
SQLite databases consistently, make the evidence copies read-only, record final
counts and byte sizes, run the snapshot reconstruction verifier, and write an
honest pass or fail against `GOAL-0.2.md`. A failed gate is evidence, not a
reason to weaken the protocol.

## Relationship to Cells and LLMs

M4 does not train or call a model. It builds the trustworthy evidence layer on
which later proposals can be evaluated:

```text
Homey + local context
        -> Heart validation and canonical WorldStore
        -> deterministic baselines / shadow scorer
        -> optional bounded LLM context projection
        -> optional curated dataset for a separate Cell experiment
```

The Heart owns authoritative state, continuity, policy, authorization, and
audit. An LLM may later make broad, untrusted proposals from a bounded context
projection. A Cell would be a small local specialist for one measured task.
Neither can grant authority or certify success. The repository's first Cell
experiment was a no-go and is not registered in this runtime.

## What comes after M4

1. **M5, shadow competence.** Engine makes inert proposals and compares them
   with actual household behavior. The planned frozen gate requires at least 50
   closed opportunities over at least 10 days, at least 60% agreement, at least
   10 percentage points over the best equal-budget baseline, and at most 10%
   strict false intervention. No action is dispatched.
2. **M6, first cross-body decision.** A Homey proposal must cite typed evidence
   from `engine.context`. It first passes five simulated loops, including an
   injected no-effect case, before one explicitly approved supervised live
   action can be considered.
3. **M7, earned hands.** One physical lighting zone must pass five supervised
   loops with independent lux and watt verification, including a no-effect
   disturbance. Only that proven zone may then receive bounded delegated
   authority, followed by a clean seven-day delegated soak.

Passing M4 unlocks evidence that Engine can observe reliably. It does not by
itself authorize M5, M6, M7, a Cell, an LLM, or any physical action.

## Takeover from another computer

A repository clone on another computer can review code and evidence, but it
cannot silently continue the live soak: the authoritative process, token, lease,
and databases are on the original Mac. Do not start a second daemon and combine
its time or rows with this run.

To continue this exact window, access the original Mac and append to the same
evidence log. If the operational host must move, stop and seal the original run,
record the interruption, establish fresh paths and credentials on the new host,
rerun both restart gates, and begin a new explicitly timestamped fourteen-day
window.
