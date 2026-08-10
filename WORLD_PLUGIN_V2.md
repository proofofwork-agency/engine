# Engine World Plugin v2 — implemented vertical slice

Status on 2026-08-10: implemented, fake-world verified and live whole-world
observation verified. This document is an implementation map, not a claim that
the live Homey actuation gate has passed.

## What now works

Engine has a canonical `engine.plugin/v2` runtime; v1 remains compatibility only:

- one durable `WorldSnapshotV2` composed from multiple target providers;
- multi-target `GoalSpecV2` and persistent standing mandates;
- the full proposal → request → policy → authorization → receipt → fresh
  observation → effect lifecycle;
- declarative condition data with units, Boolean composition, change, duration,
  windows and counts;
- a bounded model projection while the complete world remains local and durable;
- deterministic reuse of an observed-successful typed plan;
- zero executive-model calls while a maintained world remains observed stable;
- optional plugin-neutral `ExperienceProvider` imports with durable cursors,
  exactly-once signal storage and unlinked evidence for unknown declarations;
- namespaced `PreferenceSpecV1` values and the fixed evidence → candidate →
  seven-day shadow → versioned GoalSpec → rollback route;
- additive scoped routine guards, real counterfactual shadow opportunities,
  durable recurrence/cooldown/conflict state and exact routine rollback;
- persistent owner-enrolled low-risk autonomy profiles with 24-hour exact
  derived submandates and immediate disable/revoke behavior;
- v1 goals migrated to observe-only target selectors;
- generic immediate/task/stream contract values, durable task wake records and
  a tested task start → poll/cancel → post-observe lifecycle that reconstructs
  after process restart.

The public types and plugin protocols live in dependency-light `engine-sdk`.
`engine-heart` owns the generic cycle and store. The separately installable
`engine-runtime` package owns entrypoint discovery, the `engine` CLI, SQLite
runtime lease, signals and model composition.

## Proof worlds

`plugins/reference-world` is a non-house warehouse with a durable asynchronous
crate-transfer task and independent effect oracle. It runs through the same
Heart without a core fork and reconstructs after process restart.

`plugins/engine-context` provides local time, scheduled wakes, explicitly
confirmed location and optional provider-neutral weather. Missing location or
network becomes `UNKNOWN`; location is sent to weather only after explicit
consent.

`plugins/engine-homey` projects all discovered Homey zones, devices, sensors,
meters and camera detection signals as entities, relations and observations.
Lighting, switch, cover and climate are declared families. Only families backed
by a loaded controller, executor and oracle can mutate; unknown dynamic families
remain opaque/read-only.

The deterministic fake proves one Homey plus context in a single snapshot,
three generic lighting zones, eight camera entities, lux/power reconciliation,
ACK-without-effect failure, missed-event recovery and cognitively quiet stable
monitoring. No room- or brand-specific Python branch is used.

Homey and the warehouse also pass the same automatic learning route. Homey
publishes external brightness changes in declared five-percent bands; Engine
dispatches are suppressed. The warehouse publishes an independent crate target.
Both promote only through the generic gate, survive restart and change the next
typed specialist proposal.

The implemented Homey routine tranche is lighting-only: daily zone-off,
presence-plus-darkness lighting-band activation and continuous-fresh-absence
zone-off. `lighting.any_on` and `presence.inactive_seconds` are derived only
from covered observations; missing continuity remains `UNKNOWN`. Routine shadow
performs no dispatch. Switch, cover and climate contracts are not enrolled by
the autonomy profile.

The read-only live proof used the already-authorized official Homey CLI session
and composed Homey plus local context into one snapshot: 2 targets, 21 zones,
65 non-camera devices, 8 camera entities, 15 camera-detection signals and 442
observations. Provider failures and mutation attempts were both zero. The
sanitized result is stored in
`artifacts/experiments/EXP-2026-002-world-v2/live-world-observe.json`.

## Brain provider seam

The runtime does not depend on a model vendor. `NaturalIntentCompilerV2` and
`ModelExecutiveBrainV2` accept untrusted structured output through small
provider protocols. The deterministic brain uses the same proposal boundary in
tests.

No model family is fixed in core. `engine-runtime` supplies one stateless
OpenAI-compatible structured-output adapter for both GoalSpec compilation and
world decisions. The Meta Model API / Muse Spark 1.1 path is contract-tested as
the actual `ModelExecutiveBrainV2`; a live call remains opt-in through
`META_MODEL_API_BASE_URL`, `META_MODEL_API_KEY` and `META_MODEL_ID`. Every model
output remains an untrusted proposal and provider failure is isolated per goal.

Local OpenAI-compatible servers use `ENGINE_LOCAL_MODEL_BASE_URL` and
`ENGINE_LOCAL_MODEL_ID`. Only loopback URLs may omit an API key; remote URLs
remain fail-closed. Gemma 3 4B IT Q4_K_M is the measured small all-round option
for llama.cpp, not a core dependency: another schema-valid local provider can
replace it. Gemma 3 1B passed the executive-brain route quickly but failed the
semantic GoalSpec smoke test, so it is only suitable for the narrower routing
role unless a stronger intent compiler is composed alongside it.

## Still unmeasured

- no v2 physical Homey mutation was performed in this implementation run;
- the five consecutive live lux/watt trials remain open;
- the natural-intent ambiguity test and Meta path have contract-model evidence;
  a credentialed Meta API canary remains open;
- OpenClaw/Hermes comparison is preregistered but not executed;
- stream reconnect has contract/store scaffolding but no end-to-end reference
  proof yet; the non-Homey task lifecycle is covered through poll, deadline
  cancellation and process-restart recovery.

The next decisive step is therefore one low-energy live lighting zone using the
same v2 lifecycle, followed by five measured repetitions—not more core design.
