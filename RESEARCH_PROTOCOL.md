# RESEARCH_PROTOCOL.md — Engine Experimental and Safety-Evidence Rules

> Applies to benchmarks, simulator studies, adapter claims, mini-brain training and hardware pilots.

## 1. Every experiment begins with a claim

Before a decisive run record:

- hypothesis and null hypothesis;
- target, adapter, firmware and environment identity;
- risk class and permitted side effects;
- independent variables and dependent metrics;
- exact fixtures/dataset and split manifests;
- baselines;
- success, failure and safety thresholds;
- number of runs/seeds;
- compute, time, energy and model budgets;
- allowed remediation;
- abort conditions;
- owner, date and reviewer.

Do not decide success after seeing the result.

## 2. Evidence lifecycle

Use:

```text
DRAFT -> PREFLIGHTED -> SEALED -> RUNNING
-> CONSUMED -> INTERPRETED -> SUPERSEDED
```

- `DRAFT`: protocol can change.
- `PREFLIGHTED`: instruments tested only on allowed development fixtures.
- `SEALED`: protocol, gates and protected manifests are hashed.
- `RUNNING`: decisive execution has begun.
- `CONSUMED`: protected results were exposed in a way that can influence work.
- `INTERPRETED`: outcome, including negative/aborted outcome, is recorded.
- `SUPERSEDED`: a later experiment replaces scope but never erases history.

## 3. Evidence environments

Label every result:

- `UNIT/REFERENCE_MODEL`;
- `FAKE_ADAPTER`;
- `SIMULATION`;
- `HARDWARE_IN_LOOP`;
- `BOUNDED_REAL_TARGET`;
- `PRODUCTION_OBSERVATIONAL`.

Evidence never automatically promotes upward. Simulator evidence can validate contracts and fault handling, not physical safety or deployment certification.

## 4. Baseline-first order

For runtime/control claims compare, as applicable:

1. direct manual/device-native operation;
2. deterministic rules/controller;
3. classical optimization/control;
4. existing domain runtime/product;
5. bounded LLM proposal provider;
6. mini-brain or other learned skill;
7. Umwelt-assisted prediction/planning.

A simple baseline winning is a successful result and may simplify the product.

## 5. Equal-budget policy

Report or constrain:

- real target executions;
- simulator executions;
- model calls and tokens;
- wall-clock and deadline misses;
- CPU/GPU/accelerator time;
- memory and storage;
- energy where relevant;
- human approvals/interventions;
- retries and recoveries;
- candidate count/search depth;
- external API cost.

Do not call a system better when it quietly spends an order of magnitude more or receives broader authority.

## 6. Core Engine 0.1 metrics

Measure at least:

- schema/conformance pass rate;
- replay versus full-materialization equivalence;
- cross-session/target isolation failures;
- unauthorized dispatch count;
- stale-action rejection/revalidation rate;
- duplicate physical-effect count under retry/crash injection;
- receipt completeness and terminal `UNKNOWN/PARTIAL` rate;
- fault detection and bounded-stop latency in simulation;
- recovery correctness;
- audit-link completeness;
- p50/p95/p99 runtime latency by lifecycle stage;
- LLM-offline equivalence for fixed proposals.

Zero unauthorized dispatches, zero hidden cross-target state and zero invented observations are release-blocking for every scope.

## 7. Adapter conformance protocol

Each adapter is tested against a frozen suite containing:

- discovery and manifest negotiation;
- canonical units and frames;
- valid requests;
- malformed and unsupported requests;
- precondition and staleness failures;
- duplicate command IDs;
- timeout before/after possible execution;
- lost/duplicate/out-of-order acknowledgements;
- delayed/conflicting telemetry;
- partial execution;
- cancellation and stop;
- reconnect and process restart;
- target isolation;
- receipt/effect reconciliation.

Fakes and simulators must state which device guarantees they cannot model.

## 8. Reconstruction and stateful testing

For generated sequences:

```text
reference_reduce(initial_state, accepted_events)
== canonicalize(runtime_replay(log_to_boundary))
== canonicalize(full_materialization(target_at_boundary))
```

Define excluded nondeterministic fields in advance, such as wall-clock arrival timestamps, and explain why they do not affect semantics.

Property/state-machine tests must:

- generate valid and invalid actions;
- inject crashes at every lifecycle transition;
- shrink failing sequences;
- reset stores, targets and clocks between examples;
- use independent sessions/workspaces and contamination canaries;
- report seeds and the minimal counterexample;
- never share authorization or correctness-relevant caches across examples.

## 9. Safety and fault-injection protocol

Begin with a fault matrix:

- stale/missing/conflicting observation;
- policy service unavailable;
- expired or wrong-target authorization;
- adapter timeout;
- network partition;
- process crash;
- delayed or corrupt telemetry;
- target refuses command;
- partial movement/effect;
- watchdog activation;
- emergency stop;
- recovery action failure.

Progress from reference model to fake, simulator, HIL and bounded hardware only as prior gates pass. Hardware tests require a written safe state, energy/workspace bounds, observer, emergency stop and abort procedure appropriate to the risk.

No internal protocol substitutes for applicable legal, regulatory or certification work.

## 10. Mini-brain experiment protocol

Before training:

- define one bounded capability and operational metric;
- freeze deterministic/classical baselines;
- record data sources, consent/licensing and target distribution;
- separate train/validation/test by time, target and scenario where claims require it;
- include out-of-scope and failure cases;
- define uncertainty/defer behavior;
- set memory, latency and energy budgets for target hardware;
- define rollback and fallback.

Every run records:

```text
code_revision
dataset_manifest_hash
split_manifest_hash
preprocessing_and_feature_version
model_config
seed
framework_versions
training_hardware
optimizer_and_schedule
checkpoint_hash
quantization/export_config
target_hardware_and_runtime
evaluation_protocol_version
```

Evaluate task metric, calibration/supported scope, worst relevant failures, p95/p99 latency, memory, energy, hardware compatibility and performance after quantization.

## 11. No-leakage rules

Prohibited examples:

- post-action telemetry in pre-action features;
- test-target identity leaking through filenames or scenario IDs;
- repeated near-identical trajectories across train and test;
- future environment state in a cache;
- hardware calibration from the held-out decisive run;
- manual threshold changes after inspecting protected failures;
- LLM-derived labels presented as sensor ground truth;
- using an Umwelt prediction as the observed target.

## 12. Umwelt integration experiment

To claim Umwelt improves Engine:

1. freeze the same Engine snapshot/capabilities and candidate set;
2. compare deterministic/no-Umwelt operation against the Umwelt adapter;
3. preserve equal proposal, execution and model budgets;
4. keep Engine policy/authorization identical;
5. independently observe outcomes;
6. report calibration/defer and operational value, not only plausible reasoning;
7. retain Umwelt's evidence labels and model/version metadata.

Engine must still run safely when the Umwelt provider is absent, stale or defers.

## 13. Holdout consumption

A protected set is consumed when predictions, decisive aggregate metrics or labeled failures are inspected in a way that can influence later design or thresholds. It cannot then be reused as untouched confirmation evidence.

Hardware is often scarce; scarcity does not justify reusing consumed trials without labeling them exploratory.

## 14. Abort conditions

Abort and preserve the run when:

- a safety envelope or workspace bound is crossed;
- an unauthorized or wrong-target dispatch occurs;
- emergency stop/watchdog behavior is unavailable or unverified for the planned test;
- oracle or simulator self-consistency fails;
- replay and reference state diverge beyond the frozen equivalence rule;
- target/firmware/adapter identities mismatch the manifest;
- telemetry or receipts silently drop errors;
- evaluation code or thresholds change mid-run;
- protected labels leak;
- hardware/runtime failure materially changes the protocol;
- privacy/consent boundaries are violated.

## 15. Abandon or pivot gates

Require formal review when:

- a common Engine lifecycle adds more complexity than target-native integration without measured benefit;
- a second adapter cannot conform without weakening core semantics;
- reliable recovery from ambiguous execution cannot be established for the target;
- the needed safety case exceeds the project's authority/resources;
- a mini-brain fails to beat a simpler baseline under edge constraints;
- Umwelt assistance adds no operational value under equal budget;
- human approval burden eliminates the claimed usefulness;
- physical-domain expansion would require pretending target-specific guarantees are generic.

## 16. Reproducibility artifacts

Recommended layout:

```text
experiments/
  EXP-YYYY-NNN/
    protocol.md
    threat-model.md
    manifest.json
    environment.lock
    target-manifest.json
    fixtures-or-split-manifest.json
    configs/
    logs/
    receipts/
    observations/
    metrics.json
    result.md
    hashes.txt
```

No decisive result may depend on chat transcripts.

## 17. Result language

Use:

- `PASS`;
- `FAIL`;
- `ABORTED-SAFETY`;
- `ABORTED-INSTRUMENT`;
- `ABORTED-DATA`;
- `NOT-SUPPORTED`;
- `INCONCLUSIVE`;
- `SUPERSEDED`.

Avoid “safe”, “autonomous”, “intelligent” and “controls everything” unless each term has a frozen operational definition and matching evidence.

## 18. Final rule

A polished demo does not outrank an unauthorized dispatch, ambiguous physical effect, reconstruction failure or controlled benchmark loss. Measured reality changes Engine.
