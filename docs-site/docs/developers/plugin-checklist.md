---
title: Plugin checklist
description: Enrollment and review checklist for an engine.plugin/v2 plugin.
sidebar_position: 6
---

# Plugin checklist

Use this checklist before allowing a plugin to observe or mutate. A check means
there is code and appropriate evidence; a manifest claim alone is insufficient.

## Identity and packaging

- [ ] `plugin.id` is stable, dotted, lowercase, and not derived from free text.
- [ ] `version`, `engine_api`, and `contract_version = "engine.plugin/v2"` are set.
- [ ] `pyproject.toml` declares exactly one appropriate `engine.plugins` entry point.
- [ ] `engine-plugin.toml` is present in both wheel and editable installation.
- [ ] Import and factory invocation are inert: no network, mutation, or background thread.
- [ ] The static manifest and `plugin.manifest` match exactly where the runtime requires it.
- [ ] Target and entity IDs are canonical and stable across restart.
- [ ] The plugin store has its own `identity` and positive `schema_version`.

## Needs and secrets

- [ ] Network, filesystem, secret, and privacy needs are declared minimally.
- [ ] No secret appears in a manifest, observation, receipt, log, or model context.
- [ ] External transmission of private data requires explicit opt-in.
- [ ] The plugin fails closed when credentials or consent are absent.
- [ ] The deployment documents additional OS or container isolation.

The current Engine runtime does not yet enforce `[needs]` through a general
sandbox and does not verify cryptographic artifact signatures. Do not present
these open gaps as completed security controls in the plugin README.

## World observation

- [ ] `WorldProvider` declares polling and freshness intervals.
- [ ] Target revisions are monotonic and survive or reconstruct after restart where required.
- [ ] Entities, relations, and observations reference only valid stable IDs.
- [ ] Every observation includes source, time, evidence grade, relevant units, and coverage.
- [ ] `quality` and `confidence` remain separate from evidence grade.
- [ ] Missing data becomes `UNKNOWN` or unavailable, not automatically `false`.
- [ ] Stale data is treated as `STALE` for mutating decisions.
- [ ] Provider failures retain last-known state plus explicit failure and staleness.
- [ ] An event schedules a wake; a fresh observation remains authoritative.

## Capabilities

- [ ] Every family has a stable ID, version, and description.
- [ ] `input_schema` describes the concrete request; `effect_schema` describes the semantic proposal.
- [ ] `control_layer`, `invocation_mode`, risk, and privacy are explicit.
- [ ] Units, preconditions, deadlines, limits, and recovery are explicit.
- [ ] Idempotency is honest: use `false` if retrying may duplicate an effect.
- [ ] `effect_measurements` name the observations that can support success.
- [ ] Dynamically unknown families remain opaque and read-only.

## Mutation path

- [ ] Every mutating plugin declares a provider, controller, executor, and oracle.
- [ ] The controller cannot switch target, entity, goal, or capability.
- [ ] The request binds the current snapshot, world revision, and target revision.
- [ ] Parameters pass JSON Schema and capability limits.
- [ ] Preconditions fail closed on `UNKNOWN`, `STALE`, or conflict.
- [ ] The executor checks request-bound authorization.
- [ ] Authorization has exact scope and a short expiry.
- [ ] Lost ACK, timeout, duplicate ACK, and partial execution are tested.
- [ ] Receipt states are explicit; ambiguity becomes `unknown`.
- [ ] The oracle uses pre-state, receipt, and fresh post-state.
- [ ] An ACK alone can never produce `achieved = true`.
- [ ] Recovery or safe-state success is observed again.

## `immediate`, `task`, and `stream`

- [ ] `immediate`: terminal receipt and post-observation are tested.
- [ ] `task`: durable external handle, polling, deadline cancellation, and restart recovery are tested.
- [ ] `stream`: cursor, reconnect, deduplication, deadline, and restart are tested end to end.

Engine currently has a reference proof for `task`. For `stream`, contract and
store scaffolding exist, but there is no general end-to-end reference. Do not
claim stream production readiness based on the enum alone.

## Brains

- [ ] Specialist ID and `supported_families` are stable and declared.
- [ ] Advice is typed and can express unsupported or defer.
- [ ] A specialist returns only advice or a proposal and owns no executor.
- [ ] Model output is schema-validated as untrusted data.
- [ ] Provider/model ID, projection hash, latency, and output are recorded for audit.
- [ ] Core correctness and the safe fallback work without a model provider.

## Experience and routines

- [ ] Experience is optional; its absence does not break the normal lifecycle.
- [ ] The provider uses an opaque cursor and duplicate-free signal IDs.
- [ ] Preferences are namespaced under `<plugin-id>.preference.*`.
- [ ] Preference values have a JSON Schema and capability binding.
- [ ] Signals include provenance and remain `OBSERVED` or `INFERRED` as warranted.
- [ ] A signal cannot add a mandate, target, family, risk, privacy, or authority.
- [ ] Routine templates have pattern, guard, and goal schemas plus a fixed priority.
- [ ] Every scoped guard leaf has an exact entity selector.
- [ ] Shadow dispatch count is structurally zero.
- [ ] Promotion uses real opportunities, independently observed agreement, and conflict checks.
- [ ] Automatic routine promotion requires exact low-risk owner delegation; otherwise it requires approval.
- [ ] Every promotion has an exact rollback patch and invalidates stale plan cache entries.

## Tests

- [ ] `engine-plugin validate .` succeeds.
- [ ] `engine-plugin inspect .` shows only intended declarations.
- [ ] `engine-plugin test .` passes the generated or shared contract test.
- [ ] A deterministic fake covers observe, controller, executor, and oracle.
- [ ] Conformance runs against every adapter implementation.
- [ ] Restart or replay produces the same relevant state.
- [ ] Stateful tests cover invalid sequences and crash boundaries.
- [ ] Fault tests cover network loss, timeout, duplicate response, and partial failure.
- [ ] No test uses sealed evaluation data as a debugging fixture.
- [ ] Physical tests begin low-energy and bounded, with an independent stop mechanism.

## Documentation and claims

- [ ] The README names supported targets and versions, and exact units.
- [ ] The README describes failure, fallback, and recovery behavior.
- [ ] Simulator evidence is not presented as physical safety or certification.
- [ ] Unimplemented marketplace, signing, sandboxing, or stream E2E remains documented as a gap.
- [ ] Plugin semantics do not leak into the Heart or runtime as a special branch.
- [ ] A lifecycle, authority, or adapter-contract change has the required ADR.

