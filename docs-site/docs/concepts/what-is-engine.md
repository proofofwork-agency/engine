---
title: What is Engine?
sidebar_position: 1
description: A grounded explanation of Engine, the current implementation, and the boundary between vision and evidence.
---

# What is Engine?

Engine is a local-first runtime that connects persistent goals to typed observations and bounded actions across different worlds. The system combines a **Heart** for continuity with a **general brain**, **specialist brains**, and **world plugins**. A model may propose an action; only Engine can validate, authorize, execute, and observe the effect again.

> **Status labels used in this documentation**
>
> - **Exists now** — implemented in the current v2 code and public contracts.
> - **Tested in a fake/simulation** — proven through automation or preserved experiments, but not automatically proven on real hardware.
> - **Roadmap** — direction or hypothesis; do not present it as a current product capability.

## The short version

A conventional agent harness starts with a model turn: the user asks for something, the model selects a tool, and the transcript remembers what happened. Engine starts with a durable world and a durable goal:

```text
record goal
  -> observe world
  -> determine whether the goal is already true
  -> propose a bounded action if needed
  -> check schema, preconditions, policy, and mandate
  -> authorize and execute the exact request
  -> observe again
  -> compare expected and actual effect
  -> complete the goal or continue maintaining it
```

Operational truth therefore does not live in a prompt. Goals, snapshots, observations, policy decisions, authorizations, receipts, and effects are stored durably and can be reconstructed after process or provider loss.

## What Engine consists of

| Component | Responsibility | Status |
| --- | --- | --- |
| **Heart** | Keeps goals, world state, attention, cycles, experience, and recovery alive | **Exists now** |
| **General brain** | Selects the next cognitive step, specialist, or semantic effect | **Exists now**: deterministic or model-backed |
| **Specialist brains** | Provide bounded, domain-specific advice and optionally a typed proposal | **Exists now**; multiple specialists can be registered at once |
| **World plugins** | Observe targets and translate Engine contracts into domain-specific semantics | **Exists now** through `engine.plugin/v2` |
| **Policy and authorization** | Decide outside every brain whether an exact request may execute | **Exists now** as deny-by-default mandate policy |
| **Executor and effect oracle** | Execute an authorized request and verify its effect against fresh state | **Exists now** |
| **Learning/routines** | Process explicit corrections and bounded behavior signals without expanding authority | **Exists now**, primarily tested with fakes/simulations |
| **Hard-realtime controller and safety hardware** | Enforce timing, interlocks, watchdogs, and physical limits | Belongs to the target; **not** the deliberative Heart loop |

Read [Heart and brains](./heart-and-brains.md) for the exact division of responsibility and [Architecture](./architecture.md) for the full v2 chain.

## Two kinds of goals

Engine has two canonical goal modes:

- `ACHIEVE`: reach an effect once, then become `completed`;
- `MAINTAIN`: keep an effect true. When the world is stable, the goal becomes `monitoring`; observed drift reactivates the loop.

A `MAINTAIN` goal makes the difference from a one-off workflow clear. “Turn on light A” is a command. “Keep this workspace between 350 and 450 lux, under a power budget” is a persistent desired state. While the state is stable, Engine should continue observing without repeatedly calling the general or specialist brain.

Both goal modes **exist now**. The quiet-monitoring, drift, and repair route has been tested in deterministic fakes/simulations. A v2 Homey observation run exists, but the decisive physical lux/watt actuation test remains on the roadmap. See [All modes](./modes.md).

## Which worlds exist now?

The current repository contains several layers of evidence:

| World | What it proves | Evidence boundary |
| --- | --- | --- |
| Sandbox filesystem and discrete grid | The original 0.1 acceptance: the same Heart/brain/catalog path, partial effect, oracle, and restart | **Tested in a sandbox/simulation**; this is the older v1 acceptance layer |
| Reference warehouse plugin | A separately installable, non-household v2 world with a durable `TASK`, polling, deadline cancellation, oracle, and restart | **Tested in a fake/simulation** |
| Engine Homey/HomeOps | Whole-house world model, events as wake hints, polling, typed actions, sensor oracles, preferences, and routines | **Fake-tested**; only live observe-only operation is proven, not v2 actuation |
| Engine Context | Local time, scheduled wakes, confirmed location, and optional weather with an explicit privacy choice | **Exists now**; missing data remains `UNKNOWN` |

These examples prove that a shared lifecycle can support different domains. They do not prove that every possible machine is already supported or can be operated safely.

## Why “local-first”?

Local-first means here that:

- the complete operational state and audit trail remain in local stores;
- the system works with a deterministic brain and no external model provider;
- a local or remote OpenAI-compatible provider can be used optionally;
- a remote model URL without an API key fails closed;
- a model receives a bounded context projection, not the complete world by default;
- plugins declare network, filesystem, secret, and privacy needs.

Local-first does not mean “without a network,” nor does it mean “automatically safe.” A plugin may require network access; a human must configure that boundary deliberately.

## Is an LLM part of Engine?

Intelligence is part of the Engine concept, but no particular LLM provider is. The current runtime can compose exactly one general executive brain:

- a transparent deterministic executive for known, stable routes; or
- a model-backed executive behind a provider-neutral structured-output contract.

Plugins may also register specialist brains. Every brain produces untrusted, typed input. It cannot create permission, declare an effect observed, or bypass a safety rule. Core correctness must continue to work when every LLM provider disappears or is replaced.

## What can and cannot Engine do today?

### It can

- manage durable, multi-target `GoalSpecV2` goals and composed `WorldSnapshotV2` state;
- execute `ACHIEVE` and `MAINTAIN` goals;
- compose one general brain and multiple specialists;
- validate plugin manifests, capability families, units, limits, and schemas;
- durably record the complete proposal-to-effect lifecycle;
- handle immediate actions and durable tasks with polling, cancellation, and restart;
- process explicit preference corrections and bounded routine/preference candidates;
- scaffold new v2 plugins with the SDK and discover them through entry points.

### It cannot yet claim broadly

- control arbitrary devices without a predeclared plugin contract;
- run hard-realtime motor, flight, or stabilization loops;
- replace physical safety hardware, certification, or fail-safe behavior;
- arbitrate multiple competing general brains as a first-class feature;
- prove that multi-brain systems are always better than a monolith;
- train model weights online or create a new neural brain from experience by itself;
- provide an end-to-end `STREAM` reconnect reference proof;
- claim that physical Homey actuation has passed the v2 trial.

Read [What Engine is not](./what-engine-is-not.md) for the hard boundaries and [The end goal](./end-goal.md) for the direction behind the current vertical slice.

## Core identity rules

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

These separations are not merely an extra safety layer around Engine; they determine how Engine interprets its own state, decisions, and evidence.
