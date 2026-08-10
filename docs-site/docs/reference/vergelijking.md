---
title: Vergelijking met andere projecten
description: Laagvergelijking van Engine met automation-, robotics- en agentprojecten.
sidebar_position: 2
---

# Vergelijking met andere projecten

Deze pagina is een **laagvergelijking, geen uniforme benchmark**. De projecten
hebben verschillende doelen, volwassenheid, ecosystemen en meeteenheden. We
hebben geen identieke workload, latencytest, veiligheidsanalyse of
featurechecklist over alle projecten uitgevoerd. “Anders” betekent daarom niet
automatisch “beter” of “slechter”.

De bronnen hieronder zijn de officiële projectdocumentatie. De vergelijking
beschrijft het primaire architectuurzwaartepunt en waar Engine ermee kan
samenwerken.

## Samenvatting

| Project | Primair zwaartepunt | Overlap met Engine | Belangrijk verschil in deze vergelijking |
| --- | --- | --- | --- |
| Home Assistant | Smart-home core, integrations en automations | Entities, state, integrations, automation | Engine onderzoekt een generieke typed action/authorization/oracle-lifecycle over heterogene werelden; Home Assistant is een volwassen home-automationplatform |
| openHAB | Vendorneutrale home automation met Things/Items/rules | Adapters, model van apparaten, regels | Engine scheidt proposal, exact request, policy, authorization, receipt en observed effect als generiek kernpad |
| Node-RED | Flow-based programming | Events, nodes, integraties, orkestratie | Engine is geen visuele flow-editor; GoalSpec en duurzame authority/evidence staan centraal |
| ROS 2 | Roboticsmiddleware en communicatie-interfaces | Topics/services/actions, gedistribueerde targets | Engine vervangt geen ROS-realtimecontroller; ROS 2 kan juist een adapter/body-laag zijn |
| OpenAI Agents SDK | Agentworkflow, tools, handoffs, tracing en sessions | Executive/specialistcompositie, structured output | Engine maakt LLM's optionele proposal providers en houdt policy/authorization/effectoracle buiten agents |
| MCP | Protocol voor context en tools tussen clients en servers | Plugin/tool interoperability | MCP definieert niet op zichzelf Engine's operational state, mandate, request authorization of fresh-effect oracle |
| LangGraph | Stateful agentorkestratie en persistence | Durable workflows, checkpoints, human-in-the-loop | Engine richt de state machine specifiek op targetrevisions, typed actions, policy en observed physical/software effects |
| OpenClaw | Persoonlijke agentruntime met tools, skills en duurzame memory | Local/persistent agentervaring, skills | Verschil is niet “Engine heeft persistence”: Engine focust op typed operational state plus onafhankelijke authority en post-effectobservatie |
| Hermes | Persoonlijke agent met memory en uitbreidbare/self-improving skills | Memory, tools, skills, modelgebruik | Engine behandelt leren als begrensde evidence/statepromotie; een skill of model krijgt geen extra execution authority |

## Home Assistant

[Home Assistant Core](https://developers.home-assistant.io/docs/architecture/core/)
organiseert een volwassen smart-homeplatform rond onder andere core state en
integrations. De officiële documentatie beschrijft ook
[automations](https://www.home-assistant.io/docs/automation/) en een groot
[integratie-ecosysteem](https://www.home-assistant.io/integrations/).

Engine probeert Home Assistant niet opnieuw te bouwen. Een homeplatform kan een
wereldadapter of uitvoeringslaag voor Engine zijn. Engine's onderzoeksvraag zit
een laag anders: kan dezelfde Heart ook een filesystem, warehouse, robot- of
ander target besturen met exact dezelfde typed proposal/authority/receipt/oracle-
lifecycle? Dat is geen claim dat Engine nu het bereik of de volwassenheid van
Home Assistant heeft.

## openHAB

openHAB documenteert een vendor- en technologieneutraal automationplatform in de
[hoofddocumentatie](https://www.openhab.org/docs/), met een expliciet
[Things-concept](https://www.openhab.org/docs/concepts/things) en
[rules](https://www.openhab.org/docs/concepts/rules.html).

De overlap is sterk bij adaptering en duurzame automation. Engine legt voor zijn
eigen thesis extra nadruk op het afzonderlijk vastleggen van semantisch proposal,
target-specifiek request, deterministic policy, request-gebonden authorization,
execution receipt en verse effectreconciliatie. Dit zegt niet dat openHAB geen
veiligheids- of statusmechanismen heeft; die zijn niet als één uniforme benchmark
tegen Engine getest.

## Node-RED

Node-RED is volgens de officiële
[conceptendocumentatie](https://nodered.org/docs/user-guide/concepts) een
flow-based omgeving met nodes, messages, flows en context. Het is sterk als
visuele integratie- en automationlaag.

Engine is geen flow-editor en probeert nodes/flows niet te vervangen. Een
Node-RED-flow kan later als client of adapter koppelen. Engine's onderscheidende
objecten zijn een typed GoalSpec, durable world snapshots, authority die niet uit
een model/flowvoorstel volgt en succes via een verse oracle.

## ROS 2

ROS 2 biedt onder andere
[topics, services en actions](https://docs.ros.org/en/rolling/Concepts/Basic/Interfaces-Topics-Services-Actions.html)
voor gedistribueerde roboticacomponenten. Dat is een veel rijkere
roboticsmiddlewarelaag dan Engine probeert te zijn.

Engine mag niet in hard-realtime feedbackloops zitten. Een ROS 2-stack of
gevalideerde devicecontroller kan onder een Engine-adapter de realtime authority
behouden; Engine werkt dan op semantische task-/doelniveau en observeert het
resultaat. Engine vervangt geen motion controller, flight stack, watchdog of
e-stop.

## OpenAI Agents SDK

De [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) ondersteunt
agentic toepassingen met onder meer agents, tools, handoffs en tracing. De
[sessions-documentatie](https://openai.github.io/openai-agents-python/sessions/)
beschrijft persistent conversation history.

Engine kan een agent of model achter zijn executive-interface gebruiken. Het
architectuurverschil in deze laagvergelijking is dat zo'n agent alleen
onbetrouwbare proposals levert: deterministic policy mint authorization en een
pluginoracle gebruikt verse observations om effect te beoordelen. Sessionmemory
is niet de operationele source of truth.

## Model Context Protocol (MCP)

MCP beschrijft een client/host/serverarchitectuur in de officiële
[architectuurdocumentatie](https://modelcontextprotocol.io/docs/learn/architecture)
en servertools in de
[specificatie](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

MCP en Engine zijn complementair. MCP kan een interoperabele context- of
tooltransportlaag zijn. Het bezit niet automatisch Engine's GoalSpec,
targetrevision, mandate, authorization, idempotency, receipt of effectoracle.
Een MCP-toolcall mag daarom niet zonder adaptercontract als geautoriseerde
Engine-mutatie worden behandeld.

## LangGraph

[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) richt zich
op low-level orchestration van long-running stateful agents. De officiële
[persistence-documentatie](https://docs.langchain.com/oss/python/langgraph/persistence)
behandelt checkpoints en duurzame state.

Engine heeft dus geen monopolie op persistence of stateful execution. Het
verschil zit in de specifiek afgedwongen wereld/actionsemantiek: observations met
coverage, targetrevisions, proposal ≠ authority, exact request, deterministic
policy, receipt ≠ effect en post-observation/oracle. LangGraph kan boven of naast
Engine een deliberatieve workflow dragen.

## OpenClaw

OpenClaw documenteert een
[agent runtime](https://docs.openclaw.ai/agent),
[duurzame memory](https://docs.openclaw.ai/concepts/memory) en
[skills](https://docs.openclaw.ai/skills). Het zou onjuist zijn OpenClaw als
alleen vluchtige chat of promptstate neer te zetten.

Engine's positionering rust daarom niet op persistence alleen. De focus is typed
operational state die na contextverlies reconstrueerbaar is, proposals zonder
authority, deterministic mandates/authorization en onafhankelijk geobserveerde
effecten. OpenClaw kan juist een intent- of interactielaag vóór Engine zijn.

## Hermes

Hermes beschrijft zichzelf in de officiële
[documentatie](https://hermes-agent.nousresearch.com/docs/) als een uitbreidbare
agent, met
[skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills)
en [memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/).
Ook hier is “Hermes heeft geen duurzame memory of learning” geen houdbare
onderscheidende claim.

Engine gebruikt een smaller leerbegrip: plugin-owned behavior evidence kan via
vaste gates een namespaced preference of routineversie beïnvloeden, zonder
weights te trainen of authority uit te breiden. Self-improving skills kunnen in
de toekomst proposals verbeteren, maar zouden nog steeds dezelfde policy- en
oraclegrens moeten passeren.

## Waar Engine wel en niet op concurreert

Engine's kernhypothese is de combinatie van:

- lokale, typed en reconstrueerbare operational state;
- levende `achieve`- en `maintain`-goals;
- verwisselbare deterministic/model executive en pluginspecialisten;
- proposal → request → policy → authorization → execution → observation → oracle;
- dezelfde lifecycle over meerdere semantisch verschillende werelden.

Engine claimt momenteel niet:

- het integratie-ecosysteem van Home Assistant/openHAB;
- de flow-UX van Node-RED;
- de roboticsmiddleware en realtime guarantees van ROS 2;
- de algemene agentframeworkbreedte van Agents SDK/LangGraph;
- MCP te vervangen;
- de skill-/assistantproductervaring van OpenClaw of Hermes;
- dat de tabel een prestatie-, veiligheids- of kwaliteitsbenchmark is.

