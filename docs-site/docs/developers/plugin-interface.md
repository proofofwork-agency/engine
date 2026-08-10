---
title: Plugininterface v2
description: Statisch manifest, runtimeprotocollen en de grens tussen wereldsemantiek en Engine.
sidebar_position: 2
---

# Plugininterface v2

`engine.plugin/v2` is de publieke grens tussen Engine en een wereld. Een plugin
mag één of meer targets observeren en kan typed capabilities, controllers,
executors, effectoracles, specialisten en experience providers aanbieden. Engine
blijft eigenaar van de generieke lifecycle, policy, authorization en audit.

Een plugin bestaat altijd uit twee kanten:

1. een statisch `engine-plugin.toml`, leesbaar vóór import;
2. een Python-factory in de entrypointgroep `engine.plugins` die een object met
   het `WorldPluginV2`-oppervlak teruggeeft.

Import en factory-aanroep horen inert te zijn: niet verbinden, geen target
muteren en geen achtergrondproces starten. Verbindingen ontstaan pas in de
expliciete provider- of executoroperatie.

## Registratie

Declareer de distributie-entrypoint in `pyproject.toml`:

```toml
[project.entry-points."engine.plugins"]
mijn_wereld = "mijn_wereld.plugin:load_plugin"
```

De runtime zoekt de bijbehorende `engine-plugin.toml`, valideert die en vergelijkt
de statische manifestinhoud met `plugin.manifest`. Een verschil in identiteit,
rollen, capabilities, preferences of routines blokkeert registratie. Dubbele
plugin- en target-ID's worden eveneens geweigerd.

Er is momenteel geen Engine-marketplace. Installatie en distributiekeuze lopen
via normale Python-packaging en de lokale beheerder.

## Minimaal manifest

Een muterende capability heeft meer informatie nodig dan een toolnaam:

```toml
[plugin]
id = "example.warehouse"
version = "0.1.0"
engine_api = ">=2.0,<3"
contract_version = "engine.plugin/v2"
description = "Bounded warehouse world"

[declarations]
world_providers = ["warehouse"]
controllers = ["warehouse-controller"]
executors = ["warehouse-executor"]
effect_oracles = ["warehouse-oracle"]
specialists = []
entity_types = ["warehouse.bin"]
relation_types = []
observation_types = ["bin.count"]
experience_providers = []
routine_compilers = []

[needs]
network = []
filesystem = []
secrets = []
privacy = []

[store]
identity = "example.warehouse.store"
schema_version = 1

[[capability_families]]
id = "example.warehouse.transfer-bin/v1"
family = "warehouse.transfer-bin"
version = "1.0.0"
description = "Verplaats een begrensd aantal kratten"
control_layer = "semantic"
invocation_mode = "task"
risk_class = "low"
privacy_class = "local"
idempotent = true
deadline_ms = 5000
input_schema = {type = "object", required = ["from", "to", "count"]}
effect_schema = {type = "object", required = ["minimum_count"]}
effect_measurements = ["bin.count"]
limits = {count = {min = 1, max = 10}}
recovery = "poll_task_then_observe"
```

Het manifest declareert behoefte; het dwingt die behoefte nog niet zelfstandig
af. De huidige runtime heeft nog geen algemene sandbox- of permission-enforcement
op basis van `[needs]`, en valideert pluginartefacts nog niet cryptografisch.
Behandel signing en sandboxing dus als open productgaps, niet als bestaande
veiligheidsgarantie.

## De rollen

### `WorldProvider`

Een provider bezit `plugin_id`, een stabiele `target_id`, poll- en
freshnessintervallen en implementeert:

- `discover()` voor capability-instanties;
- `observe()` voor een monotone `TargetObservationV2`;
- `subscribe(wake)` als optionele wake-upbron.

`observe()` retourneert entities, relations, observations, dekking, bron,
targetrevision en beschikbaarheid. Een event is slechts aanleiding om opnieuw te
observeren; het event zelf is niet automatisch operationele waarheid.

### `DomainController`

De controller vertaalt een semantische `ProposedActionV1` naar een exacte
`ActionRequestV1`. Dit is waar domeinbetekenis, units, doelparameters,
targetrevision, deadline en idempotency key worden vastgelegd. De controller mag
niet van target, entity, goal of capability wisselen.

### `Executor`

De executor ontvangt uitsluitend een concrete request plus een
`AuthorizationV1`. Hij implementeert `dispatch`, `poll` en `cancel` en retourneert
een `ExecutionReceiptV2`. Een receipt zegt wat de executor weet over de
uitvoering; een ACK bewijst niet dat het gewenste effect in de wereld bestaat.

### `EffectOracle`

De oracle vergelijkt proposal, pre-snapshot, receipt en een verse post-snapshot.
Hij levert een `EffectDeltaV1` met bewijsniveau, `achieved: true | false | null`,
metingen en reden. Bij onvoldoende dekking is `null`/`UNKNOWN` correcter dan
`false`.

### `SpecialistBrainV2`

Een specialist declareert ondersteunde capabilityfamilies en geeft typed
`SpecialistAdviceV1`. Hij mag een voorstel leveren, maar kan niet autoriseren,
dispatchen of zijn eigen succes vaststellen.

### `ExperienceProvider`

Een experience provider publiceert cursor-gebaseerde `BehaviorBatchV1`-waarden
uit plugin-eigen opslag. Engine bewaart signalen exactly-once per cursor en kan
ze koppelen aan een namespaced preference of routinetemplate. Een behavior
signal is bewijs, geen impliciete toestemming.

### `RoutineCompiler`

Een routinecompiler vertaalt plugin-eigen patroonsemantiek naar een inert
`RoutineSpecV1` plus `GoalSpecV2`. Hij kan geen mandate of authorization maken.

## Discovery is begrensd door het manifest

Een provider mag dynamische apparaten ontdekken, maar alleen vooraf gedeclareerde
capabilityfamilies kunnen de muterende route in. Een onbekende family wordt als
`opaque`, `query`, `read_only` en `observe_only` geprojecteerd. Dit voorkomt dat
een nieuw targetdevice automatisch nieuwe authority creëert.

Voor muterende capabilities vereist de manifestvalidator minimaal een provider,
controller, executor en effectoracle. Een v1-plugin kan via de compatibiliteitsbrug
zichtbaar blijven, maar is in de v2-worldruntime observe-only.

## Lifecycle van een mutatie

```text
verse observatie
  -> onbetrouwbaar voorstel
  -> scope- en schemavalidatie
  -> controller maakt exact request
  -> deterministische policy
  -> request-gebonden authorization
  -> executor dispatch/poll/cancel
  -> verse post-observatie
  -> plugin-oracle reconcilieert effect
  -> receipt en EffectDelta worden duurzaam vastgelegd
```

Een capability met `immediate` kan direct terminaal antwoorden. `task` gebruikt
een duurzaam external handle, polling, deadline cancellation en restart recovery.
`stream` bestaat in het publieke contract en de store heeft scaffolding, maar er
is nog geen end-to-end streamreference die reconnect en cursorherstel bewijst.

## Opslaggrens

Een plugin declareert een eigen store identity en schema version. Plugindata
hoort niet in Engine's private operationele tabellen en Engine deelt geen
mutable database als impliciete interface. Wissel alleen publieke contractwaarden
uit.

## Wat conformance wel en niet bewijst

`engine-plugin validate` valideert het statische manifest. `engine-plugin test`
start de gegenereerde `unittest`-suite. `engine_sdk.check_plugin()` controleert
onder andere identiteiten, duplicate targets, providerobservaties, declarations
en undeclared families.

Dat bewijst contractvorm en fakegedrag. Het bewijst geen netwerkisolatie,
artefactsigning, fysieke veilige toestand, timinggarantie of certificering.

