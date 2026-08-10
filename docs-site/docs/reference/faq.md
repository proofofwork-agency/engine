---
title: Veelgestelde vragen
description: Korte antwoorden over Heart, brains, plugins, learning, veiligheid en huidige grenzen.
sidebar_position: 4
---

# Veelgestelde vragen

## Is Engine een AI-agent?

Niet primair. Engine is een lokale runtime voor levende doelen, typed world
state en een auditable action lifecycle. Een LLM of agent kan een executive brain
of intentcompiler leveren, maar blijft proposal provider. Policy,
authorization, execution en effectwaarheid liggen buiten het model.

## Wat is het verschil tussen Heart en brain?

De Heart bezit de duurzame loop en operational state. Hij observeert, evalueert,
valideert, vraagt policy, legt authorization/receipts vast en observeert opnieuw.
Een brain kiest bij novelty of drift een typed vervolgstap of semantisch
proposal. Een brain kan worden vervangen of wegvallen zonder dat de world state
verdwijnt.

## Werkt Engine zonder LLM?

Ja voor de kernruntime, observatie, deterministic executive, typed goals,
plugins, policy, execution, oracle en tests. De huidige `engine setup`-route voor
vrije natuurlijke taal vereist wel een geconfigureerd structured-outputmodel.
Een applicatie kan daarnaast zelf een typed GoalSpec aanmaken.

## Kan ik meerdere modellen tegelijk gebruiken?

Je kunt meerdere pluginspecialisten hebben. Per huidige `EngineApplication` is
er precies één executive actief: deterministic of één OpenAI-compatible
modeladapter. Multi-executive voting, fallback of ensemble-routing is nog niet
geïmplementeerd.

Meer brains zouden geen extra authority krijgen: ieder proposal moet dezelfde
validation, policy, authorization en oracle doorlopen.

## Kan één goal meerdere plugins gebruiken?

Ja. De Heart composeert alle aangesloten targetobservaties in één snapshot en
een GoalSpec kan entities/conditions over meerdere targets gebruiken. Scoped
routineguards kunnen bijvoorbeeld een tijdentity uit een contextplugin combineren
met een devicezone uit een andere plugin. Muterende desired effects blijven aan
een exacte capabilityfamily, target en entity gebonden.

## Is iedere Python-plugin automatisch vertrouwd?

Nee. Engine vergelijkt statisch en geladen manifest en houdt onbekende families
observe-only, maar de huidige runtime heeft geen algemene processandbox en
dwingt manifest-needs niet op OS-/netwerkniveau af. Ook pluginartefactsigning is
nog niet afgedwongen. Installeer alleen code die je op deploymentniveau vertrouwt.

## Is er een pluginmarketplace?

Nee. Discovery gebruikt lokaal geïnstalleerde Python-distributies met de
`engine.plugins`-entrypointgroep. Er is nog geen marketplace, automatische trust
chain of version-resolverdienst.

## Kan een plugin zichzelf nieuwe capabilities geven?

Niet voor mutatie. Dynamische discovery mag nieuwe instanties tonen, maar een
niet vooraf in `engine-plugin.toml` gedeclareerde family wordt opaque,
query-only en read-only. Een statisch manifest plus enrollment/mandate is nodig
voordat authority kan bestaan.

## Welke modi bestaan er?

Op goalniveau zijn er `achieve` en `maintain`. Op capabilityniveau bestaan
`immediate`, `task` en `stream`. Cognitieve beslissingen gebruiken
`query_world`, `consult_specialist`, `propose_effect`, `wait`, `complete` en
`abandon`. Daarnaast is er een begrensd `yolo`-autonomieprofiel voor de eerste
Homey-lightingtranche; dat is geen onbeperkte modus.

## Zijn `task` en `stream` productierijp?

`task` heeft een non-home referenceproof met durable handle, poll, deadline
cancel en reconstruction na restart. `stream` bestaat in contract en store-
scaffolding, maar mist een end-to-end referenceproof voor reconnect en cursor-
herstel. Beoordeel daarnaast ieder concreet target afzonderlijk.

## Wat betekent “Engine leert”?

De huidige learningroute importeert plugin-owned behavior evidence, valideert
scope en schema, maakt een candidate, draait minimaal een begrensde shadowfase
en kan daarna een nieuwe GoalSpec-preference of routineversie opslaan. Promotie
is auditable en rollbackbaar en mag nooit target, capability, risk, privacy of
authority uitbreiden.

Dit is geen online training van modelweights. Engine kan dus voorkeur/state
aanpassen zonder een model te retrainen.

## Kan Engine zelf skills schrijven of verbeteren?

Niet als huidige productkern. Een plugin of extern systeem kan nieuwe code of
een skill voorstellen, maar installation, trust, signing, sandboxing, tests en
enrollment blijven aparte stappen. Self-modifying code krijgt niet vanzelf
authority.

## Is een execution receipt hetzelfde als succes?

Nee. Een receipt vertelt wat de executor over de uitvoering meldt. Daarna moet
een verse world observation volgen en moet de pluginoracle het gewenste effect
met relevante measurements reconciliëren. Een ACK zonder effect kan dus een
`succeeded` receipt en toch `achieved = false` of `null` opleveren.

## Waarom is ontbrekende telemetry niet gewoon `false`?

Omdat afwezigheid alleen een negatief feit bewijst als de bron complete relevante
coverage garandeert. Een offline sensor, incomplete query of stale snapshot zegt
niet dat een deur dicht, een lamp uit of een relatie afwezig is. Engine bewaart
dan `UNKNOWN` of `STALE` en faalt gesloten voor mutatie.

## Vervangt policy een noodstop of hardware-interlock?

Nee. Softwarepolicy beperkt requests maar vervangt geen e-stop, watchdog,
force/temperature limiter, gecertificeerde PLC of realtime controller. Een
model kan die onafhankelijke safety plane evenmin overrulen.

## Kan Engine motoren, drones of auto's rechtstreeks besturen?

Niet in een hard-realtime loop. Realtime stabilisatie en actuatorfeedback horen
bij een gevalideerde lokale controller. Engine kan op een hoger semantisch niveau
een begrensde taak voorstellen en autoriseren, mits een geschikte adapter,
safety boundary en onafhankelijke observation/oracle bestaan.

## Is Engine een vervanger voor Home Assistant, ROS 2, MCP of een agentframework?

Nee. Die systemen zitten op andere of overlappende lagen en kunnen met Engine
samenwerken. Home Assistant/openHAB kunnen homewerelden leveren, ROS 2 kan een
roboticsbody/controllerlaag zijn, MCP kan context/tools transporteren en een
agentframework kan intent/deliberation leveren. Engine's eigen focus is typed
operational state plus proposal/authority/effectscheiding.

## Kan ik Engine nu via PyPI installeren?

Deze documentatie publiceert geen PyPI-installclaim. Gebruik de repository-
workspace:

```console
uv sync --all-packages --locked
```

Daarna voer je de commando's uit met `uv run`.

## Waar staat de lokale database?

Standaard in `.engine/engine.sqlite3`, relatief aan de werkmap. Stel
`ENGINE_DATABASE` in voor een ander expliciet pad. Plugin-owned stores hebben
een eigen identity en migratieversie en horen niet als gedeelde private tabellen
in deze database-interface te lekken.

## Wat gebeurt er bij twee runtimes op dezelfde store?

De operationele CLI gebruikt een exclusieve SQLite-lease met heartbeat. Een
tweede actieve owner wordt geweigerd; leaseverlies vraagt de lopende Heart te
stoppen. Dit beschermt tegen twee executives die dezelfde store gelijktijdig
muteren, maar is geen distributed consensusprotocol voor meerdere hosts.

## Wat is het einddoel van Engine?

De thesis is een local-first runtime die menselijke intentie kan omzetten in
veilige, typed en auditable acties over heterogene software- en fysieke systemen,
terwijl modellen optionele proposal providers blijven, realtime controllers hun
authority houden en een onafhankelijke policy/safety boundary uitvoering
begrenst.

De eerstvolgende waarde komt uit het bewijzen of falsificeren van die thesis met
kleine, meetbare werelden. Het einddoel is niet een demo die autonoom lijkt, een
universele butler of een claim op certificering zonder extern bewijs.

## Welke grote gaps zijn er nu?

- geen marketplace;
- geen afgedwongen plugin signing;
- geen algemene sandbox-/needs-enforcement;
- geen end-to-end streamreference;
- geen multi-executive runtime;
- geen universele fysieke safety- of certificeringsclaim.

Die gaps zijn bewust zichtbaar gehouden zodat documentatie geen roadmap als
gerealiseerde capability presenteert.

