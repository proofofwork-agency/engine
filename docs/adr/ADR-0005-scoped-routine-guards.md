# ADR-0005 — Scoped routine guards above GoalSpecV2

- Status: accepted by explicit owner implementation direction
- Date: 2026-08-10
- Owner: project owner
- Scope: routine contracts, guard evaluation, recurrence, conflicts and Heart order

## Context

`GoalSpecV2` describes an effect that should hold. It does not describe when a
recurring effect should become active. Existing `ConditionV1` evaluation inherits
one selector, so it cannot safely express a guard combining local time with a
specific Homey or warehouse entity. Putting Homey conditionals in Heart would
break the plugin contract and make routine semantics device-specific core state.

## Decision

1. `RoutineSpecV1` is a durable activation layer above one linked `GoalSpecV2`.
   It never replaces the goal, policy, authorization, executor or oracle.
2. `ScopedConditionV1` is a condition AST whose every leaf carries its own exact
   entity selector. Boolean nodes carry only children. This permits one guard to
   combine independently sourced targets without an inherited wildcard.
3. Static `RoutineTemplateSpecV1` declarations bind template identity,
   capability family, schemas, deterministic priority and shadow gate. An
   optional plugin `RoutineCompiler` translates pattern semantics into inert
   RoutineSpec/GoalSpec data and cannot create a mandate.
4. Heart evaluates routine authority and guard before every linked goal:
   - false becomes `dormant` with zero brain calls and zero actions;
   - `UNKNOWN`, `STALE` or `CONFLICTING` becomes `guard_uncertain` and stops;
   - true may enter the existing GoalSpec lifecycle;
   - a triggered multi-step occurrence remains latched only until the linked
     desired effect is independently observed or authority fails.
5. Same-scope, opposite desired states conflict. Equal highest priority blocks
   all conflicting routines. Otherwise one deterministic highest priority wins.
6. Recurrence occurrences are durable. A daily key uses the observed local date,
   so fall-back clock duplication executes once and a nonexistent spring-forward
   time is skipped because no qualifying observation exists.
7. Cooldowns, override ownership and hourly action limits are durable gates.
   They do not convert missing evidence into false.
8. Core interprets guard/recurrence/lifecycle contracts only. Homey lighting,
   warehouse or future domain meaning stays in plugin templates and compilers.

## Alternatives considered

### Put schedule and presence fields into GoalSpecV2

Rejected. A goal is the desired state; conflating activation with the desired
state makes stable-goal evaluation and reusable policies ambiguous.

### Let the general brain decide whether a routine fires

Rejected. Routine activation is deterministic operational state. A model may
describe or rank candidates but is neither a clock, sensor nor authority source.

### Add Homey branches to Heart

Rejected. The same runtime tests are parameterized with non-Homey identities and
no core conditional names a Homey template or observation property.

## Consequences

Routine evaluation adds a small durable state machine and occurrence ledger.
Triggered routines still pay every existing lifecycle cost. Stable dormant
routines are cognitively quiet. Multi-step zone-off actions survive restart
without treating one acknowledgement as whole-zone success.

## Safety and scientific impact

Guard uncertainty is fail-closed. Shadow dispatch count is structurally fixed at
zero. DST, restart, conflict and stale-evidence behavior are deterministic test
oracles rather than model judgments.

## Migration

Existing goals have no linked routine and execute unchanged. Existing
`ConditionV1`, preference signals and plugin manifests deserialize unchanged;
new routine manifest sections are additive.

## Reversibility

Removing or suspending a routine leaves its GoalSpec, receipts, evidence and
occurrences auditable. Routine rollback abandons the linked goal, revokes its
submandate and invalidates its plan cache.

