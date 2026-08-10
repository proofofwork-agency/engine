# ADR-0002 — Plugin/world contract v2

- Status: accepted by explicit owner implementation direction
- Date: 2026-08-10
- Owner: project owner
- Scope: plugin identity, world state, capability and cognition seams

## Context

The v1 plugin seam registers a target adapter, flat capabilities and optional
brains. A target returns one opaque state object and may expose `execute()`.
That was sufficient to prove two worlds on one Heart, but it does not describe
entities, relations, evidence coverage, semantic effects or the boundary between
a proposed effect and an exact target command. A whole-house plugin would either
leak Homey strategy into Engine or leave the model with raw device operations.

Engine also needs plugin authors to depend on stable contracts without importing
the complete Heart runtime. Loading a plugin must remain inert: discovery may not
open a connection or mutate a target.

## Decision

1. `engine.plugin/v2` is a public, provider-neutral contract supplied by the
   dependency-light `engine-sdk` distribution.
2. Plugins declare a static `engine-plugin.toml` and a Python entry point in
   `engine.plugins`. The runtime compares the static declaration with the loaded
   manifest before enrollment.
3. The world contract uses stable `EntityV1`, `RelationV1`, `ObservationV1`,
   monotone `TargetObservationV2` and composed `WorldSnapshotV2` values. Evidence
   grade, source, time, unit, quality and coverage remain explicit.
4. Capability families are declared statically with `CapabilitySpecV2`. Dynamic
   devices instantiate those families. Unknown capabilities may be exposed as
   opaque observations but are read-only until a typed family is installed and
   enrolled.
5. Public plugin roles are separate:
   - `WorldProvider` discovers and observes;
   - `DomainController` converts a semantic desired effect into an exact request;
   - `Executor` dispatches only an authorized request;
   - `EffectOracle` reconciles pre-state, receipt and post-state;
   - `SpecialistBrain` returns typed advice and has no execute/authorize right.
   - optional `ExperienceProvider` publishes cursor-based `BehaviorBatchV1`
     values from a plugin-owned store. It cannot patch goals or grant authority.
6. A manifest may declare namespaced `PreferenceSpecV1` values. The SDK validates
   plugin ownership and capability-family binding; Heart validates signal values
   against the declared schema before linking them to a goal.
7. `IMMEDIATE`, `TASK` and `STREAM` are contract lifecycle modes. Homey uses
   `IMMEDIATE`; the warehouse reference proves durable `TASK` handles, polling,
   deadline cancellation and restart reconstruction.
8. V1 plugins remain loadable for compatibility but are observe-only in the v2
   world runtime. Autonomous mutation requires a matching v2 static manifest.
9. Plugin stores have their own identity and migration version. They do not share
   Engine's mutable operational tables.

## Alternatives considered

### Extend the v1 target dictionary with conventions

Rejected. Undocumented dictionary shapes cannot support conformance, enrollment
or independent effect measurement and would make Homey the accidental schema.

### Let every plugin provide arbitrary tools

Rejected. It collapses Engine into an LLM tool harness and makes capability,
authority and success semantics prompt-owned.

### Put SDK types in the Heart package only

Rejected. Plugins would depend on runtime storage/provider dependencies and the
contract could not be versioned or tested independently.

## Consequences

The contract is more verbose, but it exposes the information Heart needs to
compose a world and enforce mutation gates. Plugin authors gain a small SDK,
bootstrapper, deterministic fake and shared conformance suite. Homey-specific
entities and strategies remain outside core. A second non-house world can use the
same lifecycle without pretending its device semantics are identical.
Plugins without an `ExperienceProvider` keep the complete world/action lifecycle;
only behavioral learning is absent.

## Safety and scientific impact

The decision strengthens `missing != false`, preserves observation provenance,
and makes opaque capabilities non-actuating by default. Static/dynamic manifest
comparison detects capability drift before authority is expanded. Simulator
conformance is lifecycle evidence only and is not physical certification.

## Migration

V1 goals receive a target selector containing their current `target_id`. V1
plugins can be projected into read-only target observations. Mutation enrollment
requires an explicit v2 manifest and a new standing mandate bound to its version.

## Reversibility

V1 remains intact during the migration. The v2 package, tables and runtime can be
removed without rewriting v1 events. Persisted v2 goals and mandates would need
an export or explicit down-migration before removal.
