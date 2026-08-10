---
title: What Engine is not
sidebar_position: 2
description: Non-goals, product boundaries, and a cautious comparison with other project categories.
---

# What Engine is not

Engine is deliberately narrower than the claim “an autonomous system that can do everything.” Its value lies precisely in its boundaries: a durable Heart loop, replaceable brains, typed plugins, and independent observation of effects.

> **Status of this page:** the architecture boundaries below are **existing contracts or accepted design decisions**. The comparisons are positioning, not a current benchmark or superiority claim.

## Not a chat assistant or messaging gateway

Engine does not treat a WhatsApp, Telegram, or inbox experience as its core object. A chat interface may later supply intent, but it would not own the goal, world state, or execution authority.

The difference is subtle but important:

- an assistant usually optimizes the next interaction with a user;
- Engine manages a desired state of a world, even when no conversation is active.

## Not an “LLM plus tools” harness

A tool call in a transcript is not yet an Engine action. In v2, model output first becomes a `ProposedActionV1`, then potentially an exact `ActionRequestV1`, a `PolicyDecisionV1`, an `AuthorizationV1`, an `ExecutionReceiptV2`, and only after fresh observation an `EffectDeltaV1`.

The model:

- does not own authoritative state;
- may not authorize its own proposal;
- may not rename an acknowledgement into an achieved effect;
- may not call an unconstrained device API outside the capability contract.

## Not a conventional workflow engine

Engine can execute multi-step work and durable tasks, but a fixed process graph is not its identity. The Heart can observe a world again, preserve `UNKNOWN`, consult a specialist, wait for a relevant change, and reactivate a maintained goal.

For a fully known administrative workflow, a script or workflow engine may be simpler and better. Engine becomes relevant when world state, persistent goals, heterogeneous targets, and independent effect reconciliation are central.

## Not a universal device abstraction

Engine standardizes the lifecycle, not the physics or semantics of every target. A file, warehouse bin, light, robot arm, and drone do not share an artificial universal command.

A plugin therefore keeps the following domain-specific:

- entities, relations, observations, and units;
- capability families and parameters;
- preconditions, limits, and recovery;
- controller translation and effect oracle;
- specialist strategy.

What remains generic is described in [Architecture](./architecture.md).

## Not a hard-realtime controller

The Heart loop is always-on but deliberative. Model calls, network traffic, SQLite, policy evaluation, and plugin polling provide no hard deadline guarantee. Motor stabilization, force limiting, flight control, and equivalent loops belong in a validated local controller.

Engine may later request a high-level setpoint or skill invocation. The target controller retains realtime authority. A delayed Heart cycle must never be the only reason a physical system stays within safe limits.

## Not a replacement for safety hardware

Software policy is not an emergency stop, interlock, watchdog, or certified safety component. Where independence is required, the safety plane must be able to refuse or stop without depending on the same process, network, or model as the command path.

The current fake and simulation tests are therefore lifecycle evidence. They are not certification and do not support a general physical-safety claim.

## Not a world model that turns predictions into truth

Engine may later use Umwelt or another `WorldModelPort` for predicted effects, dynamics, or planning. That advice remains `INFERRED` until an Engine observation or deterministic oracle supports something stronger.

The ownership boundary is:

- Engine: capabilities, policy, authorization, execution, target safety, and operations;
- Umwelt or another model provider: advisory reconstruction, prediction, and planning;
- target providers, executors, and oracles: operational observation within their documented coverage.

## Not a self-learning AGI

Engine currently trains no general model and does not create new weights automatically. What is currently called “learning” is bounded, inspectable state adaptation: collecting evidence, treating a preference or routine as a candidate, shadowing it, creating a new `GoalSpec` version, and supporting exact rollback.

A future mini-brain is a specialist skill with explicit scope, model artifact, training provenance, evaluation, and fallback. It never receives more authority merely because it is learned. See [How Engine learns — and does not learn](./learning.md).

## Comparison with other projects and categories

The table below compares each system's primary object. It does not claim that Engine is broader, better, or more production-ready.

| Project/category | Primary object | Overlap with Engine | Key difference |
| --- | --- | --- | --- |
| **OpenClaw** | Self-hosted personal agent/gateway around channels, sessions, and tools | Always-on runtime, local deployment, replaceable models, tools | Engine centers durable world state, maintained goals, and effect oracles; a chat gateway is not the core |
| **Hermes Agent** | Personal agent with an experience-to-skill loop | Persistence, tools, specialization, and compounding experience | Hermes centers reusable agent skills; Engine centers a typed multi-world lifecycle and bounded GoalSpec/routine adaptation |
| **LangGraph/Temporal-style orchestration** | Explicit workflows, state machines, and durable jobs | Retries, durable state, and multi-step execution | Engine adds world snapshots, brains as proposal providers, capability policy, and post-effect oracles; orchestration may be simpler for fixed workflows |
| **Home Assistant/Homey automation** | Product- or domain-specific device control and automations | Events, state, devices, and routines | Engine uses such a platform as a target/world through a plugin; it does not replace the platform or its local controllers |
| **ROS/PLC/flight-stack category** | Device communication and/or realtime physical control | Adapters, capabilities, and actions targeting physical systems | Engine is the deliberative intent and policy layer above it, not the realtime control or safety layer |
| **Umwelt** | World-model and research primitives | State reconstruction, predicted effects, uncertainty, and planning | Umwelt output is advisory; Engine owns concrete action, policy, authorization, and execution |

The honest current position is this: OpenClaw and Hermes have a different product focus and a more mature user-facing surface; Engine has a narrower, experimental kernel with stronger explicit world/action contracts. The repository does not yet contain an executed, pinned head-to-head benchmark.

## What the current implementation does not prove

### **Tested in a fake/simulation, not physically proven**

- Homey closed-loop behavior, sensor oracles, event/poll recovery, routines, and YOLO scope;
- warehouse task polling, cancellation, and restart;
- learning routes across different plugin domains;
- multi-world lifecycle and restart reconstruction.

### **Exists as contract/scaffolding, without a complete reference proof**

- `STREAM` invocation and reconnect/cursor semantics.

### **Roadmap**

- five consecutive bounded live Homey lux/watt runs;
- broader external plugin conformance and operational hardening;
- production supervision, distribution, and event QoS;
- mini-brain training after measured evidence of need;
- physical expansion per target and risk envelope.

## When should you use something else?

- Choose a chat agent when channels, conversations, and fast software tools are the product.
- Choose a workflow engine when the process is fixed and the state machine is known in advance.
- Choose a Homey/Home Assistant automation when a local rule solves the problem completely.
- Choose a PLC, realtime controller, or certified safety solution for timing-critical or hazardous control.
- Choose Engine when the experiment specifically concerns durable goals, heterogeneous worlds, brains as untrusted proposal providers, and independently established effects.
