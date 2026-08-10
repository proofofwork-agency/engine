# Engine Builder Governance

These repository-root files define how Engine is designed, tested and evaluated. They are an Engine-specific starting fork of the governance principles used by the neighboring Umwelt project; Engine does not inherit future Umwelt changes automatically.

## Files

- `AGENTS.md` — canonical builder constitution and source-of-truth hierarchy.
- `RULES.md` — strict MUST/MUST-NOT rules and stop conditions.
- `ARCHITECTURE_GUARDRAILS.md` — recurring design and safety traps.
- `RESEARCH_PROTOCOL.md` — preregistration, conformance, reconstruction, hardware and mini-brain evidence rules.
- `BUILDER_CHECKLIST.md` — change/review checklist.
- `CLAUDE.md` — Claude-specific entry point that defers to the canonical rules.
- `plan.md` — current concept, architecture, falsifiable slice, roadmap and Umwelt relationship.

## Placement and precedence

All files above live at repository root. A nested `AGENTS.md` may add tighter adapter-, device-, safety- or experiment-specific rules but may never weaken root constraints.

Conflict precedence is defined in `AGENTS.md`. Material changes to state, authority, safety, action/receipt lifecycle, adapter/skill contracts, experiments or the Engine/Umwelt boundary require an ADR.

## Status discipline

`plan.md` is currently a proposal, not implementation evidence. Builders use these words precisely:

- `SPECULATIVE`: design hypothesis only;
- `IMPLEMENTED`: code and applicable tests exist;
- `MEASURED`: result obtained under a documented protocol;
- `SUPPORTED`: evidence favors the scoped claim;
- `NOT-SUPPORTED`: valid evidence does not favor it;
- `INCONCLUSIVE`: evidence cannot decide;
- `CERTIFIED`: use only when an identified competent external certification process actually grants it.

## Core checksum

```text
real state != LLM context
proposal != authorization
prediction != observation
policy != physical safety
deliberation != realtime control
acknowledgement != achieved effect
simulation != certification
Engine execution != Umwelt prediction
negative result != governance failure
```

## Project separation

Engine and Umwelt are sibling projects. Shared ideas are documented; mutable runtime state and ownership remain separate. Integration happens only through explicit, versioned contracts after each side's own gates pass.
