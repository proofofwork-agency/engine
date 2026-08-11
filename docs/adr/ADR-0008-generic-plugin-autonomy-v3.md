# ADR-0008 — Generic plugin autonomy v3

- Status: accepted by explicit owner implementation direction
- Owner: project owner
- Date: 2026-08-11

## Context

Engine's earlier `AutonomyProfileV1` was a Homey-specific authority envelope for
routine promotion. It did not provide a generic way for a plugin to contribute
bounded autonomous behavior without starting another agent loop or leaking
domain identities into Heart. The owner wants every current plugin to conform to
one autonomy-capable contract, while keeping operational state, scheduling,
cognition, policy, authorization, dispatch, and effect verification in Engine.

## Decision

1. `engine.plugin/v3` extends the v2 world contract. Every v3 manifest declares
   an `[autonomy]` table, including plugins with empty strategy and template
   lists. A v2 plugin without autonomy remains loadable.
2. Plugins may declare proposal-only `AutonomyStrategy` implementations, typed
   `GoalTemplateSpecV1` values, inert `GoalTemplateCompiler` implementations,
   and bounded specialists. Strategies return only `NOOP`, `DEFER`,
   `PROPOSE_EFFECT`, `PROPOSE_GOAL_CANDIDATE`, `REQUEST_EXECUTIVE`, or
   `REQUEST_SPECIALIST`. They receive only `AutonomyContextV1`, not executor,
   policy, authorization, registry, model, or plugin handles.
3. Engine owns one Heart lifecycle. Heart observes one previous/current world
   boundary, recovers in-flight work, evaluates goals/routines/enrollments once,
   arbitrates resources, revalidates, and admits at most one mutation per
   `(target, entity, conflict_domain)` resource.
4. An `AutonomyEnrollmentV2` freezes exact targets, entities, capabilities,
   templates, context plugins, privacy grants, cognition route, risk, limits,
   budget, expiry, privileges, and manifest/strategy/template fingerprints.
   Wildcards are forbidden. Overlapping enabled enrollments are rejected.
5. Privileges are separate: control existing goals, instantiate declared goal
   templates, and promote proven routines. A proposal never implies any of
   these privileges.
6. Modes are `OBSERVE`, `SUPERVISED`, `DELEGATED`, and `PAUSED`.
   `OBSERVE` persists real shadow evaluations with zero dispatch;
   `SUPERVISED` persists proposals and approval reobserves and reevaluates;
   `DELEGATED` permits low-risk enrolled work; `PAUSED` preserves observation,
   learning, and recovery while starting no strategy, cognition, or dispatch.
7. Cognition routes are deterministic, executive, specialist, or hybrid.
   Deterministic makes no brain call. Hybrid evaluates the deterministic
   strategy first and admits at most one explicitly requested executive or
   specialist call. Strategy and cognition receive the same bounded context.
8. Goal creation is template-bound. A free-form `SuggestionV1` is explicitly
   non-operational and can become executable only after an owner or later plugin
   version adds a typed template.
9. Delegated v1 risk is at most `low`, and mutations remain plugin-owned.
   Cross-plugin context is allowed only when enrolled; cross-plugin mutation is
   rejected. Plugins are trusted in-process code for this release.
10. Evaluation, proposal, request, policy decision, and authorization carry the
    same mode epoch, enrollment revision, context fingerprint, and
    manifest/strategy fingerprints. Fresh mode, enrollment, lease, authorization
    expiry, request hash, target revision, capability, privacy, and risk gates
    are checked again immediately before external I/O.
11. `engine yolo enable|disable|status` is only an alias for delegated, paused,
    and autonomy status. It creates no enrollment. Stored legacy
    `AutonomyProfileV1` records remain audit data and grant no generic authority.

## Alternatives

- Give each plugin an agent loop or direct tool access: rejected because it
  creates multiple Hearts and allows proposal providers to bypass authority.
- Put target-specific strategies in core: rejected because generic lifecycle is
  not generic device semantics.
- Allow free model-created goals: rejected for this release because typed
  template identity is the executable boundary.
- Treat model confidence as observation: rejected; only identified providers
  and oracles establish effects within their coverage.
- Isolate every plugin in a process now: deferred. In-process code is a declared
  trust limitation, not a security claim.

## Consequences

Reference warehouse reserve maintenance and Homey enrolled lighting use the
same registry, context, enrollment, scheduling, policy, and lifecycle code with
different plugin semantics. Stable worlds produce no repeated strategy or
brain calls. Adding higher risks, overlapping-resource arbitration, Engine-owned
cross-plugin workflows, richer multi-hop cognition, or process isolation
requires a later owner decision, ADR, and evidence.

## Safety and scientific impact

The change does not turn strategies, models, specialists, compilers, or Cells
into authorities. Dispatch still requires typed validation, deterministic
policy, an expiring authorization, fresh observation, and an independent effect
oracle. Fake/simulation tests establish software behavior only. The existing
physical Homey evidence boundary does not move.

## Migration and reversibility

Built-in plugins migrate to v3 and explicitly declare empty or bounded autonomy
roles. Third-party v2 plugins remain loadable without autonomy. Operators must
create exact enrollments explicitly; switching to delegated mode alone grants no
scope. Disable an enrollment or select `PAUSED` to stop new mutations while
retaining recovery and audit data. Rolling back code leaves typed v3 records as
inert audit data for older runtimes that do not read them.
