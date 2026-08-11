---
title: Heart and brains
sidebar_position: 4
description: What the Heart, general brain, and multiple specialist brains mean and how they work together.
---

# Heart and brains

The organ metaphor is functional, not biological. The **Heart** carries continuity and authority boundaries; brains provide cognition. Without the Heart, brains are isolated model calls. Without a brain slot, Engine is only a deterministic control runtime. The current architecture combines both while keeping every brain replaceable.

> **Current topology:** **exactly one active general executive brain per runtime composition** plus **zero or more registered specialist brains**. This is **Implemented**. Multiple competing general brains and their arbitration are not a first-class feature.

“Brain” names a role and typed interface, not a vendor or a model council. Conceptually, a Claude model, GPT model, local model, deterministic planner, or classical algorithm could implement a general or specialist role when connected through the appropriate contract. The current repository ships deterministic and OpenAI-compatible executive implementations. It does not ship a Claude-plus-GPT council, concurrent general executives, voting, or automatic provider arbitration.

## What the Heart means

`WorldHeartV2` owns the living, durable cycle. It:

- observes every connected target and creates a versioned `WorldSnapshotV2`;
- manages `ACHIEVE` and `MAINTAIN` goals and their priority/status;
- evaluates declarative effects, stop conditions, and routine guards;
- determines when cognition is needed and when quiet monitoring is enough;
- builds a bounded, fresh context projection for every brain call;
- invokes the executive brain and a selected specialist;
- validates proposals and concrete requests;
- lets deterministic policy grant or refuse authorization;
- dispatches only through a plugin executor;
- observes after an action and lets an oracle reconcile the effect;
- stores causal IDs, receipts, effects, brain calls, wakes, and learning evidence;
- resumes durable tasks and reconstructs state after process restart;
- isolates a failing goal as `degraded` instead of stopping the entire world loop.

The Heart therefore makes decisions about **lifecycle and authority**, not about the specific meaning of a warehouse transfer or light brightness.

## What the Heart is not

The Heart is not:

- an LLM or hidden chain of thought;
- a domain specialist;
- a hard-realtime scheduler;
- an executor allowed to call arbitrary APIs;
- an effect oracle;
- an emergency stop or safety controller.

The Heart may validate and stop a plugin result, but it cannot prove that physical safety hardware works correctly.

## The general brain

The general brain receives a bounded projection containing the goal, relevant world state, effect results, visible capabilities, and specialists. It selects a next cognitive step:

- request more world information;
- consult a specialist;
- propose a semantic effect;
- wait;
- advise completion or abandonment.

The Heart never accepts completion on the brain's word alone. Only observed goal conditions can produce `completed` or `monitoring`.

### Two current implementations

| Executive | Use | Status |
| --- | --- | --- |
| `DeterministicExecutiveBrainV2` | Provider-free baseline and known, stable routes | **Implemented**, the default without model configuration |
| `ModelExecutiveBrainV2` | Structured-output provider for novelty, conflict, or ambiguity | **Implemented** behind a provider-neutral port; local/API canaries exist |

At composition time, the runtime selects exactly one of these executives. There is no automatic “council of LLMs.” An application could build its own composite executive behind the same protocol, but Engine does not currently define canonical identity, arbitration, cost, timeout, or conflict semantics for one.

`engine.plugin/v3` does not change that ownership. An enrolled strategy may
handle a known typed situation deterministically or ask Heart for at most one
executive or specialist call through its declared cognition route. It receives
the same bounded context projection as that cognition call and cannot schedule,
authorize, or dispatch. A Cell may later implement a specialist, but never a
second Heart or executive runtime.

## Specialist brains

A specialist declares:

- a stable, versioned identity;
- supported capability families;
- an `advise(goal, snapshot, request)` contract;
- a `SpecialistAdviceV1` response with `supported`, summary, metadata, and optionally a `ProposedActionV1`.

Plugins can register multiple specialists. The registry projects their IDs and supported families to the general brain. When the general brain selects `CONSULT_SPECIALIST`, the Heart invokes exactly that specialist and records the output with provenance.

Specialists may be deterministic algorithms, classical planners, or models. “Brain” here therefore means a cognitive decision organ, not necessarily a neural network.

## One general brain and multiple specialists

```text
                         +-> specialist: lighting/energy -+
Goal + bounded context -> general executive               +-> ProposedAction
                         +-> specialist: warehouse -------+
                         +-> specialist: vision (later) ---+
                                      |
                                      v
                         Heart validates and authorizes lifecycle
```

What is possible today:

- catalog multiple specialists from multiple plugins at once;
- select by explicit specialist ID and supported capability families;
- make specialist outputs snapshot-bound and durably traceable;
- let a specialist provide a typed proposal;
- replace a provider or specialist without moving goal/state into its session.

What is not a canonical feature today:

- letting multiple general brains vote in parallel;
- automatically using consensus, debate, or model ranking as authority;
- letting a specialist register itself from free-form model text;
- letting a specialist invent capabilities outside the enrolled manifest;
- proving that more brains always produce better outcomes.

The older 0.1 pilot and current fixtures prove the general -> specialist -> capability -> observation route. They do not prove general multi-brain superiority; that requires a controlled comparison under equal budgets.

## From decision to action

The division of responsibility remains the same for every mutation:

1. **General brain:** selects strategy, specialist, or semantic effect.
2. **Specialist:** provides bounded domain advice or a semantic proposal.
3. **Heart:** validates identities, state binding, and schemas.
4. **Domain controller:** produces the exact target request.
5. **Policy:** decides and may mint authorization.
6. **Executor:** executes.
7. **World provider + effect oracle:** establish what was actually observed.
8. **Heart:** records the result and determines the next lifecycle status.

No brain skips steps 3-7.

## Context is not state

For each call, `BoundedContextProjector` projects at most a bounded number of relevant entities and observations, together with relations, capability metadata, and effect evaluations. A projection receives a hash and snapshot ID.

This has three consequences:

- the model provider does not need to preserve session history;
- the complete world remains local and reconstructible after provider loss;
- brain output against an old snapshot can be rejected as stale.

The projection may be truncated. That is explicit incomplete coverage, not evidence that something is absent.

## Stable state is cognitively quiet

A `MAINTAIN` goal that is demonstrably true enters `monitoring`. Polls and events may continue to arrive, but they do not automatically invoke brains. Only a fresh observation showing relevant drift reactivates cognition.

This exists and is deterministically tested. It is both a cost rule and an architecture boundary: an LLM does not belong in the continuous sensor or actuator loop.

## Are brains optional or essential?

Both statements can be true when stated precisely:

- **A particular LLM is optional.** The deterministic executive can carry core correctness.
- **The brain slot is part of Engine.** The runtime has an explicit cognitive decision seam and specialist catalog.
- **Cognition is not always active.** Observation, policy, task recovery, and stable monitoring are often deterministic.
- **Authority is never cognitive.** Even a highly capable model remains a proposal provider.

Read [How Engine learns](./learning.md) for the distinction between experience and weights, and [All modes](./modes.md) for the complete decision taxonomy.
