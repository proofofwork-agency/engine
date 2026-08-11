---
title: Engine at a glance
sidebar_position: 1
slug: /intro
description: Start here for the mental model, the current evidence boundary, and the right reading path.
---

# Engine at a glance

Engine is an experimental, local-first runtime for durable goals across software and physical worlds. It combines a durable **Heart**, exactly one active and replaceable **general executive brain**, zero or more **specialist brains**, and installable **world plugins**.

A request can be immediate—“turn this light off”—or become a durable intent: `ACHIEVE` an outcome once, or `MAINTAIN` it as the world changes. Engine persists that intent independently of the conversation, model, or process that first expressed it.

```text
interaction  ->  intelligence  ->  Engine  ->  target / world
chat or API      model/planner     durable     software, home,
                                  runtime      business, energy,
                                               or machine
```

The intelligence layer is replaceable cognition, not operational authority. The design starts with a current world and a desired world that continue to exist without a model context:

```text
durable current world + durable desired goal
                |
                v
     event or poll wakes the Heart
                |
                v
         observe again and assess
                |
                v
      brain/specialist proposes
                |
                v
 schema -> policy -> authorization
                |
                v
       execute -> observe again
                |
                v
      oracle -> receipt -> experience
```

A brain may choose and propose. The Heart maintains the cycle, state, and causal history. Policy grants or denies authority. A target-specific executor acts. An event is only a wake-up hint, and an API acknowledgement is only an execution fact. Only a fresh observation and an effect oracle may establish what actually happened within their current coverage.

## The essence in four statements

1. **Heart means continuity.** Goals, snapshots, receipts, and experience remain durable outside the model session.
2. **Brain means replaceable cognition, not authority.** A deterministic planner or model-backed executive chooses the next cognitive step; specialists provide bounded advice.
3. **Plugins represent worlds with their own semantics.** Providers observe; controllers translate; executors act; oracles measure effects.
4. **Success requires independent evidence.** Model output or an API acknowledgement is never enough.

## What to expect today

| Status | Meaning in this documentation |
| --- | --- |
| **Implemented** | Present in the current action lifecycle and v3 plugin contracts |
| **Fake/simulation-tested** | Proved automatically, but not evidence of physical safety |
| **Live read-only** | Observed against a real target without mutation |
| **Roadmap** | A direction or hypothesis, not a feature available today |

The current repository contains:

- `engine-heart`, with the Heart, durable world store, policy, learning, and routines;
- `engine-sdk`, with `engine.plugin/v3`, v2 compatibility, scaffolding, and conformance tooling;
- `engine-runtime`, with the composition root, discovery, lease, and the `engine` CLI;
- a warehouse reference plugin, context plugin, Homey plugin, and opt-in bounded ntfy lifecycle observer;
- tests for reconstruction, stale/denied/malformed cases, immediate and task lifecycles, and bounded learning.

The current evidence boundary is deliberately narrower than the vision: Homey observation is **Live read-only**, while its v2 mutation path is **Fake/simulation-tested**. `STREAM`, multiple general executive brains, trained mini-brains, and physical-safety certification have not been demonstrated. [The end goal](concepts/end-goal.md#five-plugin-and-application-examples) works through five possible applications and labels each one at this boundary.

## Choose a reading path

### I want to understand Engine

1. [What is Engine?](concepts/what-is-engine.md)
2. [What Engine is not](concepts/what-engine-is-not.md)
3. [Heart and brains](concepts/heart-and-brains.md)
4. [Architecture](concepts/architecture.md)

### I want to understand every capability and boundary

1. [Modes and statuses](concepts/modes.md)
2. [How Engine learns—and how it does not](concepts/learning.md)
3. [The end goal](concepts/end-goal.md)
4. [Status and evidence](reference/status-and-evidence.md)

### I want to build

1. [Quickstart](developers/quickstart.md)
2. [Plugin interface v3](developers/plugin-interface.md)
3. [SDK reference](developers/sdk.md)
4. [CLI reference](developers/cli.md)
5. [Multiple plugins and brains](developers/multiple-plugins-and-brains.md)
6. [Plugin checklist](developers/plugin-checklist.md)

### I want to position Engine

- [Comparison with other projects](reference/comparison.md)
- [Glossary](reference/glossary.md)
- [Frequently asked questions](reference/faq.md)

## The fixed checksum

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

These statements are not slogans added after the fact. They define which code, tests, and claims belong in Engine.
