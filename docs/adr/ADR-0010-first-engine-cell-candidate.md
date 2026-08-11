# ADR-0010 — First Engine Cell candidate remains unregistered

- Status: rejected by preregistered gate under explicit owner Cell direction
- Owner: project owner
- Date: 2026-08-11

## Context

After generic plugin autonomy v3, the roadmap permits one Engine Cell only
after a deterministic/classical deficit is measured and a bounded local runner
earns its complexity on held-out evidence. A Cell is a specialist
implementation, not a second Heart, executive, agent loop, or authority source.

EXP-2026-003 tested one reference-world candidate: classify a bounded English
or Dutch warehouse utterance as the already installed
`warehouse.reserve-minimum/v1` template identifier or `DEFER`. The candidate
used a deterministic unsupported-scope gate and a 16-unit int8 MLP. Its proposed
integration output was only a non-operational `SuggestionV1`; it had no route to
a goal, proposal, authorization, tool, executor, or dispatch.

## Decision

1. Do not register the candidate as a reference-world specialist and do not
   package its model artifact with a plugin.
2. Retain the exact artifact, runner, provenance, development attempts,
   sealed protocol and canonical held-out result under EXP-2026-003.
3. Keep the current deterministic/classical path. A model that ties the best
   baseline in either language has not earned a runtime dependency.
4. Do not add a generic Cell plugin role, scheduler, store, authorization, or
   action contract. Existing `SpecialistBrainV2` and non-operational
   `SuggestionV1` remain the future integration boundaries.
5. A later Cell attempt needs a distinct, measured bounded task, a new ADR or
   explicit amendment, a new experiment identifier and sealed held-out set.
   EXP-2026-003 examples are consumed evidence and cannot become training or
   remediation data for that claim.

## Alternatives

- Ship because English improved by 0.211 macro-F1: rejected because the frozen
  gate applied separately to English and Dutch.
- Pool language scores: rejected because it would hide the Dutch tie.
- Lower the `0.03` margin or raise the baseline ceiling after consumption:
  rejected as moving a decisive gate.
- Run the held-out set again after tuning: rejected because the first complete
  output is canonical.
- Let the classifier emit a `GoalCandidateV1` or `ProposedActionV1`: rejected
  because this experiment authorized only an inert suggestion and a model
  cannot make its output operational.

## Consequences

Engine ships no learned Cell from this experiment. The source tree gains a
reproducible negative-result harness and evidence, but no production import,
manifest declaration, model load, brain call, goal, mandate, or dispatch. The
Cell roadmap remains open rather than being represented as implemented.

## Safety and scientific impact

The candidate achieved template precision and `DEFER` recall of 1.0 in both
held-out language slices, and its resource envelope passed. Those facts show
bounded feasibility, not a comparative win, effect truth, target safety, or
permission. Rejecting the candidate preserves the preregistered null and avoids
turning a model-confidence result into observation or authority.

The data is repository-authored CC0-1.0 text. No production, user, private or
external model data was used. The runner used no network or external provider.

## Migration and reversibility

No runtime or database migration exists because the Cell was never registered.
The rejected model is isolated under the experiment artifacts. A later owner
decision can introduce a different specialist behind existing proposal-only
contracts after new evidence; it cannot relabel this no-go as a pass.
