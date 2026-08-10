---
title: Meerdere plugins en brains
description: Hoe één Heart meerdere werelden, één executive en meerdere specialisten composeert.
sidebar_position: 5
---

# Meerdere plugins en brains

Engine kan meerdere geïnstalleerde plugins tegelijk laden. Iedere plugin kan
meerdere targets en specialisten leveren. In de huidige runtime is er per
`EngineApplication` precies één executive brain actief en kunnen er meerdere
plugin-specialisten beschikbaar zijn.

Dat onderscheid is belangrijk: “meerdere brains” betekent nu één executive plus
N vervangbare specialisten, niet meerdere executive modellen die stemmen,
onderhandelen of tegelijk authority bezitten.

## Eén samengestelde wereld

De registry sorteert plugins en targets op stabiele ID. Bij iedere
observatiegrens combineert Heart de laatste targetobservaties tot één duurzame
`WorldSnapshotV2` met:

- een Engine-brede revision;
- een onafhankelijke revision per target;
- alle entities, relations en observations;
- dekking, staleness en providerfouten per target.

Doelscope beperkt welke entities een effect mag raken en welke context naar een
brain wordt geprojecteerd. De volledige connected-world snapshot blijft lokaal
en duurzaam zodat restart en audit niet afhangen van modelcontext.

Plugins mogen geen target-ID delen. Als twee plugins hetzelfde target claimen,
faalt registratie. Een entity-ID hoort eveneens stabiel en canoniek te zijn;
free-form namen of embeddings zijn geen persistence key.

## De huidige executivekeuze

Zonder modelconfiguratie composeert `engine-runtime`:

```text
DeterministicExecutiveBrainV2
```

Met een geconfigureerd structured-outputmodel composeert het:

```text
OpenAICompatibleV2Model -> ModelExecutiveBrainV2
```

Beide implementeren hetzelfde `ExecutiveBrainV2`-protocol en leveren een
`BrainDecisionV2`. De besliswoorden zijn:

- `query_world`
- `consult_specialist`
- `propose_effect`
- `wait`
- `complete`
- `abandon`

Modeloutput is onbetrouwbare data. Heart bindt proposals opnieuw aan de actuele
goal en snapshot en valideert family, target, entity en schema vóór een request
kan ontstaan.

## Meerdere specialisten

Elke plugin mag nul of meer `SpecialistBrainV2`-objecten teruggeven. De runtime
projecteert alleen specialist-ID en ondersteunde capabilityfamilies naar de
executive. Kiest de executive `consult_specialist`, dan zoekt Heart exact die ID
en roept `advise(goal, snapshot, query)` aan.

De specialist kan:

- aangeven dat de vraag wel of niet binnen zijn scope valt;
- een typed `ProposedActionV1` teruggeven;
- een samenvatting en metadata leveren.

Hij kan niet:

- een `ActionRequestV1` autoriseren;
- policy overslaan;
- direct een executor aanroepen;
- een ACK of voorspelling als waargenomen effect labelen.

Per Heartpass wordt in de huidige implementatie hoogstens één geselecteerde
specialist geraadpleegd. Er is geen ingebouwde specialistendebat- of ensemblelus.

## Hoe de keuze samenhangt met de Heart

```text
WorldSnapshot + GoalSpec + effectresultaten
  -> begrensde contextprojectie
  -> één executive decision
      -> eventueel één specialistadvies
  -> ProposedAction
  -> controller
  -> policy + authorization
  -> executor
  -> verse observatie + oracle
```

De brain kiest strategie of semantisch effect. De controller vertaalt dat naar
exacte domeinparameters. Policy bepaalt authority. De executor handelt. De
oracle bepaalt op basis van nieuwe observaties of het effect werkelijk is
bereikt. Geen van deze rollen mag zijn buurrol stilzwijgend overnemen.

## Stabiele doelen zijn cognitief stil

Als alle gewenste effecten al aantoonbaar waar zijn, zet een `achieve`-goal zich
op `completed` en een `maintain`-goal op `monitoring` zonder braincall. Een
succesvol typed plan kan uit de plan-cache worden hergebruikt, maar alleen als
goalversie, entityselectie, capabilitymanifest en mandate nog matchen.

Novelty, conflict, onbekend bewijs of een geobserveerde schending kunnen de
executive opnieuw nodig maken. Een LLM zit daardoor niet in een realtime
feedbacklus.

## Plugins combineren zonder domeinlek

Een goal kan feiten uit verschillende plugins gebruiken: bijvoorbeeld lokale
tijd uit een contextplugin en lichtstatus uit een huisplugin. Scoped routineguards
geven iedere leaf een eigen exacte entityselector. De Heart evalueert de
generieke boolean- en tijdscontracten; de plugin blijft eigenaar van properties,
units, capabilityfamilies en devicevertaling.

Een plugin kan ook alleen context leveren of alleen een specialist bevatten.
Muterende capabilityfamilies vereisen altijd de volledige
provider/controller/executor/oracle-set in de manifestdeclaratie.

## Huidige grenzen

- Er is geen multi-executive orchestrator, stemming, fallbackketen of dynamische
  executive-routing. Een andere executive kiezen betekent nu een andere
  `EngineApplication`-compositie.
- Er is geen marketplace die specialist- of pluginversies oplost.
- Pluginprocessen worden niet algemeen gesandboxt en artefactsigning wordt niet
  afgedwongen.
- `stream` is een contractmodus, maar mist een end-to-end referenceproof voor
  reconnect/cursorherstel.
- Meer brains geven nooit meer authority; alle proposals doorlopen dezelfde
  policy- en effectroute.

Als multi-executive gedrag correctness of safety beïnvloedt, vraagt dat een ADR,
tests voor deterministische selectie/failure-isolation en een expliciet antwoord
op wie één uiteindelijk proposal produceert. Een modelensemble mag geen
alternatieve authorization boundary worden.

