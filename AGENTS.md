# AGENTS.md — Engine Builder Constitution

> Canonical repository-root instructions for human and AI contributors. Applies to the entire tree.

> Status: initial governance fork derived from Umwelt's builder governance. Engine-specific decisions are still preflighted in `plan.md` and must not be presented as implemented or measured.

## 0. Mission

Engine tests this thesis:

> A local-first runtime can turn human intent into safe, typed, auditable actions across heterogeneous software and physical systems while LLMs remain optional proposal providers, device controllers retain realtime authority, and an independent policy/safety boundary controls execution.

The job of a builder is to implement the smallest experiment that can support or falsify the active claim. The job is not to make a demo look autonomous.

## 1. Source-of-truth hierarchy

Resolve conflicts in this order:

1. explicit current instruction from the project owner;
2. frozen safety requirement or preregistered acceptance protocol;
3. accepted Architecture Decision Record (ADR);
4. version specification or approved ticket contract;
5. this `AGENTS.md` and `RULES.md`, using the stricter reading;
6. directory-local `AGENTS.md`, which may only strengthen root rules;
7. tests that encode an accepted contract;
8. existing implementation;
9. comments, examples, generated docs and chat history.

Stop and report unresolved conflicts. Never reinterpret a safety gate, oracle or threshold merely to make a result pass.

## 2. Canonical separations

These separations define Engine and require an ADR plus human approval to change.

### 2.1 Real state is not LLM context

Authoritative operational state must be durable, typed and reconstructible after process, provider and context loss. Prompts, transcripts, summaries, hidden model state and chain-of-thought are not operational state.

### 2.2 Proposal is not authority

An LLM, planner, skill or user-interface component may produce a `ProposedAction`. It cannot mint its own permission, lower its risk class, certify its own success or bypass policy.

### 2.3 Deliberation is not realtime control

LLMs and high-level planners must never occupy a hard-realtime feedback loop. Motor control, flight stabilization, steering control, force limiting and equivalent timing-critical behavior belong to validated local controllers.

### 2.4 Policy is not safety hardware

Software policy complements but does not replace required interlocks, emergency stops, watchdogs or certified control components. A model cannot override the independent safety plane.

### 2.5 Prediction is not observation

Predicted or imagined effects remain separate from independently observed effects. Execution, sensors and deterministic tools are authoritative about what actually happened within their documented coverage.

### 2.6 Missing is not false

No telemetry, no relation or no acknowledgement means `UNKNOWN` unless a complete deterministic oracle justifies a negative. Preserve coverage, conflict and staleness explicitly.

### 2.7 State is not weights

- state: current target-specific facts and beliefs;
- experience: historical actions and outcomes;
- weights: reusable learned regularities;
- context projection: bounded temporary input for a model;
- imagined state: ephemeral counterfactual state.

A state change must not require model retraining.

### 2.8 Generic lifecycle is not generic device semantics

Engine may standardize capability discovery, validation, authorization, execution receipts and audit. It must not pretend a filesystem, arm, drone and vehicle share identical physical semantics or risk envelopes.

## 3. Required vocabulary

- `WorldSnapshot`: immutable/versioned state at an observation boundary.
- `Observation`: typed evidence with source, time, quality, coverage and artifact identity.
- `Capability`: an operation a target exposes under explicit preconditions and limits.
- `CapabilityGraph`: current targets, capabilities, dependencies and availability.
- `GoalSpec`: declarative desired outcome, constraints, budget and stop conditions.
- `ProposedAction`: untrusted candidate without execution rights.
- `ActionRequest`: concrete typed action bound to target and state preconditions.
- `PolicyDecision`: `ALLOW`, `DENY`, `REQUIRE_APPROVAL` or `DEFER`, with reasons.
- `Authorization`: scoped, expiring proof permitting an exact class of action.
- `ExecutionReceipt`: durable lifecycle and outcome record produced by the executor.
- `EffectDelta`: observed or predicted state difference, with evidence grade.
- `SkillManifest`: versioned strategy contract including supported scope and safety envelope.
- `AdapterManifest`: target protocol and conformance contract.
- `SafeState`: target-specific condition to seek on failure; never assume reaching it succeeded without observation.

Canonical identities must not use embeddings or free-form descriptions as persistence keys.

## 4. Execution lifecycle

Mutating operations follow this conceptual sequence:

```text
OBSERVE
-> PROPOSE
-> VALIDATE SCHEMA AND PRECONDITIONS
-> EVALUATE POLICY AND RISK
-> AUTHORIZE OR DEFER/DENY
-> DISPATCH
-> EXECUTE
-> OBSERVE
-> RECONCILE EXPECTED VS ACTUAL
-> RECORD RECEIPT AND EFFECT
```

Rules:

- authorization binds to target, action, relevant snapshot/preconditions, limits and expiry;
- dispatch is idempotent or explicitly non-idempotent with stronger recovery rules;
- retries cannot silently duplicate physical effects;
- stale preconditions force rejection or explicit revalidation;
- every terminal status is explicit, including `UNKNOWN` and partial failure;
- recovery and rollback success must be observed, not assumed;
- high-risk actions require an approval boundary outside any model.

## 5. LLM and cognition rules

LLMs may:

- translate natural-language intent into a proposed `GoalSpec`;
- propose actions or bounded workflows;
- explain observations and decisions while preserving evidence grades;
- help generate code, fixtures and hypotheses.

LLMs may not:

- own authoritative state;
- issue raw actuator commands on the realtime path;
- grant authorization;
- be the only safety evaluator;
- declare their own action successful;
- turn model confidence into observed truth;
- retain required runtime memory only in a provider session;
- require one specific vendor for core correctness.

Provider output is untrusted data. Validate it against a versioned schema. Record provider/model, bounded input projection, output artifact hash, purpose, latency and cost where available. External transmission of private data is opt-in.

## 6. Skills and mini-brains

A skill is replaceable implementation behind a capability contract. A neural skill receives no special authority.

Every skill must declare:

- exact inputs, outputs and units;
- supported targets and versions;
- preconditions and resource needs;
- safe operating envelope;
- latency/deadline behavior;
- uncertainty, defer or supported-scope behavior where learned;
- fallback and recovery;
- artifact/version identity;
- test and evaluation evidence.

A mini-brain additionally needs training-data provenance, reproducibility manifests, a simple baseline, held-out evaluation, quantization/hardware measurements and rollback. Do not introduce one until a simpler controller's limitation is measured.

## 7. Adapter boundaries

- Core modules depend on protocols, not device SDK types.
- Adapters translate canonical requests to target-specific commands and observations.
- Adapters do not choose goals or strategy.
- Each adapter must have a simulator or deterministic fake sufficient for contract and failure tests.
- A fake may validate lifecycle semantics but cannot support physical-safety claims.
- Network disconnect, timeout, duplicate acknowledgement, delayed telemetry and partial execution are first-class outcomes.
- Target-specific units and coordinate frames are explicit and never inferred from prose.

## 8. Test requirements

Every substantive contribution considers these layers.

### Unit tests

Validate deterministic local logic, canonical serialization, state reducers, policy evaluation, authorization scope/expiry, idempotency and error mapping.

### Contract/conformance tests

Validate typed interfaces and run the same black-box adapter and skill suites against every implementation.

### Reconstruction tests

Compare incremental/event replay with full materialization at the same logical boundary using explicit equivalence rules. Test process restart and store isolation.

### Stateful/property tests

Generate valid and invalid action sequences; compare the system to a small reference model; shrink failures; inject crashes at lifecycle boundaries; prove no authorization, state, receipt or cache crosses sessions.

### Safety/fault tests

Test deny-by-default, stale state, malformed proposals, limits, watchdogs, lost acknowledgements, stop paths and safe-state claims. Physical tests begin with low-energy bounded setups and independent emergency stop.

### Scientific regression tests

Protect split integrity, oracle semantics, metric calculations, reproducibility, calibration and no-leakage controls. A metric or oracle is production-critical code.

## 9. Evidence and uncertainty

Use at least:

- `OBSERVED`: directly emitted by an identified sensor/tool/executor;
- `DERIVED`: deterministic transformation of identified observations;
- `INFERRED`: model/statistical conclusion;
- `UNKNOWN`: insufficient evidence;
- `CONFLICTING`: sources disagree;
- `STALE`: evidence is no longer safe for the requested decision.

Keep provenance and confidence separate. High-confidence inference is not observation. Preserve raw artifact hashes where possible.

## 10. Security, privacy and authority

- deny by default;
- least privilege for targets, capabilities, duration and resources;
- no raw secrets in prompts, logs, datasets or receipts;
- isolate generated/untrusted code;
- constrain process, filesystem, device, time, compute and network access;
- sign or otherwise verify deployable skill artifacts before production use;
- make audit records tamper-evident where risk warrants it;
- never claim certification from internal testing alone;
- never test hazardous behavior on real hardware when simulation or a lower-energy rig can answer the question.

## 11. Research discipline

Before a decisive experiment record the claim, null, fixtures/dataset, baselines, metrics, thresholds, seeds, budgets, allowed remediation and abort conditions. Seal protected evaluation inputs. Preserve negative outcomes.

Learned systems must earn complexity against deterministic, classical and existing-product baselines under equal budgets. A beautiful demo cannot overrule a failed controlled benchmark.

## 12. Umwelt boundary

Engine is a separate project. It may integrate with Umwelt only through versioned provider-neutral contracts such as `WorldModelPort`.

- Engine owns capabilities, policy, authorization, execution, target safety and operations.
- Umwelt may provide state reconstruction, predicted effects, uncertainty/defer and bounded planning.
- Engine must work with a deterministic world model when Umwelt is absent.
- Umwelt output is advisory until Engine policy and authorization accept a concrete action.
- No shared mutable database or circular core dependency without an accepted ADR.
- Umwelt evidence claims retain Umwelt's own protocols; Engine cannot relabel speculative output as measured fact.

## 13. Agent change protocol

Before a non-trivial change, report:

```text
Phase/claim:
Area:
Relevant invariant(s):
Contract or ADR affected:
Tests/oracles affected:
Physical or external side effect possible: yes/no
External LLM/network usage introduced: yes/no
ADR required: yes/no
```

Then:

1. prefer the smallest valid change;
2. preserve explicit errors and provenance;
3. run the narrowest tests, then the applicable broader gate;
4. do not consume sealed evaluation data for debugging;
5. report changes, evidence, limitations, safety impact and rollback;
6. stop if authority or risk scope is ambiguous.

## 14. ADR policy

Create an ADR for changes to:

- authoritative state and identity semantics;
- action, policy, authorization or receipt lifecycle;
- safety boundary or risk classes;
- adapter/skill contract;
- realtime vs deliberative boundary;
- external data/privacy boundary;
- oracle, acceptance gate or experiment-consumption rule;
- Engine/Umwelt ownership boundary;
- model family on a safety- or correctness-relevant path.

An ADR contains context, decision, alternatives, consequences, safety/scientific impact, migration, reversibility, owner, date and status.

## 15. Stop conditions

Stop and escalate before changing or executing when:

- source-of-truth documents conflict;
- the target, authorization principal or risk class is ambiguous;
- a requested path bypasses observe/validate/policy/authorize;
- a model output is proposed as truth without an independent oracle;
- a safety rule would be weakened;
- an irreversible or hazardous physical action lacks explicit human authority;
- private data may leave its approved boundary;
- a sealed test may be consumed;
- idempotency or crash recovery semantics are unknown;
- a generated action could affect systems outside the declared sandbox;
- a failed experiment is being rescued by moving gates.

## 16. Definition of done

A substantive change is done only when applicable contracts, error paths, provenance, isolation, deterministic oracles, tests, observability, safety analysis, documentation and ADRs are complete. Core correctness must survive loss or replacement of every LLM provider.

Final checksum:

```text
LLM proposal != authority
prediction != observation
policy != physical safety
deliberation != realtime control
simulation evidence != real-world certification
generic lifecycle != generic device semantics
state != weights
imagine != execute
```
