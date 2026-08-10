---
title: Begrippenlijst
description: Canonieke Engine-termen voor wereld, action lifecycle, cognition en learning.
sidebar_position: 3
---

# Begrippenlijst

Gebruik deze termen precies. Vooral proposal/authority, prediction/observation en
state/weights mogen niet als synoniemen worden gebruikt.

## A

### `ACHIEVE`

Goalmodus waarin een doel na onafhankelijk aangetoonde vervulling `completed`
wordt. Anders dan `MAINTAIN` blijft het doel daarna niet als continue monitorlus
actief.

### `ActionRequestV1`

Exact, typed verzoek voor één target en entity. Het bevat capability,
parameters, snapshot/world/targetrevision, preconditions, deadline en eventueel
idempotency key. Het request is nog geen toestemming.

### Adapter

Plugincomponent die canonieke Engine-contracten vertaalt naar een
targetprotocol en terug. De publieke rollen zijn fijner gescheiden in provider,
controller, executor en oracle.

### `AuthorizationV1`

Scoped en expiring bewijs dat één exact requesttype in een concrete scope mag
worden uitgevoerd. Bindt onder andere requesthash, target, entity, capability,
limieten, snapshot, mandate en policybeslissing.

### `AutonomyProfileV1`

Door de owner expliciet geactiveerde low-risk delegatie voor exacte entities,
capabilityfamilies, routinetemplates en limieten. In de huidige eerste tranche is
dit Homey-lighting-specifiek. Het profiel is geen algemene “alles mag”-modus.

## B

### Behavior signal

`BehaviorSignalV1`: plugin-evidence over een externe verandering of patroon,
met scope, preference, context, provenance en evidence grade. Herhaald gedrag is
geen consent.

### Brain

Vervangbare deliberatieve component. De executive kiest een besliskind of
semantisch proposal; een specialist adviseert binnen capabilityfamilies. Een
brain bezit geen authoritative world state, policy, authorization, executor of
succesoracle.

### Bounded context projection

Tijdelijke, begrensde selectie van goal, actuele relevante worlddata,
effectresultaten, capabilities en specialistmetadata voor een brain. De
projectie is geen operational state en kan opnieuw worden opgebouwd.

## C

### Capability

Een typed operatie die een target aanbiedt onder expliciete input-/effectschema's,
units, preconditions, risk/privacy, limieten, deadline, invocation mode en
recoverysemantiek.

### Capability family

Stabiele semantische familie die dynamische targetinstanties groepeert. De
family is statisch gedeclareerd; onbekende dynamische families blijven opaque en
read-only.

### Capability graph

Conceptuele actuele verzameling van targets, capabilities, afhankelijkheden en
beschikbaarheid. De huidige runtime projecteert manifests en per-target discovery
in snapshots/context; niet iedere graphbewerking is een aparte publieke CLI.

### Controller

`DomainController`: vertaalt een semantisch proposal naar een exact
`ActionRequestV1` binnen de capability-envelop. Dit is geen realtime
devicecontroller in de betekenis van een motor-/flightcontrol-loop.

### Coverage

Beschrijving van welk deel van de wereld een observation of provideruitvoer
daadwerkelijk dekt. Zonder volledige relevante coverage mag afwezigheid niet als
`false` worden geïnterpreteerd.

## D

### `DEFER`

Policy-outcome: er is nu onvoldoende, conflicterend of onveilig bewijs om allow
of een definitieve deny te geven.

### Desired effect

Typed gewenste toestand binnen een GoalSpec, gebonden aan een capabilityfamily,
entityselector, condition en semantische parameters.

### Deterministic executive

Providerloze baseline die dezelfde onbetrouwbare `BrainDecisionV2`-seam gebruikt
als een model executive. Bekende violations kunnen zo zonder LLM worden gerouteerd.

## E

### Effect oracle

Pluginrol die proposal, prestate, receipt en verse poststate reconcilieert. De
oracle produceert een `EffectDeltaV1`; hij moet unknown teruggeven als zijn
metingen onvoldoende zijn.

### `EffectDeltaV1`

Duurzame beschrijving van waargenomen verandering tussen twee snapshots, met
evidence grade, achieved true/false/null, observation-ID's en reden.

### Entity

Stabiel geïdentificeerd object in een targetwereld, bijvoorbeeld een warehousebin
of devicezone. Een naam of embedding is geen canonieke identity.

### Evidence grade

Classificatie `OBSERVED`, `DERIVED`, `INFERRED`, `UNKNOWN`, `CONFLICTING` of
`STALE`. Staat los van confidence en quality.

### Executive brain

De ene runtimebrede brain die in een Heartapplication het volgende cognitieve
staptype kiest. Huidige compositie: deterministic of één model-backed executive.

### Execution receipt

`ExecutionReceiptV2`: executorfeit over requested/accepted/running/succeeded/
partial/failed/cancelled/unknown. Een receipt is geen bewijs dat een GoalSpec-
effect bereikt is.

### Experience

Historische actions, outcomes en behavior evidence. Experience is niet dezelfde
laag als actuele state, modelweights of tijdelijke context.

## G

### GoalSpec

`GoalSpecV2`: declaratief gewenst resultaat met scope, desired effects,
preferences, constraints, budgets, stop conditions, mode en mandatebinding.

## H

### Heart

De lokale, duurzame runtimekern. De Heart observeert, reconstrueert state,
evalueert goals/routines, roept zo nodig brains aan, valideert proposals,
doorloopt policy/authorization/execution, observeert opnieuw en bewaart auditdata.
De Heart is geen LLM en geen hard-realtime controller.

## I

### Idempotency key

Sleutel waarmee een target of executor kan herkennen dat dezelfde logische
request opnieuw wordt aangeboden. Vereist eerlijke targetsemantiek; het veld
alleen maakt een niet-idempotente fysieke actie niet veilig.

### Imagined state

Ephemeral counterfactual of voorspelde toestand. Mag plannen helpen, maar is
geen observation en wordt niet als authoritative world state opgeslagen.

### Invocation mode

`immediate`, `task` of `stream`. Immediate retourneert direct; task heeft een
duurzaam handle en polling/cancel; stream veronderstelt cursor/reconnect. De
huidige end-to-end reference dekt task, niet stream.

## L

### Learning candidate

Duurzaam voorstel om een namespaced preference te wijzigen na gevalideerde
behavior evidence. Candidate, shadow, promotion en rollback zijn gescheiden
statussen.

### Learning

In Engine: begrensde, auditable state/preference- of routineadaptatie. Het is in
de huidige runtime geen online training van modelweights en kan authority niet
uitbreiden.

### Lease

SQLite-gebaseerd exclusief eigenaarschap van de actieve runtime op één
Engine-store, met heartbeat en verliesdetectie. Voorkomt twee gelijktijdige
executive loops op dezelfde operationele state.

## M

### `MAINTAIN`

Goalmodus waarin Engine een aantoonbaar gewenste toestand blijft monitoren en na
geobserveerde drift opnieuw kan handelen.

### Mandate

`StandingMandateV1`: door een bevoegde actor geactiveerde scope voor plugins,
targets, entities, capabilities, limieten, privacy, learning, geldigheid en
manifestversies. Een goal of brain maakt niet zijn eigen mandate.

### Mini-brain

Een gespecialiseerde learned component achter een capabilitycontract. Vereist
onder meer scope, uncertainty/defer, provenance, baseline, held-out evaluatie,
hardwaremetingen en rollback. Er is geen speciale authority omdat een component
neuraal is.

## O

### Observation

`ObservationV1`: typed evidence met entity, property, value, bron, tijd,
evidence grade, unit, quality, coverage en optionele artefactidentity.

### Opaque capability

Dynamisch ontdekte maar niet statisch ingeschreven family. Wordt als query-only,
read-only en observe-only geprojecteerd totdat een typed manifestfamilie wordt
geïnstalleerd en enrolled.

## P

### Plugin

Installable `engine.plugin/v2`-pakket met statisch manifest en runtimefactory. Een
plugin bezit domeinsemantiek en adapters, niet Engine's generieke authority.

### Policy decision

Deterministische `ALLOW`, `DENY`, `REQUIRE_APPROVAL` of `DEFER` met reasons.
Alleen policy kan in de Heart-route een authorization laten ontstaan.

### Prediction

Voorspelde verandering. Blijft gescheiden van een independently observed effect.

### Proposed action

`ProposedActionV1`: onbetrouwbare kandidaat voor één desired effect, gebonden aan
goal en snapshot. Heeft geen execution rights.

## R

### Relation

Typed, gerichte relatie tussen twee entities met bron, tijd en evidence grade.
Een `RelationHypothesisV1` blijft per contract `INFERRED`.

### Routine

Duurzame activation layer boven één gekoppelde GoalSpec. Bevat scoped guard,
recurrence, cooldown, priority, conflict key en status; vervangt policy of goal
niet.

### Routine compiler

Plugincomponent die verklaarde patroonsemantiek omzet in inert RoutineSpec- en
GoalSpec-data. Kan geen authorization maken.

## S

### Safe state

Targetspecifieke toestand om bij failure na te streven. Bereiken moet opnieuw
worden waargenomen; Engine neemt rollback- of stop-succes niet aan.

### Shadow

Counterfactual evaluatiefase zonder dispatch. Een echte opportunity ontstaat pas
als de guard true is en het gewenste effect aantoonbaar false; afwezigheid is
geen agreement.

### Specialist brain

Pluginbrain met declared supported families. Levert typed advies of proposal,
maar geen requestauthority of effectwaarheid.

### State

Actuele targetgebonden feiten en beliefs. Operationele state is duurzaam, typed
en reconstrueerbaar zonder providerconversation.

## T

### Target

Eén concrete software- of fysieke systeemgrens onder een stabiele target-ID,
bijvoorbeeld één warehouse of homecontroller.

### Target observation

`TargetObservationV2`: één observation boundary voor een target met monotone
revision, entities, relations, observations, coverage, availability en errors.

## W

### Weights

Herbruikbare geleerde modelparameters. Zijn niet actuele world state, niet
experience en niet authority. De huidige bounded learningroute traint geen weights.

### WorldSnapshot

`WorldSnapshotV2`: immutable/versioned materialisatie van de aangesloten wereld
op één logische boundary, met per-target revisions en evidencecoverage.

### World provider

Pluginrol die capabilities ontdekt, targetstate observeert en optioneel wake-ups
abonneert. Hij kiest geen goals en autoriseert niets.

## Y

### YOLO

CLI-naam voor expliciete ownerdelegatie van een strikt begrensde low-risk
routineklasse. In deze versie alleen exact ingeschreven Homey-lightingzones en
vaste templates/limieten. Geen onbeperkte autonome modus.

