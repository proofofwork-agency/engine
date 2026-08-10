# RULES.md — Engine Strict Rules

> Root-level normative constraints. Local rules may tighten but never weaken them. When this file and `AGENTS.md` differ, use the stricter reading unless an accepted ADR or explicit owner instruction says otherwise.

## MUST

1. MUST keep authoritative target state outside LLM context.
2. MUST use immutable/versioned observation boundaries or snapshots.
3. MUST preserve provenance, timestamps, coverage and target identity.
4. MUST distinguish observed, derived, inferred, unknown, conflicting and stale evidence.
5. MUST treat every LLM/skill output as an untrusted proposal until validated.
6. MUST validate schema, units, target, preconditions and snapshot freshness before mutation.
7. MUST apply deny-by-default policy and least privilege.
8. MUST scope authorization to target, action, limits and expiry.
9. MUST keep authorization outside LLM/model control.
10. MUST keep hard-realtime and device-safety loops outside LLM/planner control.
11. MUST preserve an independent stop/safety path where the target risk requires it.
12. MUST use deterministic sensors/tools/controllers when they can establish a fact or satisfy the requirement.
13. MUST make dispatch idempotent or explicitly handle non-idempotent recovery.
14. MUST independently observe or explicitly mark unknown what happened after execution.
15. MUST record durable receipts for mutating actions and terminal failures.
16. MUST keep imagined/predicted effects separate from observed effects.
17. MUST support replay/reconstruction of canonical operational state.
18. MUST isolate targets, sessions, stores, authorizations and caches.
19. MUST make LLM, skill and adapter implementations replaceable behind typed contracts.
20. MUST test malformed, stale, denied, timed-out, partial and crash outcomes.
21. MUST isolate generated/untrusted code and bound filesystem, process, network, time and device access.
22. MUST preregister decisive gates and retain negative results.
23. MUST compare learned skills against simple baselines under equal budgets.
24. MUST make the Engine/Umwelt boundary versioned and optional.
25. MUST stop when authority, target scope, safety meaning or a frozen oracle is ambiguous.

## MUST NOT

1. MUST NOT send raw actuator setpoints from an LLM.
2. MUST NOT use a recursive agent loop as Engine's core control architecture.
3. MUST NOT treat chat history, prompt summaries or provider memory as operational state.
4. MUST NOT let a proposal provider mint or expand its own authorization.
5. MUST NOT let a model certify its own output or execution success.
6. MUST NOT automatically execute a proposed or imagined action.
7. MUST NOT continue on missing/conflicting safety-relevant evidence as if it were false or harmless.
8. MUST NOT retry a possibly non-idempotent physical action blindly.
9. MUST NOT silently execute against stale state.
10. MUST NOT mix target-specific units, frames or safety semantics in generic prose fields.
11. MUST NOT expose provider SDK objects in core persistence/contracts.
12. MUST NOT make embeddings canonical IDs or truth.
13. MUST NOT let a cache become hidden correctness state.
14. MUST NOT equate simulation success with real-world safety or certification.
15. MUST NOT test an avoidable hazardous case on real hardware.
16. MUST NOT add a mini-brain before measuring a deterministic/classical baseline.
17. MUST NOT train on future, protected or unprovenanced data.
18. MUST NOT send private telemetry, code or imagery externally by default.
19. MUST NOT claim support for a device class from one target-specific pilot.
20. MUST NOT couple Engine correctness to Umwelt, one model vendor or one device vendor.
21. MUST NOT share mutable operational storage between Engine and Umwelt cores.
22. MUST NOT move safety, metric, oracle or success gates after seeing decisive results.
23. MUST NOT hide partial, negative or aborted outcomes.
24. MUST NOT broaden to drones, road vehicles, boats or high-force systems during the initial slice.
25. MUST NOT continue merely because significant code has already been written.

## STOP CONDITIONS FOR A CODING AGENT

Stop before writing or executing when:

- an action could escape the declared sandbox or target;
- human authority for a physical/outward side effect is absent;
- authorization or receipt semantics are unresolved;
- failure recovery could duplicate a physical effect;
- a change weakens fail-closed behavior;
- a requested change crosses the deliberative/realtime boundary;
- source-of-truth documents conflict;
- a sealed evaluation may be consumed;
- a schema change alters safety or scientific meaning;
- privacy or data ownership is unclear.

## ARCHITECTURE CHECKSUM

```text
REAL WORLD
  -> OBSERVATIONS + PROVENANCE
  -> WORLD SNAPSHOT + CAPABILITIES
  -> PROPOSED ACTION
  -> VALIDATE + POLICY + RISK
  -> HUMAN/SYSTEM AUTHORIZATION
  -> TARGET-SPECIFIC EXECUTOR
  -> REAL WORLD
  -> OBSERVE + RECEIPT + RECONCILE

LLM = optional intent/candidate provider.
LLM != state, authority, safety controller or truth oracle.
```
