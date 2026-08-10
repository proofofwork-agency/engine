---
title: Wat Engine niet is
sidebar_position: 2
description: De non-goals, productgrenzen en een voorzichtige vergelijking met andere projectcategorieën.
---

# Wat Engine niet is

Engine is bewust smaller dan de zin “een autonoom systeem dat alles kan”. De waarde zit juist in de grenzen: een duurzame Heart-loop, vervangbare brains, getypeerde plugins en onafhankelijke waarneming van effecten.

> **Status van deze pagina:** de architectuurgrenzen hieronder zijn **bestaande contracts of geaccepteerde ontwerpbesluiten**. Vergelijkingen zijn positionering, geen actuele benchmark en geen superioriteitsclaim.

## Geen chatassistent of messaging gateway

Engine heeft geen WhatsApp-, Telegram- of inboxervaring als kernobject. Een chatinterface kan later intenties aanleveren, maar bezit dan niet het goal, de world state of execution authority.

Het verschil is subtiel maar belangrijk:

- een assistent optimaliseert meestal de volgende interactie met een gebruiker;
- Engine beheert een gewenste toestand van een wereld, ook wanneer er geen gesprek actief is.

## Geen “LLM plus tools”-harnas

Een toolcall in een transcript is nog geen Engine-actie. In v2 wordt een modeloutput eerst een `ProposedActionV1`, daarna eventueel een exact `ActionRequestV1`, een `PolicyDecisionV1`, een `AuthorizationV1`, een `ExecutionReceiptV2` en pas na verse observatie een `EffectDeltaV1`.

Het model:

- bezit geen autoritatieve state;
- mag zijn eigen voorstel niet autoriseren;
- mag een ACK niet hernoemen tot bereikt effect;
- mag een vrije device-API niet buiten het capabilitycontract aanroepen.

## Geen gewone workflow-engine

Engine kan meerstapswerk en duurzame tasks uitvoeren, maar een vast procesdiagram is niet zijn identiteit. Het Heart kan een wereld opnieuw observeren, `UNKNOWN` bewaren, een specialist raadplegen, wachten op relevante verandering en een onderhouden doel opnieuw activeren.

Voor een volledig bekende administratieve workflow kan een script of workflow-engine eenvoudiger en beter zijn. Engine wordt relevant wanneer wereldstate, blijvende doelen, heterogene targets en onafhankelijke effectreconciliatie centraal staan.

## Geen universele device-abstractie

Engine standaardiseert de lifecycle, niet de natuurkunde of semantiek van ieder target. Een bestand, magazijnbak, lamp, robotarm en drone delen geen kunstmatig universeel commando.

Een plugin houdt daarom domeinspecifiek:

- entities, relaties, observaties en units;
- capabilityfamilies en parameters;
- precondities, limieten en recovery;
- controllervertaling en effectoracle;
- specialistische strategie.

Wat generiek blijft, staat in [Architectuur](./architectuur.md).

## Geen hard-realtime controller

De Heart-loop is always-on maar deliberatief. Modelcalls, netwerkverkeer, SQLite, policy-evaluatie en pluginpolling bieden geen harde deadlinegarantie. Motorstabilisatie, force limiting, vluchtregeling en vergelijkbare loops horen in een gevalideerde lokale controller.

Engine kan later een hoog-niveau setpoint of skillinvocation aanvragen. De targetcontroller behoudt realtime authority. Een vertraagde Heart-cyclus mag nooit de enige reden zijn dat een fysiek systeem binnen veilige limieten blijft.

## Geen vervanging voor safetyhardware

Softwarepolicy is geen emergency stop, interlock, watchdog of gecertificeerd safetycomponent. Waar onafhankelijkheid nodig is, moet de safety plane kunnen weigeren of stoppen zonder hetzelfde proces, netwerk of model als de commandopath.

De huidige fake- en simulatietests zijn dus lifecyclebewijs. Ze zijn geen certificering en ondersteunen geen algemene fysieke veiligheidsclaim.

## Geen world model dat voorspellingen tot waarheid maakt

Engine kan later Umwelt of een andere `WorldModelPort` gebruiken voor voorspelde effecten, dynamics of planning. Dat advies blijft `INFERRED` tot een Engine-observatie of deterministic oracle iets anders onderbouwt.

De eigendomsgrens is:

- Engine: capabilities, policy, authorization, execution, target safety en operations;
- Umwelt of een andere modelprovider: adviserende reconstructie, voorspelling en planning;
- targetproviders, executors en oracles: operationele waarneming binnen hun gedocumenteerde dekking.

## Geen zelflerende AGI

Engine traint nu geen algemeen model en maakt niet automatisch nieuwe weights. Wat nu “leren” heet is begrensde, inspecteerbare state-aanpassing: evidence verzamelen, een preference of routine als kandidaat behandelen, shadowen, een nieuwe `GoalSpec`-versie maken en exact kunnen terugrollen.

Een toekomstig mini-brain is een specialistische skill met expliciet bereik, modelartifact, trainingprovenance, evaluatie en fallback. Het krijgt nooit meer authority omdat het geleerd is. Zie [Hoe Engine leert — en niet leert](./leren.md).

## Vergelijking met andere projecten en categorieën

Onderstaande tabel vergelijkt het primaire object van ieder systeem. Hij zegt niet dat Engine breder, beter of productierijper is.

| Project/categorie | Primair object | Overlap met Engine | Belangrijk verschil |
| --- | --- | --- | --- |
| **OpenClaw** | Self-hosted personal-agent/gateway rond kanalen, sessies en tools | Always-on runtime, lokale inzet, vervangbare modellen, tools | Engine centreert duurzame world state, maintained goals en effectoracles; geen chatgateway als kern |
| **Hermes Agent** | Personal agent met ervaring-naar-skill-loop | Persistentie, tools, specialisatie en compounding experience | Hermes centreert herbruikbare agentskills; Engine centreert een getypeerde multi-world lifecycle en begrensde GoalSpec/routine-adaptatie |
| **LangGraph/Temporal-achtige orchestratie** | Expliciete workflows, state machines en duurzame jobs | Retries, durable state en meerstapsuitvoering | Engine voegt world snapshots, brains als proposal providers, capabilitypolicy en post-effectoracles toe; voor vaste workflows kan orchestratie eenvoudiger zijn |
| **Home Assistant/Homey automation** | Product- of domeinspecifieke apparaatbediening en automations | Events, state, apparaten en routines | Engine gebruikt zo'n platform als target/world via een plugin; het vervangt het platform of zijn lokale controllers niet |
| **ROS/PLC/flight-stackcategorie** | Devicecommunicatie en/of realtime fysieke controle | Adapters, capabilities en acties naar fysieke targets | Engine is de deliberatieve intentie- en policylaag erboven, niet de realtime control- of safetylaag |
| **Umwelt** | World-model- en onderzoeksprimitieven | State reconstruction, voorspelde effecten, uncertainty en planning | Umweltoutput is adviserend; Engine bezit concrete actie, policy, authorization en execution |

De eerlijke huidige positie is: OpenClaw en Hermes hebben een andere productfocus en volwassen gebruikerssurface; Engine heeft een smallere, experimentele kernel met sterkere expliciete world/action-contracten. De repository bevat nog geen uitgevoerde, vastgezette head-to-head benchmark.

## Wat de huidige implementatie niet bewijst

### **Getest in fake/simulatie, niet fysiek bewezen**

- Homey closed-loop, sensororacles, event/poll recovery, routines en YOLO-scope;
- warehouse task polling, cancellation en restart;
- learningroutes over verschillende plugindomeinen;
- multi-world lifecycle en restartreconstructie.

### **Bestaat als contract/scaffolding, nog geen volledige reference proof**

- `STREAM` invocation en reconnect/cursorsemantiek.

### **Roadmap**

- vijf opeenvolgende begrensde live Homey lux/watt-runs;
- bredere externe pluginconformance en operationele hardening;
- productie-supervision, distributie en event-QoS;
- mini-brain-training na een gemeten behoeftebewijs;
- fysieke uitbreiding per target en per risico-envelop.

## Wanneer moet je iets anders gebruiken?

- Kies een chatagent wanneer kanalen, gesprekken en snelle softwaretools het product zijn.
- Kies een workflow-engine wanneer het proces vast en de state machine vooraf bekend is.
- Kies een Homey/Home Assistant automation wanneer een lokale regel het probleem volledig oplost.
- Kies een PLC, realtime controller of gecertificeerde safetyoplossing voor timingkritische of gevaarlijke controle.
- Kies Engine wanneer het experiment juist draait om duurzame doelen, heterogene werelden, brains als onbetrouwbare proposal providers en onafhankelijk vastgestelde effecten.
