---
title: The end goal
sidebar_position: 7
description: Engine's long-term direction, with explicit evidence boundaries and falsifiable intermediate steps.
---

# The end goal

Engine's end goal is a local-first, provider-neutral runtime that turns human intent into safe, typed, auditable actions across heterogeneous software and physical systems—with a living Heart, replaceable brains, domain-specific plugins, and independent observation of effects.

That is a direction, not a current product claim.

> **Now:** a working v2 vertical software slice with multi-target world state, goals, brains, plugin contracts, policy/authorization, immediate/task lifecycle, learning/routines, and deterministic reference worlds.
>
> **Tested in a fake/simulation:** heterogeneous closed loops, restart, partial/unknown cases, Homey contracts, the warehouse task, and bounded learning.
>
> **Roadmap:** decisive physical evidence, broader plugin conformance, operational hardening, and only then learned mini-brains where a baseline limitation has been measured.

## The intended end architecture

```text
human intent / API / optional assistant
                    |
                    v
          durable GoalSpec + mandate
                    |
                    v
       a Heart that keeps observing
          /          |           \
 general brain   specialists   deterministic tools
          \          |           /
                    v
       semantic ProposedAction (untrusted)
                    |
         validate -> policy -> authorization
                    |
                    v
     plugin controller/executor -> target controller
                    |
           fresh observation + oracle
                    |
            durable receipt/effect
```

The same generic path should work for a filesystem, software service, home, warehouse, and eventually a physical body. Only lifecycle and evidence are generic; each domain retains its own units, frames, limits, controllers, and safety envelope.

## What “living” ultimately means

Engine does not become living only when an LLM talks constantly. A mature Heart:

- owns goals and world state outside model sessions;
- keeps running without a human impulse at every step;
- remains quiet when maintained state is demonstrably stable;
- wakes on events or polling, but always observes again;
- can prioritize multiple goals fairly;
- recovers or defers after provider, process, and target failures;
- distinguishes `UNKNOWN`, conflict, and stale evidence from false;
- can replace brains without operational amnesia;
- can reconstruct an exact audit path from intent to effect.

An always-on loop is not the same as a hard-realtime loop. The target controller retains authority over timing-critical stabilization.

## What “multiple worlds” ultimately means

New worlds must be installable without building a second Heart. A plugin supplies its world providers, controllers, executors, oracles, specialists, and optional experience/routine components. The runtime discovers them through the v2 manifest and entry point.

The end goal is not for every target to have the same capability names. It is for every target to follow the same evidence discipline:

```text
observe -> propose -> validate -> policy -> authorize
        -> dispatch -> observe -> reconcile -> record
```

## The long-term role of brains

The stable topology remains:

- one general executive brain for situation understanding and strategy;
- multiple replaceable specialists for narrow cognitive tasks;
- deterministic controllers/tools for known logic;
- the Heart as lifecycle and continuity owner;
- policy, authorization, and effect truth outside every brain.

A future runtime may compose multiple general providers, ensembles, or fallbacks. That is responsible only when identity, budget, conflict, timeout, and arbitration are explicit contracts. “More models” is not a goal by itself.

## The long-term role of learning

Engine must be able to make experience useful without confusing state, authority, and weights. The expected ladder is:

1. durable observed outcomes and corrections;
2. deterministic plan reuse and preference/routine adaptation;
3. reusable specialist skills;
4. only after evidence of need: versioned mini-brain artifacts;
5. rollout, monitoring, and rollback under the same plugin and policy boundaries.

Engine does not need to train its own foundation model. The end goal is provider-neutral cognition, not model ownership. See [How Engine learns](./learning.md).

## SDK, CLI, and plugin ecosystem

The current `engine-sdk` and `engine-runtime` form the first public builder layer:

- `engine-plugin init` scaffolds `world`, `specialist`, or `full`;
- manifest validation and conformance can run outside core;
- `engine` discovers installed plugins;
- the CLI inspects plugins/world state and manages setup, run, status, learning, routines, and bounded autonomy profiles.

The end goal is a reusable ecosystem in which:

- plugin imports remain inert and manifests statically inspectable;
- the same black-box conformance runs against every implementation;
- packages declare their own stores/migrations and permissions;
- versioning and artifact identity make upgrades reconstructible;
- a new plugin requires no branches in Heart.

A marketplace, hot reload, or cross-language SDK is not a proven current feature and is not required for the core thesis.

## Phases and gates

| Phase | Goal | Current status |
| --- | --- | --- |
| 0.1 identity | Heart + general brain + specialist + two heterogeneous sandbox/simulation worlds + oracle + restart | **Implementation audit PASS**; owner review remains the governance closure |
| v2 software slice | Multi-target GoalSpec, public SDK, installed plugins, full action lifecycle, task recovery, learning/routines | **Exists now**, reference/fake-tested |
| Bounded physical proof | One low-energy Homey zone, fresh lux/watt measurements, five consecutive closed loops | **Roadmap/open gate** |
| Plugin hardening | Broader conformance use, stream reference, production supervision, QoS, packaging, and migrations | **Roadmap** |
| Learned specialists | Mini-brain only where a simple baseline demonstrably falls short | **Roadmap/hypothesis** |
| Broad physical deployment | Target-by-target safety case, controller contract, and independent evidence | **Long term**, never inferred from simulation |

## The next decisive experiment

More core design is not the next truth test. The repository identifies one bounded Homey lighting zone as the flagship gate:

- only explicitly configured low-risk lights;
- current lux and watt observations;
- acknowledgement without measured effect does not count;
- events only wake; polling/observation confirms;
- drift is repaired and stable state causes zero brain calls;
- five consecutive runs under a preregistered protocol;
- independent rollback and transport kill switch.

Until that experiment succeeds, “physically proven closed loop” remains a non-claim.

## How the project can falsify itself

Engine misses its own end goal when:

- goals or truth still live only in a model session;
- a new domain requires a second Heart;
- an acknowledgement or model text counts as effect evidence;
- stable monitoring requires continuous model calls;
- a plugin can create permission itself;
- learning silently expands authority or device scope;
- a deliberative model call enters a hard-realtime feedback loop;
- gates are moved after an experiment fails.

Negative experiments are therefore valuable. A simple rule, script, or existing controller that performs better under the same budget may show that a brain, mini-brain, or even Engine is unnecessary for that problem.

## What the end goal explicitly is not

- a universal AGI butler;
- a chat gateway with as many tools as possible;
- a marketplace that automatically grants execution rights to untyped skills;
- a replacement for Homey, Home Assistant, ROS, PLCs, flight stacks, or safety hardware;
- a promise that every device can be learned without engineering;
- an owned foundation model as a necessary moat;
- general physical certification inferred from internal tests.

## When is Engine “done”?

Not when every imaginable plugin exists. A convincing Engine version is ready for a bounded release when:

- the claim and null are clear in advance;
- state, identity, authority, and lifecycle are reconstructible;
- the relevant fake, fault, restart, and conformance gates pass;
- a target-specific oracle measures the effect independently;
- uncertain and negative outcomes remain preserved;
- rollback, limitations, and the safety boundary are documented;
- core correctness needs no particular LLM provider.

Start with [What is Engine?](./what-is-engine.md), deepen the separation in [Heart and brains](./heart-and-brains.md), and use [Architecture](./architecture.md) as the contract map.
