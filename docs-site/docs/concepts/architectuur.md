---
title: Architectuur
sidebar_position: 3
description: De canonieke Engine v2-architectuur, pluginrollen, stores en volledige actie-lifecycle.
---

# Architectuur

De canonieke productieroute is `engine.plugin/v2`: dependency-light contracts in `engine-sdk`, de generieke Heart en store in `src/engine`, en composition/discovery/CLI in `engine-runtime`. De oudere v1-kern blijft beschikbaar voor compatibiliteitsbewijs, maar v1-plugins zijn in de v2-world observe-only.

> **Status:** de v2 verticale softwaretranche **bestaat nu**. De lifecycle is met Homey-fakes en een reference-warehouse getest. Live Homey whole-world observation is bewezen; live v2-mutatie en fysieke certificering niet.

## Lagen

```text
Intent surfaces (mens, CLI, later andere clients)
        |
        v
GoalSpecV2 + StandingMandateV1       duurzame Engine-state
        |
        v
WorldHeartV2 ----------------------> WorldStore (SQLite/WAL)
   |         |          |
   |         |          +----------> general brain + specialists
   |         +---------------------> policy + authorization
   +-------------------------------> PluginRegistryV2
                                         |
                 +-----------------------+----------------------+
                 |          |            |          |           |
          WorldProvider  Controller   Executor   Oracle   Experience/Routine
                 |          |            |          |           |
                 +---------------------- target/world -----------+
```

De Heart is generiek. De plugin bezit de betekenis van “licht”, “krat”, “bestand” of “robotpose”. Een target kan zijn eigen store hebben, maar deelt geen mutable operationele tabellen met Engine.

## De duurzame objecten

| Object | Rol |
| --- | --- |
| `WorldSnapshotV2` | Een immutable logisch observatiepunt samengesteld uit targetobservaties met eigen monotone revisions |
| `ObservationV1` | Getypeerd evidence-item met bron, tijd, grade, unit, kwaliteit, coverage en optionele artifact-identiteit |
| `GoalSpecV2` | Gewenst effect, scope, constraints, budgets, stopcondities, voorkeuren, mode en versie |
| `CapabilitySpecV2` | Statisch capabilitycontract: schemas, control layer, invocation mode, risico, privacy, deadline, units, limieten en herstel |
| `ProposedActionV1` | Onbetrouwbaar semantisch voorstel, gebonden aan goal, effect, entity en snapshot |
| `ActionRequestV1` | Exact request met capability, parameters, precondities, revisions, deadline en idempotency key |
| `PolicyDecisionV1` | `ALLOW`, `DENY`, `REQUIRE_APPROVAL` of `DEFER`, inclusief redenen en policyversie |
| `AuthorizationV1` | Tijdelijk bewijs gebonden aan requesthash, target, entity, capability, limits, snapshot en expiry |
| `ExecutionReceiptV2` | Wat de executor daadwerkelijk accepteerde, uitvoerde of niet kon vaststellen |
| `EffectDeltaV1` | Verschil tussen pre- en poststate, met evidence grade en `achieved: true/false/unknown` |

Een modeltranscript is geen van deze objecten en kan ze niet vervangen.

## De volledige v2-lifecycle

Een muterende pass loopt als volgt.

### 1. Observeer een logische wereldgrens

Iedere `WorldProvider` levert entities, relations en observations voor zijn target. De Heart composeert ze tot een `WorldSnapshotV2`. Providerfouten, staleness en ontbrekende coverage blijven zichtbaar. Een event is alleen een wake hint; de eventpayload wordt niet vanzelf canonieke state.

### 2. Evalueer routine, stopcondities en gewenste effecten

Als een linked routine bestaat, controleert Engine eerst authority, guard, recurrence, cooldown, conflict en action limits. Daarna worden de declaratieve goalcondities tegen de snapshot geëvalueerd.

- Alles waar + `ACHIEVE` -> `completed`.
- Alles waar + `MAINTAIN` -> `monitoring`, zonder braincall.
- Vereist evidence onbekend -> `uncertain`, zonder mutatie.
- Stopconditie waar -> `abandoned`.
- Een geobserveerde schending -> cognition mag starten.

### 3. Hergebruik een geldig plan of projecteer begrensde context

Een eerder succesvol getypeerd plan mag alleen worden hergebruikt als de deterministic situation key, goalversie, capabilitymanifest-fingerprint en mandate nog overeenkomen. Anders bouwt `BoundedContextProjector` een target-/goalgerichte subset met entities, een-hop-relaties, observaties, effectresultaten, capabilities en specialisten. De volledige wereld blijft lokaal en duurzaam.

### 4. Laat het general brain een onbetrouwbare beslissing leveren

Het executive-brein kiest een van de cognitieve decision kinds. Het kan direct een `ProposedActionV1` leveren of een specialist selecteren. Een specialist levert `SpecialistAdviceV1` en eventueel een getypeerd voorstel. Iedere braincall krijgt een snapshotbinding, projectiehash, output, doel/purpose en latencyrecord.

### 5. Valideer het voorstel

De Heart controleert onder meer:

- hetzelfde goal en gewenste effect;
- dezelfde actuele snapshot en world revision;
- capability family verandert niet;
- entity en target vallen binnen de effectselector;
- capability is statisch bekend en niet `opaque`/observe-only;
- semantische parameters voldoen aan het effectschema.

Een afgewezen voorstel blijft auditbaar en krijgt geen execution rights.

### 6. Concretiseer en valideer het exact request

Een plugin-`DomainController` vertaalt het semantische effect naar een `ActionRequestV1`. De Heart controleert identities, target revision, inputschema en alle capability-/requestprecondities. De controller mag geen ander target, entity of capability kiezen.

Dit is de grens tussen strategie en devicebetekenis: een brein kiest “bereik dit effect”; de controller bepaalt het exacte protocolrequest binnen de capability-envelope.

### 7. Evalueer policy en maak authorization

De deny-by-default policy vergelijkt het request met het `StandingMandateV1`, de actuele pluginmanifestversie, privacy, risk class en parameterlimieten. Alleen `ALLOW` kan een `AuthorizationV1` opleveren. De authorization bindt cryptografisch aan de requesthash en verloopt uiterlijk bij request- of mandate-expiry.

`DENY`, `DEFER` en `REQUIRE_APPROVAL` stoppen voor dispatch. Geen brain, controller of pluginexecutor kan zelf dit bewijs maken.

### 8. Dispatch en boek het receipt

De `Executor` ontvangt exact het request en de authorization. Een geldig `ExecutionReceiptV2` moet bij dezelfde identities horen. Adapterexceptions of contradictoire receipts worden als terminal `UNKNOWN` geboekt; de lifecycle blijft niet stil op `REQUESTED` hangen.

### 9. Observeer opnieuw

Na dispatch maakt de Heart een verse world snapshot. Een HTTP-ACK, teruggegeven tekst of modelconfidence is geen poststate.

### 10. Reconcile met de effectoracle

De plugin-`EffectOracle` vergelijkt proposal, pre-snapshot, receipt en post-snapshot. Het resultaat is een `EffectDeltaV1` met gemeten changes, observation IDs, evidence grade en een onafhankelijk `achieved`-oordeel. Een defecte oracle levert `UNKNOWN`, geen stil succes.

### 11. Werk goalstatus, wakes, cache en audit bij

Engine evalueert het goal opnieuw:

- effect bereikt -> `completed` of `monitoring`;
- evidence onbekend -> `uncertain`;
- task nog `accepted/running` -> `waiting` plus duurzame pollwake;
- anders -> `active` voor een volgende pass.

Alle lifecycleobjecten blijven bewaard. Alleen een geobserveerd succesvolle, exact gebonden route kan de deterministic plancache voeden.

## Afwijking voor `TASK`

Een task-executor mag `ACCEPTED` of `RUNNING` met een `external_handle` teruggeven. De Heart slaat de niet-terminale lifecycle op en plant een duurzame wake. Bij de volgende pass:

1. laad proposal, request, authorization en laatste receipt;
2. poll het handle, of cancel wanneer de deadline bereikt is;
3. boek het nieuwe receipt;
4. observeer opnieuw;
5. reconcile via dezelfde oracle;
6. plan opnieuw zolang de task niet terminaal is.

Deze route **bestaat en is fake-getest** in de reference warehouse, inclusief procesrestart en deadline-cancellation. `STREAM` staat in de contracts, maar heeft nog geen vergelijkbare end-to-end reference proof.

## Plugininterface

Iedere v2-plugin heeft een inert statisch `engine-plugin.toml` en een Python-entrypoint in de groep `engine.plugins`. De runtime leest eerst het statische manifest en vergelijkt dat met de geladen plugin. Factory construction hoort geen netwerkverbinding of mutatie te starten.

De publieke rollen zijn bewust gescheiden:

| Rol | Mag | Mag niet |
| --- | --- | --- |
| `WorldProvider` | capabilities ontdekken, observeren, optioneel wake hints abonneren | doelen kiezen of target muteren |
| `DomainController` | semantisch voorstel concretiseren binnen capabilitycontract | authority maken of effect bevestigen |
| `Executor` | geautoriseerd request dispatchen, task pollen/cancelen | strategy kiezen |
| `EffectOracle` | prestate, receipt en poststate reconciliëren | voorspelling als observatie presenteren |
| `SpecialistBrainV2` | begrensd advies/getypeerd voorstel leveren | uitvoeren of autoriseren |
| `ExperienceProvider` | cursor-based gedragssignalen publiceren | GoalSpecs patchen of toestemming afleiden |
| `RoutineCompiler` | pluginpatroon naar inert routine-/goaldata vertalen | mandate maken |

Een plugin kan alleen mutable capabilityfamilies gebruiken die statisch zijn gedeclareerd en enrolled. Onbekende dynamische capabilities worden `opaque`, `QUERY` en read-only geprojecteerd.

## SDK en runtime

### `engine-sdk` — **bestaat nu**

Bevat publieke datatypes, protocollen, manifestvalidatie, conformancehelpers en `engine-plugin` scaffolding. De templates `world`, `specialist` en `full` genereren een apart installeerbare pluginstructuur. Plugin-auteurs hoeven de volledige Heart-runtime niet te importeren.

### `engine-runtime` — **bestaat nu**

Bevat entrypoint discovery, composition, runtime lease, signal handling, modelconfiguratie en de `engine` CLI. Belangrijke surfaces zijn plugininspectie, world observation, setup-preview/activation, run/status, learning, routines, begrensde YOLO-enrollment en model canary.

### Volwassenheidsgrens

De interfaces en reference plugin zijn een coherente alpha. Ze zijn nog geen bewijs van een grote third-party ecosystem, cross-language SDK, production supervisor of universele targetondersteuning.

## Stores en isolatie

Engine gebruikt een eigen SQLite/WAL-ledger voor world snapshots, goals, lifecycleobjecten, braincalls, wakes, evidence, candidates en routines. Een plugin mag een eigen versioned store gebruiken voor targetidentiteiten of ruwe domeinevidence. Store-identiteiten blijven gescheiden; een plugin schrijft niet rechtstreeks in Engine-tabellen.

Dat maakt reconstructie mogelijk zonder modelgeheugen en voorkomt dat een plugin ongemerkt de authoritative Engine-state wordt.

## Realtime- en safetygrens

```text
Engine Heart: intentie, observatie, deliberatie, policy, audit
        |
        | hoog-niveau, begrensd en geautoriseerd request
        v
Targetcontroller: protocol, timing, lokale limieten, watchdogs
        |
        v
Onafhankelijke safety/interlocks en fysiek systeem
```

Een targetcontroller kan requestparameters verder beperken of weigeren. Engine-policy vervangt nooit de fysieke safetylaag. Lees [Wat Engine niet is](./wat-engine-niet-is.md) en [Alle modi](./modi.md) voor de bijbehorende statussen en risicoklassen.
