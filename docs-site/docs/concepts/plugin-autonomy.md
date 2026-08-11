---
title: Generic plugin autonomy
sidebar_position: 6
description: Modes, enrollment, templates, cognition routing, recovery, and authority in engine.plugin/v3.
---

# Generic plugin autonomy

`engine.plugin/v3` lets a plugin contribute bounded strategy and goal-template
semantics while the single Engine Heart retains scheduling, cognition routing,
policy, authorization, dispatch, recovery, and effect verification. A strategy
is a proposal provider. It is never an executor or authority source.

> **Status:** the contracts and generic software routes are **Implemented** and
> **Fake/simulation-tested** with the reference warehouse and Homey plugins.
> Plugins are currently trusted in-process Python code. Higher-risk delegation,
> overlapping enrollment arbitration, process isolation, and live physical
> proof remain **Roadmap**.

## Modes

| Mode | Evaluation | Cognition | New dispatch |
| --- | --- | --- | --- |
| `OBSERVE` | Durable shadow | Only if the enrolled route explicitly requests it | Never |
| `SUPERVISED` | Durable pending proposal | Bounded to the route | Only after approval reobserves and reproduces the proposal |
| `DELEGATED` | Live enrolled evaluation | Bounded to the route | Only inside an enabled exact low-risk enrollment |
| `PAUSED` | No new strategy evaluation | None | None; observation, learning, and in-flight recovery continue |

`engine yolo enable` is an alias for `engine autonomy mode delegated`.
`engine yolo disable` selects `paused`. Neither command creates or widens an
enrollment.

## What an enrollment freezes

An `AutonomyEnrollmentV2` records exact:

- plugin and proposal-only strategy;
- target and entity IDs, with no wildcards;
- capability families and their `conflict_domain` resources;
- goal template IDs and separate privileges for existing goals, template
  instantiation, and proven routine promotion;
- cross-plugin context sources and privacy grants;
- deterministic, executive, specialist, or hybrid cognition route;
- risk ceiling, limits, budget, expiry, and manifest/strategy/template
  fingerprints.

The delegated release ceiling is `low`. A plugin can consume explicitly enrolled
context from another plugin but can mutate only its own declared capabilities.
Overlapping `(target, entity, conflict_domain)` enrollments fail closed.

## Strategy contract

An `AutonomyStrategy` receives one bounded `AutonomyContextV1` and returns one
`AutonomyDecisionV1`:

```text
NOOP | DEFER
PROPOSE_EFFECT | PROPOSE_GOAL_CANDIDATE
REQUEST_EXECUTIVE | REQUEST_SPECIALIST
```

It receives no executor, authorization, policy, registry, model, plugin, or
scheduling handle and cannot start a decision loop. Deterministic routes make
zero brain calls. A hybrid route always runs deterministic evaluation first and
then makes at most one explicitly requested executive *or* specialist call.
Both cognition roles see the same bounded context projection.

Model failure, a stale context, missing privacy grant, unsupported specialist,
or route expansion produces `DEFER`. A `SuggestionV1` may contain free-form
model ideas, but it is inert: it cannot create a mandate, goal, proposal, or
dispatch.

## Typed goal creation

New executable goals must start as a `GoalCandidateV1` naming a statically
declared `GoalTemplateSpecV1`. The plugin's inert compiler may produce exactly
one `GoalSpecV2` effect inside the enrolled entity, capability, risk, and
parameter scope. Heart creates the exact derived mandate and then runs the
normal lifecycle. Unknown templates, free GoalSpecs, scope expansion, or
fingerprint drift are rejected.

## Approval and delegated dispatch

In supervised mode approval is not a delayed executor call. Heart first observes
again, checks the current mode and enrollment, reruns the strategy, and compares
the operational decision. A changed proposal supersedes the old one.

Every admitted mutation binds the same mode epoch, enrollment revision,
evaluation, context fingerprint, and manifest/strategy fingerprints to the
proposal, request, policy decision, and authorization. Immediately before I/O,
Heart checks those values again together with authorization expiry, the request
hash, the live runtime lease, and resource availability.

## Crash recovery

Before external I/O Heart durably stores a `DispatchAttemptV1` with a stable
operation key. A crash after an effect but before a receipt therefore does not
look like permission to retry. On restart Heart observes first and marks an
ambiguous prepared attempt `RECOVERY_REQUIRED`; it never blindly redispatches.
Task handles continue through the existing fenced poll/cancel recovery route.
An open attempt reserves its resource until observation and reconciliation make
the outcome explicit.

The invariant remains:

```text
observe -> propose -> validate -> policy -> authorize
        -> durable attempt -> dispatch -> observe -> oracle
```

An ACK, tool result, model verdict, or neural verifier does not independently
prove the effect.

## Cells and future growth

A Cell may later implement a bounded specialist, but not a second executive or
runtime. Engine Cell starts only after a deterministic/classical baseline shows
a measured deficit, followed by a local runner, held-out evaluation, resource
envelope, specialist adapter, and authority-free shadow evidence.

See
[ADR-0008](https://github.com/proofofwork-agency/engine/blob/main/docs/adr/ADR-0008-generic-plugin-autonomy-v3.md)
and
[ADR-0009](https://github.com/proofofwork-agency/engine/blob/main/docs/adr/ADR-0009-lease-fenced-crash-safe-dispatch.md)
for the complete decisions and release boundaries.
