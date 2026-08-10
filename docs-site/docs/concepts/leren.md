---
title: Hoe Engine leert — en niet leert
sidebar_position: 6
description: Het verschil tussen state, ervaring, preferences, routines, planreuse en toekomstige modelweights.
---

# Hoe Engine leert — en niet leert

Engine gebruikt “leren” niet als verzamelwoord voor iedere statewijziging. De huidige implementatie past duurzame preferences en routines aan via vaste evidencegates. Zij traint geen modelweights en maakt geen observation of authorization uit herhaald gedrag.

> **Status:** expliciete corrections, pluginneutrale behavior-import, preference candidates, routine shadowing, GoalSpec-versioning en rollback **bestaan nu** en zijn met fakes/reference worlds getest. Online weighttraining en automatisch gemaakte mini-brains zijn **roadmap**.

## Vijf dingen die apart blijven

| Begrip | Betekenis | Voorbeeld |
| --- | --- | --- |
| **State** | Huidige targetfacts, goals en beliefs op een logisch observatiepunt | Lamp is uit; warehouse bin bevat twee kratten |
| **Experience** | Historische acties, receipts, effecten, correcties en outcomes | Deze route liep partial; deze instelling werd vijf keer extern gewijzigd |
| **Preferences/routines** | Versioned operationele configuratie afgeleid via expliciete of gated evidence | Gewenste reserveband; dagelijkse “uit”-routine |
| **Weights** | Getrainde modelparameters in een versioned artifact | Een toekomstig vision- of motionmodel |
| **Contextprojectie** | Tijdelijke, begrensde input voor een braincall | Alleen entities en observations rond dit goal |

Een statewijziging vereist geen training. Een preferencepromotie is geen nieuw neuraal model. Een nieuw modelartifact is geen actuele world state.

## Wat nu al ervaring gebruikt

Engine heeft meerdere, verschillende mechanismen die soms losjes “leren” worden genoemd.

### 1. Ervaring verandert latere routing

De oorspronkelijke 0.1-fixtures boeken observed effects en specialistoutcomes. Een negatieve specialistuitkomst kan na restart de volgende specialistselectie veranderen. De gridworld gebruikt een geobserveerd obstakel om opnieuw te plannen.

**Getest in simulatie.** Dit is een transparante heuristic/state reducer, geen weighttraining.

### 2. Geobserveerd succesvolle plannen kunnen worden hergebruikt

V2 kan een exact getypeerd plan cachen als een effectoracle `achieved: true` heeft vastgesteld. Hergebruik vereist dezelfde goalversie, situation key, capabilitymanifest-fingerprint en mandate. Daardoor kan een bekende situatie zonder nieuwe modelcall worden afgehandeld.

**Bestaat nu.** Dit is deterministic memoization van observed success, geen generalisatie naar willekeurige nieuwe situaties.

### 3. Expliciete ownercorrecties

Een expliciete correctie wordt `OBSERVED` preference-evidence, gevalideerd tegen de namespaced `PreferenceSpecV1` en direct in een nieuwe `GoalSpecV2`-versie geschreven. De oude versie en waarde blijven auditbaar.

**Bestaat nu.** Een correction mag alleen een reeds gedeclareerde preference wijzigen; hij voegt geen target, capability of mandate toe.

### 4. Inferred preference-adaptatie

Een plugin mag via een optionele `ExperienceProvider` cursor-based `BehaviorBatchV1`-signalen publiceren. De Heart:

1. valideert provider- en pluginidentity;
2. bewaart signalen exactly-once met een durable cursor;
3. controleert de declared preference en het valueschema;
4. linkt alleen als plugin, target, entity, capability, selector en preference bij een actief goal passen;
5. bewaart onbekende signalen als unlinked evidence in plaats van ze te negeren of authority te geven.

Een onverklaarde externe wijziging blijft `INFERRED`: het systeem weet niet of een mens, Flow, andere integratie of toeval de oorzaak was.

## Preferencegates

Voor een `shadow_low_risk` preferencekandidaat gelden minimaal:

- vijf equivalente voorbeelden;
- verdeeld over minstens drie UTC-dagen;
- minstens 80% consistente waarde;
- minstens 80% consistente context;
- geen expliciet conflict;
- een actief mandate met `learning.low-risk`;
- exacte plugin-, target-, entity- en capabilityscope;
- een shadowperiode van minstens zeven dagen.

Bij promotie maakt Engine een nieuwe `GoalSpecV2`-versie, bewaart evidence en outcomes, invalideert relevante planreuse en houdt een exacte rollbackpatch.

### Belangrijke bewijsgrens

De huidige preference-only code gebruikt na de vaste shadowduur een evidence-consistency outcome. Dat is genoeg om de versioning- en rollbackroute te testen, maar niet om te claimen dat een fysieke voorkeur betere effecten veroorzaakt. Waar een preference uitvoering of fysiek effect beïnvloedt, blijft onafhankelijk geobserveerd outcome-evidence de vereiste latere productgate.

Deze nuance voorkomt dat “de gebruiker deed dit vaak” wordt hernoemd tot “Engine weet dat dit beter werkt”.

## Routine learning

Routines hebben een sterkere counterfactual shadowroute. Plugins declareren statische `RoutineTemplateSpecV1`-templates en een deterministic `RoutineCompiler`. Core interpreteert alleen generieke guard-, recurrence-, conflict- en lifecyclecontracts.

De pipeline is:

```text
plugin behavior signals
  -> vaste evidencegates (5 voorbeelden, 3 dagen, 80%)
  -> compiled inert RoutineSpec + GoalSpec
  -> minstens 7 dagen shadow, zonder dispatch
  -> alleen echte trigger-opportunities tellen
  -> minimaal 3 gesloten opportunities
  -> minimaal 80% later geobserveerde agreement
  -> ready_for_approval OF auto-promotion binnen exact YOLO-profiel
  -> active routine + goal + mandate
  -> observe/act/oracle via de normale v2-lifecycle
```

Een ontbrekende opportunity telt niet als agreement. Een onzekere guard faalt gesloten. Conflicten, cooldowns, recurrence en rate limits zijn deterministic en duurzaam.

## Normale promotion en begrensde YOLO

Zonder autonomy profile kan een geslaagde routine alleen `ready_for_approval` worden. De owner activeert hem expliciet.

Met `engine yolo enable` delegeert de owner vooraf een smalle Homey-lightingenvelope. Auto-promotion mag dan alleen na dezelfde shadowgates en kan geen scope uitbreiden. Het profiel bevriest exacte entities, templates, capabilityfamilies, manifestfingerprint, risk ceiling en limieten. Afgeleide mandates duren 24 uur en mogen alleen exact worden vernieuwd.

Een extern tegengestelde wijziging krijgt tijdelijk actuatorbezit. Een expliciet conflict of drie tegengestelde veranderingen binnen zeven dagen rolt routine, linked goal en mandate terug.

Deze route is **fake-getest**, niet fysiek gecertificeerd.

## Wat Engine niet leert

De huidige Engine:

- traint geen foundation model;
- fine-tunet geen general brain online;
- verandert geen weights op een edge-device;
- maakt niet automatisch nieuwe pluginfamilies;
- leidt permission niet af uit herhaling;
- verruimt geen targets, entities, risk, privacy of mandate duration;
- noemt een modelvoorspelling geen observation;
- gebruikt embeddings of vrije beschrijvingen niet als canonieke identities;
- schrijft niet zelfstandig code of skills naar de production runtime.

## Kan Engine een nieuw apparaat “leren kennen”?

Alleen binnen een al gedeclareerd contract. Een provider mag nieuwe instances van een enrolled capabilityfamilie ontdekken. De plugin levert dan de entity, observations en exacte familybinding. Een volledig onbekende family wordt `opaque`, `QUERY` en read-only.

Voor mutatie van een werkelijk nieuw apparaattype zijn nodig:

- een versioned pluginmanifest;
- schemas, units, risk/privacy en limieten;
- controller, executor en effectoracle;
- een fake/simulator en conformancebewijs;
- expliciete enrollment/mandate;
- waar relevant een targetcontroller en onafhankelijke safetylaag.

Dat is pluginontwikkeling, geen stil online leren.

## Toekomstige mini-brains

Een mini-brain is een optionele specialist, bijvoorbeeld voor perceptie, anomaly detection, routekeuze of een control residual. Het krijgt geen eigen authority en mag nooit een hard-realtime controller vervangen zonder target-specifiek bewijs.

Voordat zo'n learned component op een correctness- of safetyrelevant pad komt, vereist de projectconstitutie minimaal:

- een gemeten beperking van een eenvoudiger deterministic/klassieke baseline;
- exact input-, output- en unitcontract;
- supported targets/versies en safe operating envelope;
- onzekerheid/defergedrag en fallback;
- trainingdata-provenance en reproduceerbaar manifest;
- held-out evaluatie en preregistreerde thresholds;
- latency-, quantization- en hardwaremetingen;
- artifactidentity, rollout en rollback.

Training is standaard off-device; online updates zijn een afzonderlijke, latere hypothese. Een mini-brain moet zijn complexiteit verdienen en kan weer worden verwijderd als de baseline gelijk of beter blijkt.

## Samenvatting

| Vraag | Antwoord nu |
| --- | --- |
| Leert Engine van expliciete correcties? | Ja, als versioned GoalSpec-preference |
| Leert Engine patronen/routines? | Ja, via vaste evidence- en shadowgates |
| Gebruikt eerdere observed success? | Ja, voor begrensde planreuse/routing |
| Leert Engine permissions? | Nee |
| Traint Engine modelweights? | Nee |
| Maakt Engine zelfstandig mini-brains? | Nee, roadmap na behoeftebewijs |
| Is fake-learning fysiek effectbewijs? | Nee |

Zie [Alle modi](./modi.md) voor de learning- en routinestatussen en [Het einddoel](./einddoel.md) voor de plaats van mini-brains in de langere richting.
