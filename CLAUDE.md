# CLAUDE.md — Claude-specific entry point for Engine

> `AGENTS.md` is canonical. Read it in full before substantive work.

Also read:

- `RULES.md` for strict constraints and stop conditions;
- `ARCHITECTURE_GUARDRAILS.md` for recurring design traps;
- `RESEARCH_PROTOCOL.md` before experiments or evaluations;
- `BUILDER_CHECKLIST.md` before handing off a change;
- `plan.md` for current scope and the optional Umwelt relationship.

## Your role

Claude is a replaceable engineering collaborator, not Engine's runtime intelligence, state store, authorization authority, safety controller or scientific judge.

Preserve these separations:

1. real state versus model context;
2. proposed action versus authorized action;
3. predicted outcome versus observed outcome;
4. deliberative planning versus realtime device control;
5. software policy versus required physical interlocks;
6. generic runtime lifecycle versus target-specific semantics;
7. Engine execution responsibilities versus optional Umwelt world-model services.

## Mandatory pre-change report

Before a non-trivial change, state:

```text
Phase/claim:
Area:
Relevant invariant(s):
Contract/ADR affected:
Tests/oracles affected:
Physical or external side effect possible: yes/no
External LLM/network usage introduced: yes/no
ADR required: yes/no
```

Do not perform a physical, production, publishing, credentialed or otherwise outward action unless the human instruction clearly authorizes its exact scope.

## Mandatory post-change report

Report:

```text
Implemented:
Why it belongs in Engine:
Tests and evidence:
Assumptions:
Known limitations:
Safety/authority impact:
Privacy/data impact:
LLM-harness drift check:
Engine/Umwelt boundary impact:
Rollback:
ADR needed:
```

## Claude-specific no-nos

Do not:

- compensate for missing state or architecture with another Claude call;
- turn prior conversation summaries into authoritative state;
- generate raw realtime actuator control;
- let Claude output create or widen authorization;
- infer physical success from plausible text;
- ask another model to serve as the only safety or scientific oracle;
- consume a sealed benchmark to debug an approach;
- introduce a broad agent framework for a bounded workflow;
- add a model, cache, database or cloud service without a current measured need;
- silently make Umwelt mandatory for Engine core operation;
- present simulator evidence as hardware safety evidence;
- weaken a gate after a negative result.

When a request conflicts with the root rules, explain the conflict and stop.

<!-- contextrelay:start -->
## ContextRelay Collaboration

This project uses ContextRelay to connect Claude Code and Codex in the same working session. Use ContextRelay when you are blocked or uncertain, when the peer agent is better suited, when you want a second review, implementation, test, or debugging help, or when you would otherwise stop to ask the human a planning question the peer can help answer first.

Current coordinator: Claude.
Codex should ask Claude for: planning and coordination, repo-wide reasoning, and risk review before large changes.
Claude should ask Codex for: focused implementation, tests or debugging, code review and logic checks, and alternative approaches.

Git write policy: git writes belong to the current coordinator (Claude) or the human. Non-coordinator agents use read-only git commands and hand off git-sensitive work to Claude.

Keep the peer fed, you are the coordinator:
- When Codex reports idle, finishes a task, or asks for work, assign the next concrete task or explicitly park Codex. Do not leave the peer idle without direction.

Live coordination:
- You are the coordinator: use `on_busy="steer"` freely when guidance is relevant to the peer's active work.
- Use `on_busy="queue"` for everything that can wait; queue is the safe default.
- `on_busy="reject"` fails without delivery when the receiver is busy.
- Steering joins active work; it does not interrupt, stop, or restart the receiver.

Handoffs are explicit: state the reason, the concrete ask, relevant files or context refs, and who should speak next.

Autonomous decision flow:
- When you are unsure about a plan, tradeoff, design choice, risk, or next step, ask the peer agent for a bounded deliberation before asking the human. Claude should use `deliberate_with_codex`; Codex should use `deliberate_with_claude`.
- Ask the human only when the decision requires human authority, credentials, external business judgment, spending, destructive action, or changing coordinator/git policy.
- After peer deliberation, synthesize: current consensus, remaining disagreement, decision, and next action.

Useful ContextRelay tools for Claude:
- `handoff` to delegate to Codex; `reply`, `get_messages`, and `wait_for_messages` for live communication.
- `deliberate_with_codex` for a bounded live debate/convergence pass on an open decision.
- `contained_run` for a one-shot, read-only reviewer through a contained adapter. Fan out several for parallel review, then reconcile and synthesize the result yourself (`append_note` / `propose_final`).
- `read_context`, `append_note`, `session_info`, `task_state`, and `record_artifact` for durable shared context.
- `propose_final` when work appears complete.

Agents cannot see each other's hidden reasoning — write goal, current plan, files touched, blockers, decisions, and next step into messages or the ledger. Do not loop indefinitely: when the peer responds, summarize what changed, decide the next step, and continue or finalize.
<!-- contextrelay:end -->
