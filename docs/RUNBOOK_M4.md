# RUNBOOK_M4 — 14-day continuous observation soak

> Everything this runbook produces is evidence class `PRODUCTION_OBSERVATIONAL`
> (`RESEARCH_PROTOCOL.md` §3, ADR-0011 Decision 12). It proves observation
> only. It supports no actuation, safety or certification claim.

Anchors: `GOAL-0.2.md` M4 "Ogen open", `docs/adr/ADR-0011-bounded-continuous-observation.md`.

## 1. Scope

Run the Engine daemon (`engine run`) against the real Homey house in
`OBSERVE` mode for at least fourteen days under launchd supervision.
Mac sleep gaps are accepted and stay visible in the record (heartbeat and
`confirmed_at` gaps); they are logged, never hidden. Nothing in this runbook
arms the runtime or dispatches an action: `OBSERVE` mode dispatches nothing
by construction, and `ENGINE_HOMEY_ARMED` stays unset throughout.

M4 passes when the soak shows: continuous observation with restart
continuity, durable behavior and manual-override signals, and store growth
within budget — target `< 50 MB/day`, hard fail `> 150 MB/day`
(ADR-0011 Decision 7). An unexplained daemon death or a busted growth budget
fails M4; the gate does not move afterwards.

## 2. Preconditions

1. Repository gate is green at the soak commit (`uv run --with pytest
   pytest -q`, Ruff F/I) and the commit hash is recorded with the evidence.
2. Stop every process using the existing live store and verify that
   `lsof .engine/engine.sqlite3` reports no holder. Then create a
   SQLite-consistent read-only archive; never open the archived copy through
   Engine (which would migrate it):

   ```bash
   mkdir -p artifacts/evidence/M4
   sqlite3 .engine/engine.sqlite3 ".backup 'artifacts/evidence/M4/engine-pre-soak-13.7g.sqlite3'"
   uv run python tools/verify_snapshot_reconstruction.py --database artifacts/evidence/M4/engine-pre-soak-13.7g.sqlite3
   chmod 444 artifacts/evidence/M4/engine-pre-soak-13.7g.sqlite3
   ```

   The SQLite backup includes committed WAL state without copying transient
   `-wal`/`-shm` files. Leave the source and old context/reference stores in
   place; the soak points at fresh paths.
3. Create a fresh soak directory, e.g. `~/engine-m4/`, for the new
   databases and the Homey config copy.
4. Make a soak copy of the Homey config, e.g. `~/engine-m4/homey.observe.toml`:
   - set `mode = "observe"` (the env override in §3 also forces this;
     keeping both aligned removes ambiguity);
   - **remove the `poll_interval_seconds` line.** The live config pins
     an explicit value; only when the key is absent does the frozen observe
     default of `30 s` apply (ADR-0011 Decision 4). The env override fixes
     mode, not poll.
   - Note: `plugin_database`-style paths inside the TOML resolve relative
     to the config file's directory, so the Homey plugin's local store
     lands in the soak directory as intended.
5. Use a read-only Homey Personal Access Token (zone + device read scopes
   only, per `plugins/engine-homey/DEPLOYMENT.md` §1). The soak must not
   hold write scopes it cannot use.
6. Verify no other runtime holds a lease on the fresh store (a fresh
   database cannot have one; `engine status` shows `lease: null`).

## 3. Environment

| Variable | Value for the soak | Semantics |
| --- | --- | --- |
| `ENGINE_DATABASE` | fresh **absolute** path, e.g. `/Users/REPLACE/engine-m4/engine.sqlite3` | Default is CWD-relative `.engine/engine.sqlite3`; launchd does not shell-expand `~`, and its working directory makes relative paths a trap. |
| `ENGINE_CONTEXT_DATABASE` | fresh absolute path, e.g. `/Users/REPLACE/engine-m4/context.sqlite3` | Same CWD-relative default. |
| `ENGINE_HOMEY_CONFIG` | absolute path of the soak TOML copy | Required by the Homey plugin. |
| `ENGINE_HOMEY_TOKEN` | the read-only PAT | Required when auth is `token`. |
| `ENGINE_HOMEY_AUTH` | `token` | `cli` auth disables Socket.IO events and falls back to polling only. |
| `ENGINE_HOMEY_MODE` | `observe` | Env overrides the config's `mode`; keep the soak copy aligned as defense in depth. |
| `ENGINE_HOMEY_ARMED` | **unset** | Armed only when exactly `1`; unset is the safe default and stays unset for all of M4. |
| `ENGINE_NTFY_TOPIC` | optional | Unset means notifications off. When set, outbound projections carry counts and statuses only (ADR-0007 + ADR-0011 Decision 10). |
| `ENGINE_CONTEXT_LATITUDE` / `ENGINE_CONTEXT_LONGITUDE` | optional | Absent means location observations are `UNKNOWN` — honest, not an error. |

## 4. launchd supervision

1. Copy `docs/launchd/com.proofofworks.engine.observe.plist` to
   `~/Library/LaunchAgents/`, fill in the `REPLACE` values, `chmod 600` the
   installed copy (it carries the PAT). Never commit a filled-in copy.
2. Create the log directory: `mkdir -p ~/Library/Logs/engine`.
3. Start and verify:

   ```bash
   launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.proofofworks.engine.observe.plist
   launchctl print gui/$UID/com.proofofworks.engine.observe   # state = running
   uv run engine status                                       # lease present, store_bytes small
   ```

4. Restart semantics (ADR-0011 Decision 11): `KeepAlive` is plain `true`,
   so launchd restarts the process after **every** exit — crash, `kill -9`,
   and lease loss (which exits cleanly with code 0 after appending
   `runtime_lease_lost`). There is no in-process lease re-acquire. After a
   long-lived process exits, launchd may try the first replacement
   immediately: the runtime lease itself rejects that process if the old
   15-second lease has not expired. `ThrottleInterval` then spaces rapid
   retries by 30 seconds, so a later supervised attempt starts after expiry.
5. Because every exit restarts, the only way to stop the soak is:

   ```bash
   launchctl bootout gui/$UID/com.proofofworks.engine.observe
   ```

   `launchctl kickstart -k gui/$UID/com.proofofworks.engine.observe` forces
   a supervised restart.

## 5. Supervised restart checks (A5 operational gate)

Run both checks on day one, while watching:

1. **kill -9.** Find the pid (`launchctl print` or `pgrep -f "engine run"`),
   `kill -9` it, wait ≥ 30 s. Pass: a new process is running; `engine
   status` shows a fresh lease generation; the store gained exactly one new
   `runtime_started` event and the previous epoch shows no clean
   `runtime_stopped` (the kill is visible, not hidden); lifecycle
   notifications resume from the durable cursor without a flood of
   duplicates and without a dropped backlog.
2. **Sleep/wake.** Sleep the Mac ≥ 2 minutes, wake it. Pass: the same
   process is still running (no restart needed), observation resumes, and
   the gap stays visible as a hole between `confirmed_at` advances /
   heartbeats. A hidden gap or a dead daemon is a fail.

A restart that duplicates or drops the notification backlog fails the A5
gate — fix before starting the fourteen-day window.

A nonzero exit code between restarts is expected and is not a failure. When
launchd replaces a process immediately, the new one finds the previous
15-second lease still valid, refuses to run, and exits with `LeaseHeldError`
in the error log. `ThrottleInterval` then spaces the next attempt past
expiry. The pass condition is a running process with a fresh lease
generation, not a clean exit code on every attempt.

## 5a. Burn-in before the official clock (mandatory)

ADR-0011 Decision 7 requires a 24-hour and 48-hour burn-in before the frozen
fourteen-day window. Do not skip it: a day-0 preflight on 2026-08-11 showed
the plugin store growing at roughly 346 MB/day, which would have consumed
the frozen window on a run that could not pass its own gate.

Preconditions specific to the burn-in:

1. Rotate the Homey PAT if it has ever been exposed, and reinstall it in the
   LaunchAgent plist only.
2. Use **fresh** stores. A store carrying rows written before `bd86078`
   mixes uncompressed and compressed bodies and pollutes the compression
   evidence.
3. Record the commit hash the daemon actually runs. If the daemon runs from
   its own virtual environment, reinstall it so the code under test is the
   committed code.

Measure at 0 h, 24 h and 48 h. The budget covers **all three stores**, main
file plus write-ahead log, per store and aggregated (ADR-0011 Amendment 1.1):

Your terminal does **not** inherit the daemon's environment: those variables
live in the LaunchAgent plist, not in your shell, so reading `$ENGINE_DATABASE`
from a fresh terminal measures nothing or the wrong store. Resolve the paths
from the plist itself, which is also what keeps this measurement honest when
the plist changes. Only non-secret keys are read; the token is never touched.

```bash
set -eu
PLIST="$HOME/Library/LaunchAgents/com.proofofworks.engine.observe.plist"
ENGINE_DB=$(plutil -extract EnvironmentVariables.ENGINE_DATABASE raw "$PLIST")
CONTEXT_DB=$(plutil -extract EnvironmentVariables.ENGINE_CONTEXT_DATABASE raw "$PLIST")
HOMEY_CFG=$(plutil -extract EnvironmentVariables.ENGINE_HOMEY_CONFIG raw "$PLIST")

# The Homey store's filename comes from the config, not from convention.
HOMEOPS_DB=$(uv run python -c '
import sys, tomllib
from pathlib import Path
cfg = Path(sys.argv[1])
rel = tomllib.loads(cfg.read_text())["homey"].get("plugin_database", "homeops.db")
print((cfg.parent / rel).resolve())
' "$HOMEY_CFG")

total=0
for db in "$ENGINE_DB" "$CONTEXT_DB" "$HOMEOPS_DB"; do
  if [ ! -f "$db" ]; then echo "MISSING STORE: $db" >&2; exit 1; fi
  main=$(stat -f%z "$db")
  wal=0; [ -f "$db-wal" ] && wal=$(stat -f%z "$db-wal")
  sub=$((main + wal)); total=$((total + sub))
  printf '%-22s main=%-12s wal=%-10s total=%s\n' "$(basename "$db")" "$main" "$wal" "$sub"
done
printf 'checkpoint=%s aggregate_bytes=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$total"
```

A missing store aborts the measurement rather than counting as zero: silently
scoring a store that does not exist as "no growth" is the one way this
measurement could report a pass it did not earn.

Paste the `checkpoint=` line into the soak log at each of 0 h, 24 h and 48 h.
The rate between two checkpoints is
`(bytes_later - bytes_earlier) / (seconds_between) * 86400 / 1e6` MB/day;
compare that against the budget, not the raw totals.

Read the plugin store's own counters, which no CLI surfaces:

```bash
sqlite3 "file:$HOMEOPS_DB?mode=ro" \
  "SELECT name, value FROM snapshot_storage_counters_v1 ORDER BY name;"
```

`snapshot_raw_body_bytes_written` divided by
`snapshot_stored_body_bytes_written` is the compression evidence measured in
production rather than in a benchmark. If this query fails with *no such
table*, the store predates the compression build and is **not a valid burn-in
store** — start from a fresh one.

Also record at each checkpoint: `uv run engine status` (lease, heartbeat
counts), `uv run engine store status` (per-table rows, retention counters and
`free_bytes` versus `database_bytes`), and confirmation that dispatch attempts
remain zero.

Reading the result honestly:

- above `150 MB/day` aggregated: hard failure. Record it, do not start the
  clock, do not adjust the budget;
- between `50` and `150 MB/day`: the target is not met. Investigate which
  store grows and why; this is not a pass;
- below `50 MB/day` and stable between 24 h and 48 h: proceed to the
  sleep/wake check and only then start the official fourteen days.

Deduplication counters near zero are expected on a house with cumulative
energy metering and are not themselves a failure (ADR-0011 Amendment 1.2).
The budget is the gate, not the dedupe rate.

Expect the Engine store to **plateau, not shrink**, once retention starts
pruning past the 24-hour horizon. Fresh stores are created with
`auto_vacuum=INCREMENTAL`, which returns pruned pages to the database's own
free list for reuse; nothing hands them back to the filesystem unless an
operator explicitly runs `engine store prune --vacuum`. A flat file size is
therefore the expected success signal. `engine store status` reports
`free_bytes` separately from `database_bytes`, which is what distinguishes
the two cases: a flat file with a growing free list means pages are being
reused as intended, while both growing together means the store is genuinely
still growing and the budget is at risk.

## 6. Daily monitoring

- `uv run engine status` — check `lease.expires_at` is advancing,
  `store_bytes`, and `last_heartbeat` (counts only: `cycles`,
  `rows_written`, `rows_confirmed`, `store_bytes`, `open_attempts`). Note
  that `store_bytes` here is the Engine store only, by design; the budget
  covers all three stores and is measured with the loop in §5a.
- `uv run engine store status` — per-table growth and retention counters.
- Growth budget (ADR-0011 Decision 7 as clarified by Amendment 1.1):
  compare the aggregated three-store total day over day. Target
  `< 50 MB/day`. Above target: investigate which store grows. Above
  `150 MB/day`: hard fail of M4; record the negative result, do not move
  the gate.
- The daemon appends one `runtime_heartbeat` per UTC day; a missing day
  means the daemon was down or asleep the whole day — explain it in the
  soak log either way.
- With `ENGINE_NTFY_TOPIC` set, the five runtime kinds arrive as
  count/status-only pushes (`runtime_started`, `runtime_stopped`,
  `runtime_lease_lost`, `runtime_circuit_open`, `runtime_heartbeat`).

Keep a dated soak log (one line per day is enough) next to the evidence.

## 7. Ending the soak

1. After ≥ 14 days, stop supervision: `launchctl bootout ...` (§4.5).
2. Record: start/end timestamps, the soak commit hash, the daily log,
   final `engine status` and `engine store status` output, the final
   three-store size measurement from §5a, and the soak databases themselves
   under `artifacts/evidence/M4/` (read-only). Copy a live SQLite database
   with `sqlite3 <db> ".backup <target>"`, never with `cp`.
3. Evaluate M4 against the `GOAL-0.2.md` criteria table: continuity
   (restarts recovered, no unexplained death), durable behavior/override
   signals, growth within budget. Record pass or fail honestly; a fail is
   recorded with the same care as a pass.
