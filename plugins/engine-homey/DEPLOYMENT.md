# HomeOps deployment and evidence protocol

This runbook separates software conformance from evidence gathered on one real
Homey Pro. Passing the fake suite does not authorize or certify a live home.

## 1. Whole-house observe

1. Create a PAT with `homey.zone.readonly` and `homey.device.readonly` only.
2. Keep `mode = "observe"`; do not set `ENGINE_HOMEY_ARMED`.
3. Run `engine-homey discover` repeatedly and compare the stable aliases,
   capability types/units, availability and timestamps with Homey.
4. Disconnect Homey once. The command must fail explicitly and must not present
   the last stored snapshot as a new observation.
5. Confirm the plugin database and Engine database are distinct files.

## 2. First low-energy closed loop

Use one bounded zone with one lamp, one lux sensor and one power measurement.
Disable Homey Flows that can mutate those test devices. Add only those device IDs
and capabilities to `control`; set conservative brightness and watt limits.

Only after the owner confirms the fixture and stop method:

1. add `homey.device.control` to the PAT;
2. set `mode = "act"`;
3. export `ENGINE_HOMEY_ARMED=1` for this process;
4. compile the charter and run `engine-homey run`;
5. remove arming immediately after the bounded session.

For each of five consecutive runs, record starting lux, motion/presence evidence,
each invocation ID, terminal receipt state, post-observation revision, final lux,
maximum watts and any manual intervention. The gate passes only when all five
runs enter the configured lux band without exceeding the watt budget. A Homey ACK
without sensor change is a failure, not a pass.

## 3. House-wide lighting

Add at least three zones through data bindings only. Do not add zone-specific
Python branches. Re-run discovery and the same charter. Confirm stable monitoring
causes observations but no new `brain_request` events. Test a manual light-off and
a missed event; polling must restore the violated charter in both cases.

## 4. Climate, covers and energy

Enable each new capability family separately with target-specific ranges. Covers
use a normalized ratio where the configured mapping documents what 0 and 1 mean;
verify this on the actual device before act mode. Thermostat limits and any
device-local safety behavior remain authoritative. Climate may wait for new
temperature evidence after passive/active actions; it must not repeat a command
merely because cooling is slow.

## 5. Preference evidence

Apply one direct correction with `engine-homey correct`, inspect the new charter
version and reproduce an equivalent later situation. An unexplained external
Homey control change may be recorded as `INFERRED` and unattributed; it must leave
the active charter unchanged.

## Optional restart appendix

Kill/restart is a fault test, not the product story. After restart, verify aliases
are unchanged, revisions never regress, the permanent goal resumes, and a
pre-crash uncertain dispatch is not blindly retried.

## Rollback and stop

- Stop the Engine process; device-local controllers and Homey remain authoritative.
- Remove `ENGINE_HOMEY_ARMED` or return to `mode = "observe"`.
- Revoke the PAT if scope or host integrity is in doubt.
- Restore the prior charter by recompiling its preserved source text. Charter and
  preference history remain in the plugin database for audit.
- Do not describe software policy as a substitute for electrical, thermal or
  device-provided safety interlocks.
