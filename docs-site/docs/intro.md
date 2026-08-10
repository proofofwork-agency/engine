---
title: Engine in één overzicht
sidebar_position: 1
slug: /intro
description: Start hier voor het mentale model, de huidige bewijsgrens en de juiste leesroute.
---

# Engine in één overzicht

Engine is een experimentele, local-first runtime voor blijvende doelen over software- en fysieke werelden. Het systeem combineert een duurzaam **Heart**, één verwisselbaar **algemeen brein**, nul of meer **specialistische brains** en installeerbare **world plugins**.

Het ontwerp begint niet bij een chatsessie, maar bij een wereld die ook zonder modelcontext blijft bestaan:

```text
duurzame wereldstate + duurzaam doel
               |
               v
        observeren en beoordelen
               |
               v
      brain/specialist stelt voor
               |
               v
 schema → policy → authorization
               |
               v
    uitvoeren → opnieuw observeren
               |
               v
     oracle → receipt → ervaring
```

Een brain mag kiezen en voorstellen. Het Heart houdt de cyclus, state en causaliteit bij. Policy verleent of weigert authority. Een target-specifieke executor handelt. Alleen een verse observatie en effect-oracle mogen vaststellen wat werkelijk is gebeurd.

## De essentie in vier regels

1. **Heart betekent continuïteit.** Goals, snapshots, receipts en ervaring staan duurzaam buiten de modelsessie.
2. **Brain betekent cognition, niet authority.** Een deterministische of model-backed executive kiest de volgende cognitieve stap; specialisten leveren begrensd advies.
3. **Plugins betekenen werelden met eigen semantiek.** Providers observeren; controllers vertalen; executors handelen; oracles meten effecten.
4. **Succes betekent onafhankelijk bewijs.** Een modeltekst of API-ACK is nooit voldoende.

## Wat je nu kunt verwachten

| Status | Betekenis in deze documentatie |
| --- | --- |
| **Bestaat nu** | In de huidige v2-code en publieke contracts geïmplementeerd |
| **Getest in fake/simulatie** | Automatisch bewezen, maar geen bewijs van fysieke veiligheid |
| **Live read-only** | Tegen een echt target geobserveerd zonder mutatie |
| **Roadmap** | Richting of hypothese, niet als bestaande feature gebruiken |

De huidige repository bevat:

- `engine-heart` met Heart, durable world store, policy, learning en routines;
- `engine-sdk` met `engine.plugin/v2`, scaffolding en conformance;
- `engine-runtime` met composition root, discovery, lease en de `engine`-CLI;
- een warehouse-referenceplugin, contextplugin en Homey-plugin;
- tests voor reconstructie, stale/denied/malformed cases, immediate/task-lifecycles en begrensde learning.

De huidige bewijsgrens is bewust smaller dan de visie: Homey is live read-only geobserveerd, maar de v2-mutaties zijn alleen met een fake getest; `STREAM`, meerdere algemene brains, getrainde mini-brains en fysieke safety-certificering zijn niet bewezen.

## Kies je leesroute

### Ik wil begrijpen wat Engine is

1. [Wat is Engine?](concepts/wat-is-engine.md)
2. [Wat Engine niet is](concepts/wat-engine-niet-is.md)
3. [Heart en brains](concepts/heart-en-brains.md)
4. [Architectuur](concepts/architectuur.md)

### Ik wil alle mogelijkheden en grenzen kennen

1. [Alle modi en statussen](concepts/modi.md)
2. [Hoe Engine leert — en niet leert](concepts/leren.md)
3. [Het einddoel](concepts/einddoel.md)
4. [Status en bewijs](reference/status-en-bewijs.md)

### Ik wil bouwen

1. [Quickstart](developers/quickstart.md)
2. [Plugininterface v2](developers/plugin-interface.md)
3. [SDK-referentie](developers/sdk.md)
4. [CLI-referentie](developers/cli.md)
5. [Meerdere plugins en brains](developers/meerdere-plugins-en-brains.md)
6. [Pluginchecklist](developers/plugin-checklist.md)

### Ik wil Engine positioneren

- [Vergelijking met andere projecten](reference/vergelijking.md)
- [Begrippenlijst](reference/begrippenlijst.md)
- [Veelgestelde vragen](reference/faq.md)

## De vaste checksum

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

Die regels zijn geen slogans achteraf. Ze bepalen welke code, tests en claims bij Engine horen.
