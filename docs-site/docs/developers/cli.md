---
title: CLI-referentie
description: Actuele commando's van engine en engine-plugin in de repository.
sidebar_position: 4
---

# CLI-referentie

De workspace levert twee command-line interfaces:

- `engine`: de pluginneutrale runtime en operationele CLI;
- `engine-plugin`: scaffolding, manifestinspectie en plugintests.

Gebruik vanuit deze repository `uv run engine ...` en
`uv run engine-plugin ...`. De tabellen hieronder volgen de actuele
`argparse`-parsers; niet-geïmplementeerde roadmapcommando's staan er niet in.

## `engine plugins`

```console
uv run engine plugins list
uv run engine plugins inspect <plugin-id>
```

`list` retourneert een JSON-array met de statische manifests die bij
geïnstalleerde `engine.plugins`-entrypoints zijn gevonden. `inspect` retourneert
het canoniek geserialiseerde manifest. Een onbekende ID eindigt met exitcode 2.

Dit is lokale Python-discovery, geen marketplace- of registryclient.

## `engine world observe`

```console
uv run engine world observe
```

Vraagt alle geregistreerde targets om een observatie, materialiseert één
`WorldSnapshotV2` en schrijft die naar de Engine-store. Het commando neemt de
runtimelease; een concurrerende muterende/observerende runtime kan de lease dus
blokkeren. Een providerfout wordt in coverage opgenomen zodat ontbrekende state
niet als `false` wordt gepresenteerd.

## `engine setup`

```console
uv run engine setup \
  --plugin engine.reference-world \
  --target engine.reference-world.warehouse \
  --entity warehouse:bin:reserve \
  --capability warehouse.transfer-bin \
  --learning engine.reference-world.preference.reserve-target-band/v1 \
  --intent "Houd voldoende voorraad beschikbaar"
```

Vereiste opties:

| Optie | Betekenis |
| --- | --- |
| `--plugin` | Exact plugin-ID |
| `--target` | Geobserveerd target van die plugin |
| `--entity` | Geobserveerde entity onder dat target |
| `--capability` | Niet-opaque gedeclareerde capabilityfamily |
| `--learning` | Namespaced preference die aan de family is gebonden |
| `--intent` | Vrije tekst voor GoalSpec-compilatie |
| `--activate` | Sla mandate en goal daadwerkelijk op |

Zonder `--activate` is setup een preview en schrijft het geen goal of mandate.
Met `--activate` wordt één exact jaarmandaat vastgelegd op de gekozen plugin,
target, entity, capability, limieten en manifestversie.

De huidige setup-route vereist een geconfigureerd structured-outputmodel; het
modelresultaat wordt vervolgens geschema-valideerd en mag niet buiten de
geselecteerde family of entity komen. Voor high-risk authority bestaat in deze
CLI nog geen generieke approvalworkflow.

## `engine run`

```console
uv run engine run
```

Start de living loop totdat `SIGINT` of `SIGTERM` binnenkomt. De runtime:

- houdt één SQLite-lease met heartbeat;
- abonneert zich waar plugins events aanbieden;
- pollt per targetinterval;
- verwerkt duurzame wakes en taskhandles;
- observeert, evalueert routines en goals, en doorloopt zo nodig de mutatielifecycle.

Een tweede runtime op dezelfde store faalt gesloten op de lease. Als de actieve
runtime zijn lease verliest, vraagt de leasewatcher de loop te stoppen.

## `engine status`

```console
uv run engine status
uv run engine status --json
```

Beide vormen produceren momenteel JSON. Het resultaat bevat:

- `store`, `plugins`, `targets` en `plugin_failures`;
- de laatste `snapshot`;
- actieve `goals`;
- preference-learning candidates;
- routines en routine candidates;
- autonomieprofielen;
- de ID van de executive brain.

`status` neemt geen muterende runtimelease en leest de duurzame toestand.

## `engine learning`

```console
uv run engine learning status
uv run engine learning correct \
  --goal <goal-id> \
  --preference <preference-id> \
  --value '<json-waarde>'
uv run engine learning rollback --candidate <candidate-id>
```

`status` toont candidates. `correct` is een expliciete ownercorrectie: de
JSON-waarde wordt tegen het preference-schema gevalideerd en resulteert in een
nieuwe GoalSpec-versie. `rollback` werkt alleen op de exacte candidate en draait
een gepromote wijziging via de opgeslagen patch terug.

Onverklaard gedrag wordt niet via `correct` gesimuleerd; dat volgt de tragere
evidence → candidate → shadowroute.

## `engine routines`

```console
uv run engine routines list
uv run engine routines inspect <candidate-of-routine-id>
uv run engine routines approve <candidate-id>
uv run engine routines reject <candidate-id>
uv run engine routines rollback <routine-id>
```

`approve` accepteert alleen een candidate met status `ready_for_approval`, dus
niet een ongeteste of nog shadowende candidate. `rollback` maakt de gekoppelde
routine onwerkzaam en bewaart de audittrail.

## `engine yolo`

```console
uv run engine yolo enable --entity <exact-homey-zone-id>
uv run engine yolo status
uv run engine yolo disable
uv run engine yolo disable --profile <profile-id>
```

Aanvullende `enable`-opties:

| Optie | Default | Opmerking |
| --- | --- | --- |
| `--plugin` | `engine.homey` | Andere plugins worden in deze eerste tranche geweigerd |
| `--target` | automatisch bij precies één target | Verplicht als de plugin meerdere targets heeft |
| `--entity` | herhaalbaar, optioneel | Exacte zone-ID's; wildcards zijn verboden |
| `--maximum-brightness` | `0.70` | Moet in `(0, 1]` liggen |
| `--maximum-power-w` | `20.0` | Mag niet boven 20 W komen |

De naam `yolo` betekent hier niet onbeperkte autonomie. Het commando maakt een
owner-geactiveerd, persistent, exact en low-risk `AutonomyProfileV1` voor drie
statisch gedeclareerde Homey-lightingroutines. Zonder dit profiel eindigt een
bewezen routine bij `ready_for_approval`. Een profiel geeft geen model authority
en omzeilt policy, authorization of oracle niet.

Zonder `--entity` kiest de huidige implementatie alleen impliciet als precies één
controllable zone is geobserveerd. Bij nul of meerdere zones moet de owner de
exacte zone-ID's opgeven.

## `engine model canary`

```console
uv run engine model canary
```

Doet één echte structured-outputbeslissing via de geconfigureerde provider en
toont decision plus usage. Zonder modelconfiguratie faalt het commando.

Ondersteunde runtimevariabelen:

| Variabele | Doel |
| --- | --- |
| `ENGINE_DATABASE` | Storepad; default `.engine/engine.sqlite3` |
| `ENGINE_MODEL_BASE_URL` | OpenAI-compatibel endpoint |
| `ENGINE_MODEL_API_KEY` | Key voor remote endpoint |
| `ENGINE_MODEL_ID` | Model-ID |
| `ENGINE_MODEL_PROVIDER` | Audit-ID voor provider |
| `ENGINE_LOCAL_MODEL_BASE_URL` | Alias voor een lokaal endpoint |
| `ENGINE_LOCAL_MODEL_ID` | Alias voor lokaal model |
| `META_MODEL_API_BASE_URL` | Meta-provideralias |
| `META_MODEL_API_KEY` | Meta-providerkey |
| `META_MODEL_ID` | Meta-model-ID |

Alleen `localhost` en numerieke loopbackhosts mogen zonder API-key. Engine start
of downloadt geen lokaal modelproces.

## `engine-plugin`

```console
uv run engine-plugin init <naam> \
  [--template world|specialist|full] \
  [--destination <map>]

uv run engine-plugin validate [<pluginmap>]
uv run engine-plugin inspect [<pluginmap>]
uv run engine-plugin test [<pluginmap>]
```

`init` weigert een niet-lege doelmap. `validate` leest alleen het statische
manifest; `inspect` print de canonieke vorm. `test` valideert eerst en draait dan
`python -m unittest discover -s tests -v` met de gegenereerde `src` op
`PYTHONPATH`.

## Exitcodes en foutoutput

Beide CLI's retourneren 0 bij succes en 2 voor hun afgehandelde contract- of
runtimefouten. `engine` print `error: <Type>: <bericht>` naar stderr;
`engine-plugin` print manifestcontractfouten als `invalid: <bericht>`.
