---
title: Status en bewijs
description: Evidence grades, lifecycle-statussen en de grens tussen uitvoering en effect.
sidebar_position: 1
---

# Status en bewijs

Engine bewaart niet alleen een eindlabel. Het legt per stap vast wat is
voorgesteld, gevalideerd, toegestaan, uitgevoerd en daarna waargenomen. Status
en bewijs zijn verschillende dimensies:

- een executor kan `succeeded` melden terwijl het gewenste effect niet wordt
  waargenomen;
- een oracle kan `achieved = null` geven omdat de meetdekking ontbreekt;
- een model kan zeer zeker klinken en toch alleen `INFERRED` data leveren.

## Evidence grades

| Grade | Betekenis | Mag als directe operationele waarheid dienen? |
| --- | --- | --- |
| `OBSERVED` | Direct uitgegeven door een geïdentificeerde sensor, tool, provider of executor binnen zijn coverage | Ja, binnen bron, tijd en coverage |
| `DERIVED` | Deterministische transformatie van geïdentificeerde observaties | Ja, als input en transformatie auditable zijn |
| `INFERRED` | Model- of statistische conclusie | Niet zonder policy/validatie; nooit herlabelen als observatie |
| `UNKNOWN` | Onvoldoende bewijs | Nee; ontbrekend is niet `false` |
| `CONFLICTING` | Bronnen spreken elkaar tegen | Nee; eerst reconciliëren of defer |
| `STALE` | Bewijs is te oud voor de beslissing | Nee voor de betreffende operationele beslissing |

`quality` of `confidence` is geen vervanging voor evidence grade. Een
hoogvertrouwelijke inferentie blijft `INFERRED`.

## Policy outcomes

| Outcome | Betekenis |
| --- | --- |
| `ALLOW` | Het exacte request past nu binnen mandate, capability, limieten en freshness |
| `DENY` | Het request is expliciet niet toegestaan |
| `REQUIRE_APPROVAL` | Een menselijke approval boundary is nodig |
| `DEFER` | Er is nu onvoldoende of onveilige informatie om te beslissen |

Alleen `ALLOW` kan in de huidige Heart een `AuthorizationV1` opleveren. Die
authorization bindt aan requesthash, request, target, entity, capability,
parameterlimieten, snapshot, mandate en expiry.

## Execution receipt states

| State | Betekenis |
| --- | --- |
| `requested` | Request is aangeboden, nog niet geaccepteerd |
| `accepted` | Target heeft een niet-terminale task geaccepteerd |
| `running` | Task loopt |
| `succeeded` | Executor meldt terminale succesvolle uitvoering |
| `partial` | Slechts een deel is uitgevoerd |
| `failed` | Executor meldt terminale fout |
| `cancelled` | Task is geannuleerd |
| `unknown` | Uitkomst kan niet betrouwbaar worden vastgesteld |

`succeeded` is een uitvoeringsstatus. Doelsucces volgt pas uit een verse
post-observatie en `EffectDeltaV1`. Bij een exception rond dispatch bewaart Heart
een `unknown` receipt in plaats van aan te nemen dat niets gebeurde; opnieuw
dispatchen zou immers een fysiek effect kunnen dupliceren.

## `EffectDeltaV1`

Een effectdelta bindt:

- goal, proposal, request en receipt;
- pre- en post-snapshot;
- evidence grade;
- `achieved: true | false | null`;
- gemeten changes en observation-ID's;
- reden en observatietijd.

`true` betekent dat de pluginoracle binnen zijn gedocumenteerde dekking het
effect in de verse poststate heeft bevestigd. `false` betekent dat voldoende
dekking een negatief resultaat rechtvaardigt. `null` betekent onbekend, niet
stilzwijgend mislukt of geslaagd.

## Goalstatussen in de v2-Heart

Goalstatus is momenteel een opgeslagen string, geen publieke enum. De canonical
v2-route gebruikt deze waarden:

| Status | Wanneer |
| --- | --- |
| `active` | Goal heeft nog niet-aangetoonde effecten en kan verder werken |
| `monitoring` | Een `maintain`-goal is nu aantoonbaar stabiel |
| `completed` | Een `achieve`-goal is aantoonbaar bereikt |
| `waiting` | Brain defer/wait, policy blokkeert of een task loopt |
| `uncertain` | Vereist bewijs of taskidentiteit is onbekend |
| `abandoned` | Stopconditie of expliciete brainbeslissing beëindigt het doel |
| `degraded` | De living loop isoleerde een goalfout en blijft voor andere doelen beschikbaar |

Een stabiele `monitoring`-goal doet nul executive- en specialistcalls. Bij drift
kan hij weer de bestaande lifecycle ingaan.

## Learningstatussen

Preference candidates gebruiken:

| Status | Betekenis |
| --- | --- |
| `candidate` | Bewijs verzameld, gate nog niet gehaald |
| `shadow` | Counterfactual evaluatie zonder dispatch |
| `promoted` | Nieuwe GoalSpec-versie opgeslagen |
| `rejected` | Candidate expliciet of door conflict afgewezen |
| `rolled_back` | Eerdere promotie via opgeslagen patch teruggedraaid |

Routine candidates gebruiken `candidate`, `shadow`, `ready_for_approval`,
`promoted`, `rejected` en `rolled_back`. Een bewezen candidate wordt alleen
automatisch gepromoveerd met een passend exact low-risk autonomieprofiel; anders
stopt hij bij `ready_for_approval`.

Actieve routines gebruiken:

| Status | Betekenis |
| --- | --- |
| `shadow` | Nog uitsluitend counterfactual |
| `ready_for_approval` | Gates gehaald, ownerapproval ontbreekt |
| `active` | Guard mag de gekoppelde GoalSpec activeren |
| `dormant` | Guard is aantoonbaar false of recurrence/cooldown blokkeert |
| `guard_uncertain` | Guardbewijs is unknown, stale of conflicting |
| `conflicted` | Een gelijkwaardige tegengestelde routine blokkeert deterministisch |
| `suspended` | Authority, profiel, manifest of limiet is niet meer geldig |
| `rejected` | Candidate/routine is afgewezen |
| `rolled_back` | Routine, goal en submandate zijn exact teruggedraaid/ingetrokken |

## Snapshot en provenance

`TargetObservationV2` heeft een targetrevision. `WorldSnapshotV2` bewaart die per
target en voegt een Engine-brede monotone revision toe. De SHA-256 van canonieke
data identificeert het artefact. Een model krijgt slechts een begrensde
contextprojectie; de volledige snapshot blijft lokale operational state.

Plan-cachehergebruik vereist een passende goalversie, effectselector,
manifestfingerprint en mandate. Een gewijzigde manifest- of authorityscope maakt
een eerder succes dus niet automatisch opnieuw geldig.

## Wat de repository nu wel bewijst

De huidige deterministic tests en referenceplugins dekken onder andere:

- statische/dynamische manifestvergelijking;
- multi-target snapshots en restart reconstruction;
- voorstel → request → policy → authorization → receipt → post-observe → oracle;
- ACK-zonder-effect;
- task poll/cancel en recovery na process restart;
- exactly-once experience-import en begrensde learning;
- routineguards, shadow zonder dispatch, conflict en rollback;
- één executive-interface met deterministic en model-backed implementatie.

Dit is software- en simulatiebewijs. De repository claimt daarmee geen universele
veiligheid, certificering of fysiek veilige toestand.

## Open bewijs- en productgaps

- Geen algemene pluginmarketplace of automatische trust/distributieketen.
- Geen afgedwongen cryptografische signing van pluginartefacts.
- Geen algemene OS-/proces-/netwerksandbox die manifest-needs afdwingt.
- `stream` heeft contract/store scaffolding maar geen end-to-end referenceproof.
- Geen multi-executive runtime; één application kiest één executive.
- De preregistreerde, herhaalde fysieke Homey lux/watt-gate is niet door de
  softwaretests vervangen.

