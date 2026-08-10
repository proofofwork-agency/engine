# BUILDER_CHECKLIST.md — Engine Change Review

> Use for every substantive change. Mark non-applicable items explicitly rather than silently skipping them.

## A. Purpose and scope

- [ ] I can name the current Engine phase, claim or user capability this supports.
- [ ] The change is necessary for the smallest active slice.
- [ ] A simpler target-native, deterministic or classical implementation was considered.
- [ ] The change does not imply support for untested device classes.
- [ ] The evidence wording matches implemented/measured reality.

## B. Architecture

- [ ] Authoritative state remains outside LLM context.
- [ ] Proposal, validation, policy, authorization, dispatch and observation remain separate.
- [ ] Deliberative cognition is outside hard-realtime control.
- [ ] Software policy does not pretend to replace required safety interlocks.
- [ ] Generic lifecycle and target-specific semantics remain separate.
- [ ] No provider- or device-SDK type leaked into core contracts.
- [ ] Engine remains operational without Umwelt and without an LLM.
- [ ] No hidden agent loop or global mutable state was introduced.

## C. State and evidence

- [ ] Every observation has target, source, time, quality/coverage and artifact/version provenance.
- [ ] Observed, derived, inferred, unknown, conflicting and stale remain distinguishable.
- [ ] Snapshot/precondition semantics are explicit.
- [ ] Incremental/replay state has an independent reference materialization path.
- [ ] Canonical identity does not depend on embeddings or free-form model text.
- [ ] Predictions and imagined state never enter observed state as truth.
- [ ] Cache keys, invalidation and isolation are defined if a correctness-relevant cache exists.

## D. Authority and security

- [ ] Policy is deny-by-default.
- [ ] Authorization is scoped to principal, target, action, limits and expiry.
- [ ] LLMs, planners and skills cannot mint or widen authorization.
- [ ] Stale or wrong-target requests are rejected or explicitly revalidated.
- [ ] Generated/untrusted code is isolated with resource and network bounds.
- [ ] Secrets and private telemetry/code are excluded from external calls by default.
- [ ] Audit records connect proposal, decision, authorization, dispatch, observations and receipt.

## E. Execution and recovery

- [ ] Units, coordinate frames and device deadlines are explicit.
- [ ] Idempotency behavior is documented and tested.
- [ ] Retry cannot silently duplicate a physical effect.
- [ ] Timeout, disconnect, lost acknowledgement and partial execution have explicit states.
- [ ] Success is independently observed; absent evidence becomes `UNKNOWN`.
- [ ] Safe state, stop and recovery behavior are target-specific.
- [ ] Rollback or compensation success is observed, not assumed.

## F. Physical safety

- [ ] The target risk class and maximum impact are documented.
- [ ] The test begins in fake/simulator/HIL where that can answer the question.
- [ ] A bounded workspace, energy/speed/force limits and abort procedure exist where applicable.
- [ ] The independent emergency-stop/watchdog path is verified where required.
- [ ] A model is not on a hard-realtime safety path.
- [ ] Simulator results are not presented as physical certification.
- [ ] Human authority exists for every intended physical/outward side effect.

## G. Skills and mini-brains

- [ ] Capability contract and skill implementation remain separate.
- [ ] Supported target, input/output, units, envelope, latency and fallback are declared.
- [ ] A deterministic/classical baseline is frozen.
- [ ] Training data, splits, configs, seeds and checkpoint/export hashes are reproducible.
- [ ] Uncertainty, defer or supported-scope behavior is evaluated.
- [ ] Quantized performance, latency, memory and energy are measured on target hardware.
- [ ] Failure and out-of-scope cases remain in the result.

## H. Tests

- [ ] Unit tests added or updated.
- [ ] Core contract tests added or updated.
- [ ] Adapter/skill conformance suite passes.
- [ ] Replay/incremental state equals the reference materialization where applicable.
- [ ] Stateful tests shrink and fully reset state between examples.
- [ ] Target/session/store/authorization isolation is proven with canaries.
- [ ] Malformed, denied, stale, timeout, partial and crash paths are tested.
- [ ] Fault injection ran at the safest sufficient evidence level.
- [ ] Test output records seeds, versions and target manifest.

## I. Research integrity

- [ ] Claim, null, metrics, thresholds, baselines and budgets were written before decisive evaluation.
- [ ] No sealed set was inspected or reused without consumption labeling.
- [ ] No future/post-action evidence leaked into pre-action inputs.
- [ ] Equal-budget comparisons are reported.
- [ ] Negative, aborted and partial outcomes are retained.
- [ ] An ADR exists if scientific, authority or safety meaning changed.

## J. Umwelt integration

- [ ] Integration occurs through a versioned, provider-neutral port.
- [ ] No mutable operational database is shared between the cores.
- [ ] Umwelt prediction remains inferred/advisory, not observed truth.
- [ ] Engine policy, authorization, execution and target safety remain authoritative.
- [ ] Engine behaves safely when Umwelt is absent, stale, errors or defers.

## K. Final questions

- [ ] If every LLM conversation disappeared, could Engine reconstruct state and audit every action?
- [ ] If every model provider went offline, would no unauthorized or unsafe fallback action occur?
- [ ] Can an independent observer distinguish what was proposed, authorized, executed and actually observed?
- [ ] Would the change still make sense if the simplest baseline wins?

If any required answer is no, the change is not ready.
