---
title: Comparison with other projects
description: Layer-level comparison of Engine with automation, robotics, and agent projects.
sidebar_position: 2
---

# Comparison with other projects

This page is a **layer-level comparison, not a uniform benchmark**. These
projects have different goals, maturity levels, ecosystems, and units of
measurement. We have not run the same workload, latency test, safety analysis,
or feature checklist across every project. “Different” therefore does not
automatically mean “better” or “worse.”

The sources below are the projects' official documentation. This comparison
describes their primary architectural focus and where Engine could work with
them.

## Summary

| Project | Primary focus | Overlap with Engine | Important difference in this comparison |
| --- | --- | --- | --- |
| Home Assistant | Smart-home core, integrations, and automations | Entities, state, integrations, automation | Engine investigates a generic typed action/authorization/oracle lifecycle across heterogeneous worlds; Home Assistant is a mature home-automation platform |
| openHAB | Vendor-neutral home automation with Things, Items, and rules | Adapters, device model, rules | Engine separates proposal, exact request, policy, authorization, receipt, and observed effect as a generic core path |
| Node-RED | Flow-based programming | Events, nodes, integrations, orchestration | Engine is not a visual flow editor; GoalSpec and durable authority/evidence are central |
| ROS 2 | Robotics middleware and communication interfaces | Topics/services/actions, distributed targets | Engine does not replace a ROS realtime controller; ROS 2 could instead provide an adapter/body layer |
| OpenAI Agents SDK | Agent workflows, tools, handoffs, tracing, and sessions | Executive/specialist composition, structured output | Engine makes LLMs optional proposal providers and keeps policy/authorization/effect oracle outside agents |
| MCP | Protocol for context and tools between clients and servers | Plugin/tool interoperability | MCP does not itself define Engine's operational state, mandate, request authorization, or fresh-effect oracle |
| LangGraph | Stateful agent orchestration and persistence | Durable workflows, checkpoints, human-in-the-loop | Engine focuses its state machine specifically on target revisions, typed actions, policy, and observed physical/software effects |
| OpenClaw | Personal agent runtime with tools, skills, durable memory, scheduled tasks, and standing intents | Persistent runtime, local operation, memory, tools, event-conditioned work | The difference is not that “Engine has persistence”: Engine focuses on typed operational state plus independent authority and post-effect observation |
| Hermes | Persistent personal agent with memory and agent-managed/self-improving skills | Memory, tools, skills, model use, cross-session improvement | Engine treats learning as bounded evidence/state promotion; a learned skill or model gains no additional execution authority |
| Claude Cowork | Delegation/workspace product for autonomous multi-step knowledge work across selected files and tools | Goals, tool use, scheduled work, sub-agents, reviewable execution | Cowork is an interaction and work-delegation product; Engine is a typed operational runtime that could sit below or beside it |

## Home Assistant

[Home Assistant Core](https://developers.home-assistant.io/docs/architecture/core/)
organizes a mature smart-home platform around core state and integrations, among
other things. Its official documentation also covers
[automations](https://www.home-assistant.io/docs/automation/) and a large
[integration ecosystem](https://www.home-assistant.io/integrations/).

Engine does not try to rebuild Home Assistant. A home platform could provide a
world adapter or execution layer for Engine. Engine's research question sits at
a different layer: can the same Heart also control a filesystem, warehouse,
robot, or other target with exactly the same typed
proposal/authority/receipt/oracle lifecycle? This is not a claim that Engine now
has Home Assistant's reach or maturity.

## openHAB

openHAB documents a vendor- and technology-neutral automation platform in its
[main documentation](https://www.openhab.org/docs/), including an explicit
[Things concept](https://www.openhab.org/docs/concepts/things) and
[rules](https://www.openhab.org/docs/concepts/rules.html).

There is substantial overlap in adaptation and durable automation. For its own
thesis, Engine places additional emphasis on recording the semantic proposal,
target-specific request, deterministic policy, request-bound authorization,
execution receipt, and fresh effect reconciliation separately. This does not
mean that openHAB lacks safety or status mechanisms; those mechanisms have not
been tested against Engine in one uniform benchmark.

## Node-RED

According to its official
[concepts documentation](https://nodered.org/docs/user-guide/concepts), Node-RED
is a flow-based environment with nodes, messages, flows, and context. It is
strong as a visual integration and automation layer.

Engine is not a flow editor and does not try to replace nodes or flows. A
Node-RED flow could later connect as a client or adapter. Engine's distinctive
objects are a typed GoalSpec, durable world snapshots, authority that does not
follow from a model or flow proposal, and success established through a fresh
oracle.

## ROS 2

ROS 2 provides, among other things,
[topics, services, and actions](https://docs.ros.org/en/rolling/Concepts/Basic/Interfaces-Topics-Services-Actions.html)
for distributed robotics components. That is a much richer robotics middleware
layer than Engine aims to be.

Engine must not be placed in hard-realtime feedback loops. A ROS 2 stack or
validated device controller could retain realtime authority beneath an Engine
adapter; Engine would then operate at a semantic task/goal level and observe the
result. Engine does not replace a motion controller, flight stack, watchdog, or
emergency stop.

## OpenAI Agents SDK

The [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) supports
agentic applications with agents, tools, handoffs, and tracing, among other
features. Its
[sessions documentation](https://openai.github.io/openai-agents-python/sessions/)
describes persistent conversation history.

Engine can use an agent or model behind its executive interface. The
architectural difference in this layer-level comparison is that such an agent
provides untrusted proposals only: deterministic policy mints authorization, and
a plugin oracle uses fresh observations to assess the effect. Session memory is
not the operational source of truth.

## Model Context Protocol (MCP)

MCP describes a client/host/server architecture in its official
[architecture documentation](https://modelcontextprotocol.io/docs/learn/architecture)
and server tools in the
[specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

MCP and Engine are complementary. MCP can provide an interoperable context or
tool-transport layer. It does not automatically own Engine's GoalSpec, target
revision, mandate, authorization, idempotency, receipt, or effect oracle. An MCP
tool call must therefore not be treated as an authorized Engine mutation without
an adapter contract.

## LangGraph

[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) focuses on
low-level orchestration of long-running, stateful agents. Its official
[persistence documentation](https://docs.langchain.com/oss/python/langgraph/persistence)
covers checkpoints and durable state.

Engine therefore has no monopoly on persistence or stateful execution. The
difference lies in the specifically enforced world/action semantics:
observations with coverage, target revisions, proposal ≠ authority, exact
request, deterministic policy, receipt ≠ effect, and post-observation/oracle.
LangGraph could carry a deliberative workflow above or alongside Engine.

## OpenClaw

OpenClaw documents an
[agent runtime](https://docs.openclaw.ai/agent),
[durable memory](https://docs.openclaw.ai/concepts/memory), and
[skills](https://docs.openclaw.ai/skills). It would be inaccurate to describe
OpenClaw as only ephemeral chat or prompt state.

Its memory documentation also describes event-conditioned standing intents and
scheduled tasks for future actions. OpenClaw therefore has persistent runtime
behavior as well as memory; “Engine persists” is not a meaningful distinction
on its own.

Engine's positioning therefore does not rest on persistence alone. Its focus is
typed operational state that can be reconstructed after context loss, proposals
without authority, deterministic mandates/authorization, and independently
observed effects. OpenClaw could provide an intent or interaction layer in front
of Engine. That is a possible complementary composition, not a tested integration.

## Hermes

Hermes describes itself in its official
[documentation](https://hermes-agent.nousresearch.com/docs/) as a persistent,
self-improving agent. Its
[skills documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
describes agent-managed skills that can be created and improved during use, and
its [memory documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
describes persistent cross-session memory. “Hermes has no durable memory or
learning” is therefore not a defensible differentiating claim.

Engine uses a narrower definition of learning: plugin-owned behavior evidence
can pass through fixed gates and influence a namespaced preference or routine
version, without training weights or expanding authority. Self-improving skills
might improve proposals in the future, but they would still have to pass through
the same policy and oracle boundary.

Hermes could likewise provide an interaction, delegation, or proposal layer for
an Engine-backed world. The repository does not contain that integration today.

## Claude Cowork

Anthropic presents
[Claude Cowork](https://www.anthropic.com/webinars/future-of-ai-at-work-introducing-cowork)
as a work-delegation experience in which Claude carries out autonomous,
multi-step workflows rather than only answering questions. Anthropic's
[official product guide](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork)
also describes work across user-selected files and tools, scheduled tasks,
parallel sub-agents, and results returned for review.

Cowork and Engine are therefore not separated by “one can do multi-step work.”
They occupy different product layers. Cowork is a user-facing workspace and
delegation product. Engine is an experimental operational runtime for durable
world state, typed target capabilities, independent policy/authorization, and
post-effect observation. A future Cowork workflow could submit intent to Engine
or review its audit evidence, but no Cowork integration is implemented or tested.

## Where Engine does and does not compete

Engine's core hypothesis combines:

- local, typed, and reconstructible operational state;
- living `achieve` and `maintain` goals;
- a replaceable deterministic/model executive plus plugin specialists;
- proposal → request → policy → authorization → execution → observation → oracle;
- the same lifecycle across multiple semantically different worlds.

Engine does not currently claim:

- the integration ecosystem of Home Assistant or openHAB;
- Node-RED's flow UX;
- the robotics middleware and realtime guarantees of ROS 2;
- the general agent-framework breadth of the Agents SDK or LangGraph;
- to replace MCP;
- the skill/assistant/workspace product experience of OpenClaw, Hermes, or Cowork;
- that the table is a performance, safety, or quality benchmark.

OpenClaw, Hermes, and Cowork are possible complementary interaction or cognition
layers. They are not current Engine integrations, and the projects have not been
run as a uniform benchmark.
