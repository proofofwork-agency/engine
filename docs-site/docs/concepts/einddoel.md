---
title: Het einddoel
sidebar_position: 7
description: De lange-termijnrichting van Engine, met expliciete bewijsgrenzen en falsifieerbare tussenstappen.
---

# Het einddoel

Het einddoel van Engine is een local-first, providerneutrale runtime die menselijke intentie omzet in veilige, getypeerde en auditable acties over heterogene software- en fysieke systemen — met een levend Heart, vervangbare brains, domeinspecifieke plugins en onafhankelijke waarneming van effecten.

Dat is een richting, geen huidige productclaim.

> **Nu:** een werkende v2 verticale softwaretranche met multi-target worldstate, goals, brains, plugincontracts, policy/authorization, immediate/task lifecycle, learning/routines en deterministic reference worlds.
>
> **Getest in fake/simulatie:** heterogene closed loops, restart, partial/unknown cases, Homey-contracten, warehouse task en begrensde learning.
>
> **Roadmap:** beslissend fysiek bewijs, bredere pluginconformance, operationele hardening en pas daarna learned mini-brains waar een baselinebeperking gemeten is.

## De gewenste eindarchitectuur

```text
menselijke intentie / API / optionele assistent
                    |
                    v
          duurzaam GoalSpec + mandate
                    |
                    v
       een Heart dat blijft observeren
          /          |           \
 general brain   specialists   deterministic tools
          \          |           /
                    v
       semantic ProposedAction (untrusted)
                    |
         validate -> policy -> authorization
                    |
                    v
     plugin controller/executor -> targetcontroller
                    |
           verse observatie + oracle
                    |
            durable receipt/effect
```

Hetzelfde generieke pad moet bruikbaar zijn voor een filesystem, softwaredienst, huis, magazijn en later een fysiek lichaam. Alleen lifecycle en evidence zijn generiek; ieder domein behoudt zijn eigen units, frames, limits, controllers en safety-envelope.

## Wat “levend” uiteindelijk betekent

Engine is niet pas levend wanneer een LLM constant praat. Een volwassen Heart:

- bezit goals en worldstate buiten modelsessies;
- blijft draaien zonder menselijke impuls per stap;
- is stil wanneer maintained state aantoonbaar stabiel is;
- wordt wakker door events of polling, maar observeert altijd opnieuw;
- kan meerdere doelen eerlijk prioriteren;
- herstelt of deferreert na provider-, proces- en targetfalen;
- onderscheidt `UNKNOWN`, conflict en stale evidence van false;
- kan brains vervangen zonder operationele amnesie;
- kan een exact auditpad van intentie tot effect reconstrueren.

Een always-on loop is daarbij niet hetzelfde als een hard-realtime loop. De targetcontroller blijft authority over timingkritische stabilisatie.

## Wat “meerdere werelden” uiteindelijk betekent

Nieuwe werelden moeten installeerbaar zijn zonder een tweede Heart te bouwen. Een plugin levert zijn worldproviders, controllers, executors, oracles, specialists en optionele experience-/routinecomponenten. De runtime ontdekt die via het v2-manifest en entrypoint.

Het einddoel is niet dat ieder target dezelfde capabilitynamen heeft. Het is dat ieder target dezelfde bewijsdiscipline doorloopt:

```text
observe -> propose -> validate -> policy -> authorize
        -> dispatch -> observe -> reconcile -> record
```

## De rol van brains op lange termijn

De stabiele topologie blijft:

- een algemeen executive-brein voor situatiebegrip en strategie;
- meerdere vervangbare specialisten voor smalle cognitieve taken;
- deterministic controllers/tools voor bekende logica;
- de Heart als lifecycle- en continuity-eigenaar;
- policy, authorization en effectwaarheid buiten ieder brain.

Een toekomstige runtime kan mogelijk meerdere general providers, ensembles of fallbacks componeren. Dat is pas verantwoord wanneer identity, budget, conflict, timeout en arbitration expliciet gecontracteerd zijn. “Meer modellen” is geen doel op zichzelf.

## De rol van leren op lange termijn

Engine moet ervaring kunnen laten renderen zonder state, authority en weights te verwarren. De verwachte ladder is:

1. duurzame observed outcomes en correcties;
2. deterministic planreuse en preference/routine-adaptatie;
3. herbruikbare specialistische skills;
4. alleen bij behoeftebewijs: versioned mini-brain-artifacts;
5. rollout, monitoring en rollback onder dezelfde plugin- en policygrenzen.

Engine hoeft geen eigen foundation model te trainen. Het einddoel is providerneutrale cognition, niet modelbezit. Zie [Hoe Engine leert](./leren.md).

## SDK, CLI en plugin-ecosysteem

De huidige `engine-sdk` en `engine-runtime` vormen de eerste publieke bouwlaag:

- `engine-plugin init` scaffolt `world`, `specialist` of `full`;
- manifestvalidatie en conformance kunnen buiten de core draaien;
- `engine` ontdekt geïnstalleerde plugins;
- de CLI inspecteert plugins/worldstate en beheert setup, run, status, learning, routines en begrensde autonomy profiles.

Het einddoel is een herbruikbaar ecosysteem waarin:

- pluginimports inert en manifests statisch inspecteerbaar blijven;
- dezelfde black-box conformance tegen iedere implementatie draait;
- packages hun eigen stores/migraties en permissions declareren;
- versioning en artifactidentiteit upgrades reconstrueerbaar maken;
- een nieuwe plugin geen branches in Heart nodig heeft.

Een marketplace, hot reload of cross-language SDK is geen bewezen huidige feature en ook geen voorwaarde voor de kernthese.

## Fases en gates

| Fase | Doel | Huidige status |
| --- | --- | --- |
| 0.1 identiteit | Heart + general brain + specialist + twee heterogene sandbox/simwerelden + oracle + restart | **Implementatie-audit PASS**; owner review blijft de bestuurlijke sluiting |
| v2 softwaretranche | Multi-target GoalSpec, public SDK, installed plugins, full action lifecycle, task recovery, learning/routines | **Bestaat nu**, reference/fake-getest |
| Bounded physical proof | Een low-energy Homey-zone, verse lux/wattmetingen, vijf opeenvolgende gesloten lussen | **Roadmap/open gate** |
| Plugin hardening | Breder conformancegebruik, stream reference, production supervision, QoS, packaging en migraties | **Roadmap** |
| Learned specialists | Mini-brain alleen waar een simpele baseline aantoonbaar tekortschiet | **Roadmap/hypothese** |
| Brede fysieke inzet | Target-voor-target safetycase, controllercontract en onafhankelijk bewijs | **Lange termijn**, nooit afleiden uit simulatie |

## De eerstvolgende beslissende proef

Meer coredesign is niet de eerstvolgende waarheidstest. De repository noemt een begrensde Homey-lightingzone als flagship gate:

- alleen expliciet geconfigureerde low-risk lights;
- actuele lux- en wattobservaties;
- ACK zonder gemeten effect telt niet;
- events wekken alleen, polling/observe bevestigt;
- drift wordt hersteld en stabiele toestand veroorzaakt nul braincalls;
- vijf opeenvolgende runs volgens een vooraf vastgelegd protocol;
- onafhankelijke rollback en transport-killswitch.

Tot die proef slaagt, blijft “fysiek closed-loop bewezen” een non-claim.

## Waarmee het project zichzelf kan falsificeren

Engine mist zijn eigen einddoel wanneer:

- goals of waarheid toch alleen in een modelsessie leven;
- een nieuw domein een tweede Heart vereist;
- een ACK of modeltekst als effectbewijs geldt;
- stable monitoring continu modelcalls nodig heeft;
- een plugin zelf permission kan maken;
- learning authority of device scope stil uitbreidt;
- een deliberatieve modelcall in een hard-realtime feedbackloop terechtkomt;
- gates worden verplaatst nadat een experiment faalt.

Negatieve experimenten zijn daarom waardevol. Een simpele rule, script of bestaande controller die onder gelijk budget beter presteert kan betekenen dat een brain, mini-brain of zelfs Engine voor dat probleem niet nodig is.

## Wat het einddoel nadrukkelijk niet is

- een universele AGI-butler;
- een chatgateway met zoveel mogelijk tools;
- een marketplace die ongetypeerde skills automatisch execution rights geeft;
- een vervanging voor Homey, Home Assistant, ROS, PLCs, flight stacks of safetyhardware;
- een belofte dat ieder apparaat geleerd kan worden zonder engineering;
- een eigen foundation model als noodzakelijke moat;
- algemene fysieke certificering uit interne tests.

## Wanneer is Engine “klaar”?

Niet wanneer alle denkbare plugins bestaan. Een overtuigende Engine-versie is klaar voor een afgebakende release wanneer:

- de claim en null vooraf helder zijn;
- state, identity, authority en lifecycle reconstrueerbaar zijn;
- de relevante fake-, fault-, restart- en conformancegates slagen;
- een target-specifieke oracle het effect onafhankelijk meet;
- onzekere en negatieve uitkomsten bewaard blijven;
- rollback, limitations en safetygrens zijn gedocumenteerd;
- core correctness geen specifieke LLM-provider nodig heeft.

Begin bij [Wat is Engine?](./wat-is-engine.md), verdiep de scheiding in [Heart en brains](./heart-en-brains.md) en gebruik [Architectuur](./architectuur.md) als contractuele kaart.
