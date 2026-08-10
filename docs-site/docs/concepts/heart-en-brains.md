---
title: Heart en brains
sidebar_position: 4
description: Wat het Heart, het algemene brein en meerdere specialistische breinen betekenen en hoe zij samenwerken.
---

# Heart en brains

De organenmetafoor is functioneel, niet biologisch. Het **Heart** draagt continuïteit en authority boundaries; brains leveren cognition. Zonder Heart worden brains losse modelcalls. Zonder een brain-slot wordt Engine alleen een deterministic control runtime. De huidige architectuur combineert beide, maar maakt iedere brain vervangbaar.

> **Huidige topologie:** **een actief algemeen executive-brein per runtimecompositie** plus **nul, een of meerdere geregistreerde specialistische breinen**. Dit bestaat nu. Meerdere concurrerende algemene breinen en hun arbitrage zijn geen first-class feature.

## Wat het Heart betekent

`WorldHeartV2` is eigenaar van de levende, duurzame cyclus. Het:

- observeert alle verbonden targets en maakt een versioned `WorldSnapshotV2`;
- beheert `ACHIEVE`- en `MAINTAIN`-goals en hun prioriteit/status;
- evalueert declaratieve effects, stopcondities en routineguards;
- beslist wanneer cognition nodig is en wanneer rustig monitoren volstaat;
- bouwt een begrensde, verse contextprojectie voor iedere braincall;
- roept het executive-brein en een gekozen specialist aan;
- valideert proposals en concrete requests;
- laat deterministic policy authorization verlenen of weigeren;
- dispatcht alleen via een pluginexecutor;
- observeert na de actie en laat een oracle het effect reconciliëren;
- bewaart causal IDs, receipts, effecten, braincalls, wakes en learning evidence;
- hervat durable tasks en reconstructeert state na procesrestart;
- isoleert een falend goal als `degraded` in plaats van de hele wereldloop stil te leggen.

De Heart neemt daarmee beslissingen over **lifecycle en authority**, niet over de specifieke betekenis van een magazijntransfer of lampbrightness.

## Wat het Heart niet is

Het Heart is niet:

- een LLM of een verborgen chain-of-thought;
- een domeinspecialist;
- een hard-realtime scheduler;
- een executor die willekeurige APIs mag aanroepen;
- een effectoracle;
- een emergency stop of safetycontroller.

De Heart mag een pluginresultaat valideren en stoppen, maar kan niet bewijzen dat fysieke safetyhardware correct werkt.

## Het algemene brein

Het algemene brein ontvangt een begrensde projectie met het goal, relevante worldstate, effectresultaten, zichtbare capabilities en specialisten. Het kiest een volgende cognitieve stap:

- meer wereldinformatie nodig hebben;
- een specialist raadplegen;
- een semantisch effect voorstellen;
- wachten;
- completion of abandon adviseren.

De Heart accepteert completion nooit op het woord van het brein. Alleen geobserveerde goalcondities kunnen `completed` of `monitoring` opleveren.

### Twee huidige implementaties

| Executive | Gebruik | Status |
| --- | --- | --- |
| `DeterministicExecutiveBrainV2` | Provider-vrije baseline en bekende, stabiele routes | **Bestaat nu**, standaard zonder modelconfiguratie |
| `ModelExecutiveBrainV2` | Structured-output-provider voor novelty, conflict of ambiguïteit | **Bestaat nu** achter een providerneutraal port; lokale/API canaries bestaan |

De runtime kiest bij composition een van deze executives. Er is dus niet automatisch een “raad van LLMs”. Een toepassing kan zelf een composite executive achter hetzelfde protocol bouwen, maar Engine heeft daarvoor nog geen canonieke arbitrage-, cost- of conflictsemantiek.

## Specialistische breinen

Een specialist declareert:

- een stabiele, versioned identity;
- ondersteunde capabilityfamilies;
- een `advise(goal, snapshot, request)`-contract;
- een antwoord `SpecialistAdviceV1` met `supported`, samenvatting, metadata en optioneel een `ProposedActionV1`.

Plugins kunnen meerdere specialists registreren. De registry projecteert hun IDs en supported families naar het general brain. Als het general brain `CONSULT_SPECIALIST` kiest, roept de Heart precies die specialist aan en boekt de output met provenance.

Specialisten kunnen deterministic algoritmen, klassieke planners of modellen zijn. “Brain” betekent hier dus een cognitief beslisorgaan, niet noodzakelijk een neuraal netwerk.

## Een general brain en meerdere specialists

```text
                         +-> specialist: verlichting/energie -+
Goal + bounded context -> general executive                  +-> ProposedAction
                         +-> specialist: warehouse ----------+
                         +-> specialist: vision (later) ------+
                                      |
                                      v
                        Heart valideert en autoriseert lifecycle
```

Wat kan vandaag:

- meerdere specialists uit meerdere plugins tegelijk catalogiseren;
- selecteren op expliciete specialist-ID en supported capabilityfamilies;
- specialistoutputs snapshot-bound en duurzaam herleidbaar maken;
- een specialist een typed proposal laten leveren;
- een provider of specialist vervangen zonder goal/state naar zijn sessie te verplaatsen.

Wat kan vandaag niet als canonieke feature:

- meerdere general brains parallel laten stemmen;
- automatisch consensus, debate of model-ranking als authority gebruiken;
- een specialist zichzelf laten registreren op basis van vrije modeltekst;
- een specialist andere capabilities laten verzinnen dan het enrolled manifest;
- aantonen dat meer brains altijd betere resultaten geven.

De oude 0.1-pilot en huidige fixtures bewijzen de route general -> specialist -> capability -> observation. Ze bewijzen geen algemene multi-brain-superioriteit; dat vereist een gecontroleerde vergelijking onder gelijk budget.

## Van beslissing naar actie

De taakverdeling blijft bij iedere mutatie hetzelfde:

1. **General brain:** selecteert strategie, specialist of semantisch effect.
2. **Specialist:** levert begrensd domeinadvies of een semantisch voorstel.
3. **Heart:** valideert identities, statebinding en schemas.
4. **Domain controller:** maakt het exacte targetrequest.
5. **Policy:** beslist en mint eventueel authorization.
6. **Executor:** voert uit.
7. **World provider + effect oracle:** stellen vast wat er werkelijk is waargenomen.
8. **Heart:** boekt resultaat en bepaalt de volgende lifecycle-status.

Geen brain slaat stap 3-7 over.

## Context is niet state

Voor iedere call projecteert `BoundedContextProjector` maximaal een begrensd aantal relevante entities en observations, plus relaties, capabilitymetadata en effectevaluaties. Een projectie krijgt een hash en snapshot-ID.

Daaruit volgen drie eigenschappen:

- de modelprovider hoeft geen sessiegeschiedenis te bewaren;
- de complete world blijft lokaal en is na providerverlies reconstrueerbaar;
- een brainoutput tegen een oude snapshot kan als stale worden geweigerd.

De projectie kan worden afgekapt. Dat is expliciete incomplete coverage, geen bewijs dat iets afwezig is.

## Stable state is cognitief stil

Een `MAINTAIN`-goal dat aantoonbaar waar is, gaat naar `monitoring`. Polls en events mogen blijven binnenkomen, maar roepen niet automatisch brains aan. Alleen een verse observatie die relevante drift toont activeert cognition opnieuw.

Dit bestaat en is deterministic getest. Het is tegelijk een kostenregel en een architectuurgrens: een LLM hoort niet in de continue sensor- of actuatorloop.

## Zijn brains optioneel of essentieel?

Beide uitspraken kunnen waar zijn, mits precies geformuleerd:

- **Een specifieke LLM is optioneel.** De deterministic executive kan core correctness dragen.
- **Het brain-slot is onderdeel van Engine.** De runtime heeft een expliciete cognitive decision seam en specialistencatalogus.
- **Cognition is niet altijd actief.** Observe, policy, task recovery en stable monitoring zijn vaak deterministic.
- **Authority is nooit cognitief.** Ook een zeer sterk model blijft proposal provider.

Lees [Hoe Engine leert](./leren.md) voor het onderscheid tussen ervaring en weights, en [Alle modi](./modi.md) voor de volledige decisiontaxonomie.
