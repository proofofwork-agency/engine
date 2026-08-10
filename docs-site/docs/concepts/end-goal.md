---
title: The end goal
sidebar_position: 7
description: Engine's long-term direction, with explicit evidence boundaries and falsifiable intermediate steps.
---

# The end goal

Engine's end goal is a local-first, provider-neutral runtime that turns human intent into typed, bounded, auditable actions across heterogeneous software and physical systems—with a living Heart, replaceable brains, domain-specific plugins, and independent observation of effects. Software policy constrains execution but does not make a physical system safe by itself.

That is a direction, not a current product claim.

> **Implemented:** a working v2 vertical software slice with multi-target world state, goals, brains, plugin contracts, policy/authorization, immediate/task lifecycle, learning/routines, and deterministic reference worlds.
>
> **Fake/simulation-tested:** heterogeneous closed loops, restart, partial/unknown cases, Homey contracts, the warehouse task, and bounded learning.
>
> **Live read-only:** a composed Homey and local-context world was observed without mutation.
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

New worlds must be installable without building a second Heart. A plugin supplies its world providers, controllers, executors, oracles, specialists, and optional experience, routine, or lifecycle-observer components. The runtime discovers them through the v2 manifest and entry point. A lifecycle observer can report a durable milestone, but cannot add facts, propose, authorize, dispatch, or certify an effect.

The end goal is not for every target to have the same capability names. It is for every target to follow the same evidence discipline:

```text
observe -> propose -> validate -> policy -> authorize
        -> dispatch -> observe -> reconcile -> record
```

## Five plugin and application examples

These examples show why Engine is designed around one generic lifecycle and domain-specific plugins. They are not a list of five finished products.

### 1. Smart-home steward

**Application:** keep selected rooms comfortable and efficient without reducing the home to a collection of one-off voice commands. A durable goal might maintain a lighting band while a zone is occupied and dark, then turn the zone off after continuously observed absence.

**Plugin context:** an `engine-homey`-style plugin provides zones, devices, presence, lux, power, declared lighting capabilities, bounded controllers, an executor, and effect oracles. A motion or device event only wakes the Heart. Engine observes again before it proposes a change, and measures light/power afterward instead of treating a device ACK as success. Authority remains limited to exact enrolled zones, capability families, and parameter ceilings.

**Evidence:** whole-home Homey plus local-context observation is **Live read-only**. Lighting mutation, ACK-without-effect, missed-event recovery, quiet monitoring, preferences, and routines are **Fake/simulation-tested**. Repeated physical lux/watt actuation remains **Roadmap**.

### 2. Software-operations caretaker

**Application:** achieve or maintain a workspace condition such as “all incoming reports are validated, normalized, and filed, while failures remain recoverable.” Unlike a one-shot script, the goal survives a process restart and can react when new files appear.

**Plugin context:** a software-operations plugin could expose sandboxed files, jobs, deployments, or service health as typed entities and capabilities. A filesystem event or webhook would wake Engine; a fresh observation would establish what exists now. Exact write/move/run requests would remain bounded by workspace, process, network, and time limits. File hashes, job state, or a deterministic verifier would establish the post-effect result.

**Evidence:** the shared Heart/brain/catalog path, multi-step filesystem goal, partial failure, oracle, and restart are **Fake/simulation-tested** in the older 0.1 sandbox. A production DevOps plugin with deployment authority is **Roadmap**.

### 3. Business and warehouse coordinator

**Application:** maintain a declared inventory reserve or complete a bounded transfer without losing track when the task outlives one model call or process.

**Plugin context:** the warehouse reference plugin exposes bins, crate counts, transfer capabilities, an asynchronous `TASK`, a specialist, and an independent effect oracle. The Heart can start the task, persist its handle, poll, cancel at a deadline, reconstruct after restart, and compare fresh bin counts with the goal. A transport acceptance does not prove that crates moved.

**Evidence:** the separately installable reference-world plugin and its start/poll/cancel/restart path are **Implemented** and **Fake/simulation-tested**. Connection to a real warehouse management system is **Roadmap**.

### 4. Energy coordinator

**Application:** maintain a home or site power envelope while coordinating flexible loads, tariffs, solar production, and battery state—for example, defer a discretionary load while the reserve is low and resume it when independently observed conditions recover.

**Plugin context:** an energy plugin would need explicit units, meter coverage, tariff validity, controllable-load families, budgets, and stale/conflict behavior. It could propose high-level schedules or bounded setpoints, but target-native battery and inverter controllers would retain their local protection and realtime behavior. Post-effect energy measurements, not forecasts or API acknowledgements, would determine the result.

**Evidence:** generic `MAINTAIN`, policy, task, and oracle contracts are **Implemented**; the described cross-device energy plugin and live closed loop are **Roadmap**.

### 5. Robotics mission layer

**Application:** ask a tabletop robot to achieve a semantic outcome such as moving an identified object to an allowed tray, while the robot controller owns trajectories, collision constraints, force limits, watchdogs, and emergency stop behavior.

**Plugin context:** a robotics plugin would expose observed objects and poses with explicit frames and units, high-level capabilities, task handles, controller limits, and target-specific oracles. Engine could choose a goal-level action and reconcile the observed result, but no LLM would emit raw motor setpoints or occupy the hard-realtime loop. Software policy would complement, never replace, independent physical safety.

**Evidence:** a discrete grid and heterogeneous lifecycle are **Fake/simulation-tested** as software evidence. A tabletop pick-and-place plugin, hardware test, and target-specific safety case are **Roadmap**; drones, vehicles, and broad physical autonomy are not implied.

### Why the shared core is powerful

The leverage comes from reusing the difficult operational discipline without pretending the domains are the same. Every application receives durable `ACHIEVE`/`MAINTAIN` goals, reconstructible state, one replaceable general executive, optional specialists, proposal-versus-authority separation, task recovery, receipts, and post-effect reconciliation. Each plugin still owns its entities, schemas, units, capabilities, limits, controller, oracle, and failure semantics.

That makes a sixth world a test of a contract, not a reason to fork the Heart. It also makes the system easier to falsify: if a domain needs a different authority model or cannot supply adequate observation/oracle coverage, Engine must expose that limitation instead of hiding it behind fluent model output.

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
| 0.1 identity | Heart + general brain + specialist + two heterogeneous sandbox/simulation worlds + oracle + restart | **Fake/simulation-tested**; owner review remains the governance closure |
| v2 software slice | Multi-target GoalSpec, public SDK, installed plugins, full action lifecycle, task recovery, learning/routines | **Implemented** and **Fake/simulation-tested** |
| Bounded physical proof | One low-energy Homey zone, fresh lux/watt measurements, five consecutive closed loops | **Roadmap**; open gate |
| Plugin hardening | Broader conformance use, stream reference, production supervision, QoS, packaging, and migrations | **Roadmap** |
| Learned specialists | Mini-brain only where a simple baseline demonstrably falls short | **Roadmap** hypothesis |
| Broad physical deployment | Target-by-target safety case, controller contract, and independent evidence | **Roadmap**, long term and never inferred from simulation |

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
