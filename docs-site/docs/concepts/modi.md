---
title: Alle modi en statussen
sidebar_position: 5
description: De actuele Engine v2-taxonomieen voor goals, cognition, invocation, policy, evidence, learning, routines en Homey.
---

# Alle modi en statussen

“Modus” wordt in gesprekken vaak gebruikt voor verschillende dingen. Engine houdt ze apart: goalgedrag, cognitive decisions, invocationduur, executionstatus, control layer, risico, privacy, policy, evidence, learning, routines en een plugin-killswitch zijn verschillende assen.

> **Status:** de enums en statuswaarden hieronder komen uit de huidige v2-SDK/runtime, tenzij expliciet als legacy of roadmap gemarkeerd.

## 1. Goalmodus: `GoalModeV2`

| Waarde | Betekenis | Eindgedrag |
| --- | --- | --- |
| `achieve` | Bereik het gewenste effect eenmaal | Geobserveerd waar -> `completed` |
| `maintain` | Houd het gewenste effect waar over tijd | Geobserveerd waar -> `monitoring`; drift -> weer actief |

Beide **bestaan nu**. `maintain` is geen realtime mode: detectielatency hangt af van events, polling en providerfreshness.

## 2. Persistente goalstatus

Dit is in de huidige implementatie een verzameling opgeslagen strings, geen aparte publieke SDK-enum.

| Status | Betekenis |
| --- | --- |
| `active` | Het goal heeft nog een volgende pass nodig |
| `completed` | Een `ACHIEVE`-goal is onafhankelijk waar bevonden |
| `monitoring` | Een `MAINTAIN`-goal is waar en blijft gevolgd worden |
| `waiting` | Wacht op verandering, approval, taskpoll of een andere hervatconditie |
| `uncertain` | Benodigd evidence of de oracle is `UNKNOWN`; niet behandelen als false of success |
| `degraded` | Een geïsoleerde goal-/provider-/brainroute faalde of budget/circuit is uitgeput |
| `abandoned` | Stopconditie of expliciete abandon heeft het goal beëindigd |

Een brainbeslissing `COMPLETE` zet niet rechtstreeks `completed`; de Heart doet dat alleen na condition-/oracle-evaluatie.

## 3. Cognitive decision: `DecisionKindV2`

| Waarde | Bedoeling | Authority/effect |
| --- | --- | --- |
| `query_world` | Meer of andere observatie nodig | Geen mutatie; huidige Heart wacht/herobserveert |
| `consult_specialist` | Roep een benoemde specialist aan | Specialistadvies blijft een voorstel |
| `propose_effect` | Lever een semantisch `ProposedActionV1` | Nog geen execution rights |
| `wait` | Doe nu niets en wacht op relevante verandering | Duurzaam `waiting` |
| `complete` | Brain denkt dat het klaar is | Alleen adviserend; oracle/conditions beslissen |
| `abandon` | Adviseer het goal te verlaten | Heart kan status `abandoned` boeken |

De v1-termen `CONSULT_BRAIN` en `USE_TOOL` zijn legacy. V2 heeft bewust geen fysieke `USE_TOOL`-fast-path: proposals gaan altijd door controller, policy, authorization, executor en oracle.

## 4. Invocationmodus: `InvocationModeV2`

| Waarde | Semantiek | Implementatiestatus |
| --- | --- | --- |
| `immediate` | Dispatch levert direct een terminal receipt of een direct te reconciliëren resultaat | **Bestaat nu**; fake-getest, Homey gebruikt dit |
| `task` | Dispatch levert een extern handle; Heart pollt, cancelt bij deadline en reconstrueert na restart | **Bestaat nu en fake-getest** in reference warehouse |
| `stream` | Langdurige stroom met cursor/reconnectsemantiek | **Contract/store-scaffolding**; nog geen end-to-end reference proof |

Invocationmodus zegt iets over de duur van een capability, niet over goalduur, risico of autonomie.

## 5. Executionstatus: `ExecutionStateV2`

| Status | Terminaal? | Betekenis |
| --- | --- | --- |
| `requested` | Nee | Het request is aangemaakt/geboekt |
| `accepted` | Nee | Externe executor heeft het aangenomen; handle verplicht voor task recovery |
| `running` | Nee | Uitvoering loopt; handle verplicht |
| `succeeded` | Ja | Executor meldt uitvoering; effect moet nog onafhankelijk worden vastgesteld |
| `partial` | Ja | Slechts een deel is uitgevoerd of bereikt |
| `failed` | Ja | Executor rapporteert failure |
| `cancelled` | Ja | Task is geannuleerd |
| `unknown` | Ja | De lifecycle kan uitvoering/ACK niet betrouwbaar vaststellen |

`succeeded` betekent dus “execution receipt succeeded”, niet automatisch “goal effect achieved”. Dat laatste staat in `EffectDeltaV1` en de verse goal-evaluatie.

## 6. Control layer: `ControlLayer`

| Waarde | Gebruik |
| --- | --- |
| `query` | Observeren/opvragen; een `opaque` capability moet query-only zijn |
| `semantic` | Hoog-niveau domeineffect dat een controller naar targetparameters vertaalt |
| `actuator` | Capability ligt dichter bij een actuator, maar blijft buiten hard-realtime control |

Een control layer verleent geen toestemming en bepaalt niet zelfstandig de risk class.

## 7. Risk class: `RiskClass`

| Waarde | Interpretatie |
| --- | --- |
| `read_only` | Geen bedoelde wereldmutatie |
| `low` | Begrensde lage-risicoactie binnen enrolled limits |
| `medium` | Hogere impact; policy/mandate moet dit expliciet dragen |
| `high` | Huidige policy vereist approval tenzij het mandate dit expliciet toestaat |

Dit is een softwaretaxonomie, geen certificering. Een verkeerd geclassificeerde capability wordt niet fysiek veilig doordat er `low` in een manifest staat.

## 8. Privacy class: `PrivacyClass`

| Waarde | Betekenis |
| --- | --- |
| `public` | Publieke informatie |
| `local` | Lokale operationele data |
| `sensitive` | Expliciete privacypermission nodig |
| `camera` | Camera-/beelddata; expliciete permission nodig |

Een remote model krijgt niet automatisch alle observations. Contextprojectie en pluginbehoeften blijven aparte grenzen.

## 9. Policy outcome: `PolicyOutcome`

| Waarde | Gevolg |
| --- | --- |
| `ALLOW` | Policy mag een exact gebonden authorization maken |
| `DENY` | Definitieve weigering voor deze request/statebinding |
| `REQUIRE_APPROVAL` | Externe bevoegde approval nodig; een brain kan die niet leveren |
| `DEFER` | Nog niet beslisbaar/actief, bijvoorbeeld een mandate dat nog niet geldig is |

Alleen `ALLOW` bereikt dispatch.

## 10. Evidence grade: `EvidenceGrade`

| Waarde | Betekenis |
| --- | --- |
| `OBSERVED` | Direct gemeld door geïdentificeerde sensor/tool/executor binnen zijn coverage |
| `DERIVED` | Deterministisch afgeleid van benoemde observations |
| `INFERRED` | Model- of statistische conclusie |
| `UNKNOWN` | Onvoldoende evidence |
| `CONFLICTING` | Bronnen spreken elkaar tegen |
| `STALE` | Evidence is te oud voor deze beslissing |

Confidence en provenance blijven apart van de grade. Hoge confidence maakt `INFERRED` niet `OBSERVED`.

## 11. Preference-promotion: `PreferencePromotionMode`

| Waarde | Betekenis |
| --- | --- |
| `explicit_only` | Alleen een expliciete ownercorrectie mag de preference wijzigen |
| `shadow_low_risk` | Inferred evidence mag na vaste gates een candidate/shadowroute volgen |

Dit verandert preference-state, niet modelweights en niet authorityscope.

## 12. Preference-learningstatus: `LearningStatus`

| Status | Betekenis |
| --- | --- |
| `candidate` | Kandidaat is geïdentificeerd |
| `shadow` | Evaluatieperiode zonder directe authority-uitbreiding |
| `promoted` | Nieuwe versioned GoalSpec-preference is geactiveerd |
| `rejected` | Gates of outcomes voldeden niet |
| `rolled_back` | Exacte oude waarde is teruggezet in een nieuwe versie |

De huidige generic route begint in de praktijk bij `shadow` zodra de evidencegates slagen; `candidate` blijft wel een publieke contractstatus.

## 13. Routine candidate status: `RoutineCandidateStatus`

| Status | Betekenis |
| --- | --- |
| `candidate` | Patroonkandidaat |
| `shadow` | Counterfactual test; dispatchcount hoort nul te zijn |
| `ready_for_approval` | Reële shadow-opportunities en agreementgate zijn gehaald; ownerapproval nodig |
| `promoted` | Routine, goal en mandate zijn atomair geactiveerd |
| `rejected` | Patroon/conflict/shadow faalde |
| `rolled_back` | Promotie is exact teruggedraaid |

## 14. Actieve routinestatus: `RoutineStatus`

| Status | Betekenis |
| --- | --- |
| `shadow` | Routine bestaat inert tijdens evaluation |
| `ready_for_approval` | Klaar voor expliciete activatie |
| `active` | Guard en authority laten evaluation/goaluitvoering toe |
| `dormant` | Guard false, cooldown, recurrence al verwerkt of override actief |
| `guard_uncertain` | Guard bevat `UNKNOWN`, `STALE` of `CONFLICTING`; fail-closed |
| `conflicted` | Een tegengestelde routine blokkeert of wint op priority |
| `suspended` | Authority, rate, manifest of andere harde gate faalt |
| `rejected` | Routine afgewezen |
| `rolled_back` | Routine, linked goal en mandate teruggedraaid |

## 15. Normale approval versus `yolo`

`yolo` is geen algemene SDK-enum en geen “alles mag”-schakelaar. Het is de CLI-naam voor een **persistente, owner-enrolled `AutonomyProfileV1`**. In de eerste implementatie is die bewust beperkt tot:

- plugin `engine.homey`;
- een exact target en exacte zone-IDs, zonder wildcards;
- drie statisch gedeclareerde lighting-routinetemplates;
- twee lighting capabilityfamilies;
- risk ceiling `low`, local privacy en vaste brightness/power/rate limits.

Zonder zo'n profiel eindigt een bewezen routine bij `ready_for_approval`. Met profiel mag alleen een routine die de echte shadowgates al haalde automatisch promoveren binnen exact die envelope. `engine yolo disable` trekt het profiel, linked routines en afgeleide mandates duurzaam in.

**Getest in fake/simulatie:** scope freeze, promotion, disable en kill switches. **Niet fysiek bewezen:** live Homey-actuatie.

## 16. Homey transportmodus

De Homey-plugin heeft daarnaast een operationele configwaarde:

| Modus | Gedrag |
| --- | --- |
| `observe` | Read-only; aanbevolen startpunt |
| `act` | Mutatiepad kan open, maar alleen samen met `ENGINE_HOMEY_ARMED=1`, allowlists, verse state, mandate, policy en request-bound authorization |

`act` is dus slechts een transport-killswitch. Het omzeilt geen Engine-policy. `observe`/`act` mag niet worden verward met `ACHIEVE`/`MAINTAIN` of `IMMEDIATE`/`TASK`/`STREAM`.

## 17. CLI preview versus activate

`engine setup` is standaard preview-only. `--activate` schrijft goal en mandate. Dit is een mutatiekeuze in de CLI, geen persistente runtime mode.

## Legacy v1

V1 bevat overeenkomstige goal-, invocation- en receiptwaarden, plus `Affordance` (`query`, `action`, `event`). Nieuwe productfeatures gaan via v2. In de v2 registry worden v1-plugins observe-only geprojecteerd; v1-action affordance geeft dus geen v2-mutatierecht.

Zie [Architectuur](./architectuur.md) voor de volgorde waarin deze assen samenkomen en [Hoe Engine leert](./leren.md) voor de learninggates achter de statussen.
