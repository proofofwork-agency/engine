# ARCHITECTURE_GUARDRAILS.md — Engine Design Considerations

> Repository-root architectural guidance. Narrower local rules may only strengthen it.

## 1. Why this file exists

Engine can accidentally become unsafe while every individual shortcut looks convenient:

- “Let the LLM send the command directly.”
- “Remember approval in the chat.”
- “Retry; it probably did not move.”
- “The simulator passed, so the robot is safe.”
- “Every device can use one generic action schema.”
- “Add a small neural net and call it adaptive.”
- “Let Umwelt own the whole loop.”

These choices erase authority, evidence and timing boundaries. Review the considerations below whenever architecture changes.

## 2. Structured state versus conversation

Preferred: canonical snapshots, observations, capability state, policy decisions, authorizations and receipts.

Allowed: bounded textual projections generated from canonical state.

Avoid: prompt history or summaries as state.

Review question: if every model conversation vanished, could Engine reconstruct what targets existed, what was authorized, what was attempted and what was observed?

## 3. Intent versus command

Human language is ambiguous. A target command must not be.

Keep explicit transformations:

```text
intent -> GoalSpec -> ProposedAction -> validated ActionRequest -> authorized dispatch
```

Do not let a natural-language string cross the executor boundary as an instruction.

## 4. Proposal versus authorization

Proposals can originate from humans, models, search, rules or Umwelt. Authorization originates only from policy plus an approved principal/process.

An authorization must be scoped and expiring. Reusing “the user said yes earlier” is not an authorization mechanism.

## 5. Deliberative versus realtime control

LLM latency, nondeterminism and failure modes are incompatible with hard-realtime stabilization. Engine should issue high-level bounded setpoints or skill invocations to controllers that enforce their own timing and limits.

Review question: if the LLM call stalls for 60 seconds, does the target remain safe?

## 6. Policy versus independent safety

Policy decides whether Engine may request an action. Device safety decides whether the target can execute it safely right now. Neither subsumes the other.

Emergency stops, watchdogs and interlocks must not depend on the same process, network or model as the command path when independence is required.

## 7. Generic runtime versus domain semantics

Standardize:

- lifecycle;
- contracts;
- provenance;
- policy decisions;
- receipts;
- audit;
- conformance mechanisms.

Do not flatten:

- coordinate frames;
- units;
- dynamics;
- deadlines;
- risk classes;
- safe states;
- regulatory requirements.

An honest adapter exposes differences rather than hiding them in strings or arbitrary maps.

## 8. Capability discovery versus trust

A target claiming a capability does not prove it is authorized, healthy or conformant. Keep separate:

- advertised capability;
- verified adapter compatibility;
- current availability;
- policy permission;
- authorization for this invocation.

## 9. Observed versus predicted state

Sensor values and receipts have coverage and can be wrong; predictions have uncertainty and can be useful. They remain different evidence classes.

Never populate an observed field from an LLM explanation merely because no sensor value exists.

## 10. Missing, stale and conflicting evidence

Safety-relevant missing evidence should normally fail closed or defer. Stale evidence is not current evidence. Conflicting sensors require an explicit resolution or stop path.

Do not encode these cases as a default boolean false.

## 11. Snapshot and precondition semantics

Every mutating action needs a clearly defined observation boundary and preconditions. Bind requests or authorizations to the relevant state identity.

Do not execute a plan against a changed world merely because the action schema still validates.

## 12. Event replay versus current snapshots

An append-only receipt/observation log improves audit and recovery; a current snapshot improves operational queries. Whichever persistence design is chosen, maintain an independent reconstruction path:

```text
replay(events to boundary) ~= materialize(full state at boundary)
```

Define equivalence and tolerated nondeterministic fields explicitly.

## 13. Idempotency versus retries

Network delivery and device execution are different facts. A timeout may mean “not executed”, “executed but acknowledgement lost” or “partially executed”.

Use command IDs, device-supported deduplication, reconciliation and target-specific recovery. Never blindly retry a non-idempotent physical action.

## 14. Receipt versus success

“Request accepted” is not “effect achieved”. Model receipt lifecycle explicitly, such as:

```text
CREATED -> AUTHORIZED -> DISPATCHED -> ACKNOWLEDGED
-> OBSERVED_SUCCEEDED | OBSERVED_FAILED | PARTIAL | UNKNOWN | CANCELLED
```

The exact state machine requires an ADR. Do not infer a terminal success from the absence of an error.

## 15. Rollback versus compensating action

Software rollback can often restore bytes. Physical worlds may be irreversible. A compensating action is a new action with its own risk, authorization and possible failure.

Never promise rollback generically across device classes.

## 16. Simulation versus hardware evidence

Simulation is excellent for contracts, state machines, fault injection and wide test generation. It is incomplete for latency, calibration, mechanics, sensor noise and environmental interaction.

Label evidence by environment. Hardware claims require hardware evidence; certification requires the applicable external process.

## 17. Fault injection versus accidental hazard

Inject disconnects, stale telemetry, timeouts and corrupt messages in fakes/simulators first. On hardware, constrain energy and workspace and preserve a human-controlled independent stop.

Do not create a real dangerous condition solely to test whether software catches it.

## 18. LLMs versus deterministic tools

Use schema validators, policy engines, type systems, planners, simulators and device controllers for facts and guarantees they can establish. Use LLMs for ambiguity resolution and proposal generation.

If replacing the LLM changes authorization or truth semantics, provider coupling leaked into core.

## 19. Skills versus capabilities

A capability states what can be requested. A skill is one implementation strategy. Multiple skills may implement the same capability.

Do not let a skill redefine the contract, units or safety envelope at runtime. Selection is a bounded decision with evidence and policy, not model whim.

## 20. Mini-brains versus universal intelligence

Small models can be valuable for narrow perception, anomaly detection or control residuals. They are not identities, permissions, observations or general world models.

Start with a measured baseline. Document supported scope, uncertainty, training provenance, edge performance and fallback. Remove the learned path when it does not earn its complexity.

## 21. Training versus state update

Keep four layers distinct:

1. live target state updates immediately;
2. experience appends after observed outcomes;
3. target-specific adaptation is periodic and optional;
4. base model training is a separate versioned process.

Do not market adding a row or calibrating a sensor as neural learning.

## 22. Local-first versus cloud dependence

Safety-critical observation, policy and execution should survive loss of an optional cloud provider when the use case requires offline operation. Cloud services may train, synchronize or provide heavier cognition, but their outage behavior must be explicit.

Track transmitted data, latency, cost and provider version.

## 23. Provider abstractions versus lowest-common-denominator design

Core semantics must be provider-independent, but adapters may expose typed optional features. Avoid both SDK leakage and an untyped `dict[str, Any]` abstraction that destroys guarantees.

## 24. Caches versus hidden truth

Every correctness-relevant cache needs key semantics, source version, invalidation, isolation and reconstruction tests. Until such a contract exists, caches stay off the correctness path.

## 25. Audit logs versus free-form logs

Important decisions need structured links among:

```text
principal
target
snapshot/preconditions
proposal source
policy version and decision
authorization
adapter and skill version
dispatch
telemetry/observations
receipt
effect delta
```

Natural-language logs are supplementary views, not the audit record.

## 26. Explanations versus evidence

An explanation must label observed, derived, inferred and unknown claims. A fluent causal story cannot upgrade evidence.

## 27. Multi-step workflows versus open-ended agents

Bounded workflows may have explicit states, budgets, approvals and stop conditions. Avoid recursive model-controlled loops with hidden memory or expanding tool authority.

For changing worlds, default to one consequential action, re-observe, then replan.

## 28. Environment adapters versus Umwelt

Engine owns execution and safety. Umwelt may serve through a `WorldModelPort` and provide state/dynamics/planning evidence.

Avoid:

- a shared mutable database;
- circular imports;
- Umwelt issuing authorizations;
- Engine presenting unvalidated Umwelt prediction as observation;
- broadening Umwelt's software research scope to satisfy Engine product needs.

## 29. Fast product path versus exact oracle

Keep a slow, simple reference path for reconstruction, policy evaluation and adapter conformance. Optimize only after correctness is measurable.

Incremental latency wins do not justify removing the exact oracle.

## 30. Claims versus demonstrations

Allowed after matching evidence:

- “this adapter passes version X conformance fixtures”;
- “this target stopped within X ms under the stated setup”;
- “this skill improved metric Y over baseline Z on the sealed split”;
- “this workflow completed with no unauthorized dispatches in N controlled trials.”

Avoid “controls anything”, “safe”, “autonomous” or “learns any device” without operational definitions and broad evidence.

## 31. Architectural smell checklist

Escalate review when you see:

- raw natural language reaching an executor;
- a model or planner creating its own authorization;
- raw actuator commands from cloud/LLM output;
- one process owning planning, safety stop and device watchdog without justification;
- provider SDK types in core storage;
- target-specific units inside untyped maps;
- acknowledgement treated as observed success;
- blind retries after timeout;
- no `UNKNOWN`, `PARTIAL` or `DEFER` path;
- simulator evidence presented as a physical guarantee;
- a mini-brain with no baseline or dataset provenance;
- a cache not covered by reconstruction/isolation tests;
- a mutable singleton shared across targets;
- no reference state reducer;
- candidate generation embedded inside authorization;
- an Engine/Umwelt shared mutable store;
- prompts spreading through policy or executor modules;
- “the model remembers” in a correctness explanation.
