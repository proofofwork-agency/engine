---
title: Wat is Engine?
sidebar_position: 1
description: Een nuchtere uitleg van Engine, de huidige implementatie en de grens tussen visie en bewijs.
---

# Wat is Engine?

Engine is een local-first runtime die blijvende doelen verbindt aan getypeerde waarnemingen en begrensde acties in verschillende werelden. Het systeem combineert een **hart** voor continuïteit met een **algemeen brein**, **specialistische breinen** en **wereldplugins**. Een model mag een actie voorstellen; alleen Engine kan het voorstel valideren, autoriseren, uitvoeren en het effect opnieuw waarnemen.

> **Statuslabels in deze documentatie**
>
> - **Bestaat nu** — zit in de huidige v2-code en publieke contracts.
> - **Getest in fake/simulatie** — automatisch of via bewaarde experimenten bewezen, maar niet automatisch in echte hardware.
> - **Roadmap** — richting of hypothese; nog niet als productcapaciteit presenteren.

## De korte versie

Een normaal agent-harnas begint bij een modelturn: de gebruiker vraagt iets, het model kiest een tool en het transcript onthoudt wat er gebeurde. Engine begint bij een duurzame wereld en een duurzaam doel:

```text
doel vastleggen
  -> wereld observeren
  -> bepalen of het doel al waar is
  -> zo nodig een begrensde actie voorstellen
  -> schema, precondities, policy en mandaat controleren
  -> exact autoriseren en uitvoeren
  -> opnieuw observeren
  -> verwacht en werkelijk effect vergelijken
  -> doel afronden of blijven bewaken
```

De operationele waarheid leeft dus niet in een prompt. Goals, snapshots, observaties, policybeslissingen, authorizations, receipts en effecten worden duurzaam opgeslagen en kunnen na proces- of providerverlies worden gereconstrueerd.

## Waaruit Engine bestaat

| Onderdeel | Verantwoordelijkheid | Status |
| --- | --- | --- |
| **Heart** | Houdt doelen, wereldstate, aandacht, cycli, ervaring en herstel levend | **Bestaat nu** |
| **General brain** | Kiest een volgende cognitieve stap, specialist of semantisch effect | **Bestaat nu**: deterministisch of model-backed |
| **Specialist brains** | Leveren begrensd, domeinspecifiek advies en eventueel een getypeerd voorstel | **Bestaat nu**; meerdere specialisten kunnen tegelijk geregistreerd zijn |
| **World plugins** | Observeren targets en vertalen Engine-contracten naar domeinspecifieke semantiek | **Bestaat nu** via `engine.plugin/v2` |
| **Policy en authorization** | Beslissen buiten ieder brein of een exact request mag worden uitgevoerd | **Bestaat nu** als deny-by-default mandaatpolicy |
| **Executor en effect oracle** | Voeren een geautoriseerd request uit en toetsen het effect aan verse state | **Bestaat nu** |
| **Learning/routines** | Verwerken expliciete correcties en begrensde gedragssignalen zonder authority uit te breiden | **Bestaat nu**, vooral fake-/simulatiegetest |
| **Hard-realtime controller en safety hardware** | Handhaven timing, interlocks, watchdogs en fysieke limieten | Hoort bij het target; **niet** de deliberatieve Heart-loop |

Lees [Heart en brains](./heart-en-brains.md) voor de precieze taakverdeling en [Architectuur](./architectuur.md) voor de volledige v2-keten.

## Twee soorten doelen

Engine kent twee canonieke goalmodi:

- `ACHIEVE`: bereik een effect een keer en word daarna `completed`;
- `MAINTAIN`: houd een effect waar. Bij een stabiele wereld wordt het doel `monitoring`; waargenomen drift activeert de lus opnieuw.

Een `MAINTAIN`-doel laat het verschil met een eenmalige workflow goed zien. “Zet lamp A aan” is een opdracht. “Houd deze werkplek tussen 350 en 450 lux, onder een vermogensbudget” is een blijvende gewenste toestand. In stabiele toestand hoort Engine te observeren zonder het algemene of specialistische brein te blijven aanroepen.

Beide goalmodi **bestaan nu**. De quiet-monitoring-, drift- en repairroute is in deterministic fakes/simulaties getest. Een v2 Homey-observatierun bestaat, maar de beslissende fysieke lux/watt-actuatietest staat nog op de roadmap. Zie [Alle modi](./modi.md).

## Welke werelden bestaan er nu?

De huidige repository bevat verschillende bewijslagen:

| Wereld | Wat hij bewijst | Bewijsgrens |
| --- | --- | --- |
| Sandbox-filesystem en discrete grid | De oorspronkelijke 0.1-acceptatie: hetzelfde Heart-/brain-/cataloguspad, partial effect, oracle en restart | **Getest in sandbox/simulatie**; dit is de oudere v1-acceptatielaag |
| Reference warehouse plugin | Een apart installeerbare, niet-huishoudelijke v2-world met een duurzame `TASK`, polling, deadline-cancel, oracle en restart | **Getest in fake/simulatie** |
| Engine Homey/HomeOps | Whole-house worldmodel, events als wake hint, polling, getypeerde acties, sensororacles, preferences en routines | **Fake-getest**; live alleen observe-only bewezen, niet v2-actuatie |
| Engine Context | Lokale tijd, geplande wakes, bevestigde locatie en optioneel weer met expliciete privacykeuze | **Bestaat nu**; ontbrekende data blijft `UNKNOWN` |

Deze voorbeelden bewijzen dat een gedeelde lifecycle verschillende domeinen kan dragen. Ze bewijzen niet dat iedere mogelijke machine al ondersteund of veilig bedienbaar is.

## Waarom “local-first”?

Local-first betekent hier:

- de volledige operationele state en audittrail blijven in lokale stores;
- het systeem werkt met een deterministisch brein zonder externe modelprovider;
- een lokale of remote OpenAI-compatibele provider kan optioneel worden gebruikt;
- een remote model-URL zonder API-key faalt gesloten;
- een model krijgt een begrensde contextprojectie, niet automatisch de volledige wereld;
- plugins declareren netwerk-, filesystem-, secret- en privacybehoeften.

Local-first betekent niet “zonder netwerk” en ook niet “automatisch veilig”. Een plugin kan netwerktoegang nodig hebben; een mens moet die grens bewust configureren.

## Is een LLM onderdeel van Engine?

Intelligentie is onderdeel van het Engine-concept, maar één specifieke LLM-provider is dat niet. De huidige runtime kan precies één algemeen executive-brein componeren:

- een transparante deterministic executive voor bekende, stabiele routes; of
- een model-backed executive achter een providerneutraal structured-output-contract.

Specialistische breinen kunnen daarnaast door plugins worden geregistreerd. Ieder brein produceert onbetrouwbare, getypeerde input. Het kan geen permission maken, geen effect als waargenomen verklaren en geen safetyregel omzeilen. Core correctness moet blijven werken wanneer iedere LLM-provider wegvalt of wordt vervangen.

## Wat kan Engine vandaag wel en niet?

### Wel

- duurzame multi-target `GoalSpecV2`-doelen en samengestelde `WorldSnapshotV2`-state beheren;
- `ACHIEVE`- en `MAINTAIN`-doelen uitvoeren;
- één general brain en meerdere specialists samenstellen;
- pluginmanifesten, capabilityfamilies, units, limieten en schemas valideren;
- de volledige proposal-to-effect-lifecycle duurzaam boeken;
- immediate acties en durable tasks met polling/cancel/restart afhandelen;
- expliciete voorkeurcorrecties en begrensde routine-/preferencekandidaten verwerken;
- nieuwe v2-plugins via de SDK scaffolden en via entrypoints ontdekken.

### Nog niet als brede productclaim

- willekeurige apparaten zonder vooraf gedeclareerd plugincontract besturen;
- hard-realtime motor-, vlucht- of stabilisatielussen draaien;
- fysieke safetyhardware, certificering of fail-safe gedrag vervangen;
- meerdere concurrerende algemene breinen first-class arbitreren;
- aantonen dat multi-brain altijd beter is dan een monoliet;
- online modelweights trainen of uit ervaring zelf een nieuw neuraal brein maken;
- end-to-end `STREAM`-reconnect als reference proof leveren;
- fysieke Homey-actuatie als geslaagde v2-proef claimen.

Lees [Wat Engine niet is](./wat-engine-niet-is.md) voor de scherpe grenzen en [Het einddoel](./einddoel.md) voor de richting achter de huidige verticale slice.

## Belangrijkste identiteitsregels

```text
LLM proposal != authority
prediction != observation
policy != fysieke safety
deliberation != realtime control
simulation evidence != real-world certification
generic lifecycle != generic device semantics
state != weights
imagine != execute
```

Deze scheidingen zijn geen extra veiligheidslaag rond Engine; ze bepalen hoe Engine zijn eigen state, beslissingen en bewijs interpreteert.
