---
title: Engine at a glance
sidebar_position: 1
slug: /intro
description: Start here for the mental model, the current evidence boundary, and the right reading path.
---

# Engine at a glance

Engine is an experimental, local-first runtime for durable goals across software and physical worlds. It combines a durable **Heart**, one replaceable **general executive brain**, zero or more **specialist brains**, and installable **world plugins**.

The design starts with a world that continues to exist without a model context, rather than with a chat session:

```text
durable world state + durable goal
                |
                v
          observe and assess
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

A brain may choose and propose. The Heart maintains the cycle, state, and causal history. Policy grants or denies authority. A target-specific executor acts. Only a fresh observation and an effect oracle may establish what actually happened.

## The essence in four statements

1. **Heart means continuity.** Goals, snapshots, receipts, and experience remain durable outside the model session.
2. **Brain means cognition, not authority.** A deterministic or model-backed executive chooses the next cognitive step; specialists provide bounded advice.
3. **Plugins represent worlds with their own semantics.** Providers observe; controllers translate; executors act; oracles measure effects.
4. **Success requires independent evidence.** Model output or an API acknowledgement is never enough.

## What to expect today

| Status | Meaning in this documentation |
| --- | --- |
| **Implemented** | Present in the current v2 code and public contracts |
| **Tested with a fake or simulation** | Proved automatically, but not evidence of physical safety |
| **Live read-only** | Observed against a real target without mutation |
| **Roadmap** | A direction or hypothesis, not a feature available today |

The current repository contains:

- `engine-heart`, with the Heart, durable world store, policy, learning, and routines;
- `engine-sdk`, with `engine.plugin/v2`, scaffolding, and conformance tooling;
- `engine-runtime`, with the composition root, discovery, lease, and the `engine` CLI;
- a warehouse reference plugin, context plugin, and Homey plugin;
- tests for reconstruction, stale/denied/malformed cases, immediate and task lifecycles, and bounded learning.

The current evidence boundary is deliberately narrower than the vision: Homey has been observed live in read-only mode, but v2 mutations have only been tested with a fake. `STREAM`, multiple general executive brains, trained mini-brains, and physical-safety certification have not been demonstrated.

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
2. [Plugin interface v2](developers/plugin-interface.md)
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
