---
title: Quickstart vanuit de repository
description: Installeer de uv-workspace, inspecteer plugins en voer de contracttests uit.
sidebar_position: 1
---

# Quickstart vanuit de repository

Engine wordt in deze repository ontwikkeld als een Python 3.12+-workspace. De
packages zijn nog niet als algemene PyPI-installatieroute gedocumenteerd. Werk
daarom vanuit een checkout van de repository en gebruik het gelockte
workspacebestand.

## Vereisten

- Python 3.12 of nieuwer;
- [uv](https://docs.astral.sh/uv/);
- een lokale checkout van deze repository.

## 1. Synchroniseer exact de workspace

Voer dit uit in de root van de repository:

```console
uv sync --all-packages --locked
```

`--all-packages` neemt `engine-heart`, `engine-sdk`, `engine-runtime` en de
workspaceplugins mee. `--locked` weigert een onbedoelde herberekening van
`uv.lock`.

## 2. Controleer discovery

```console
uv run engine plugins list
uv run engine plugins inspect engine.reference-world
```

De runtime vindt geïnstalleerde plugins via de Python-entrypointgroep
`engine.plugins`. `plugins inspect` toont de statische, gevalideerde declaratie;
het is geen marketplace-query en downloadt niets.

## 3. Observeer zonder te muteren

```console
uv run engine world observe
uv run engine status --json
```

`world observe` vraagt de beschikbare providers om een verse observatie en
slaat een samengestelde `WorldSnapshotV2` op. Een ontbrekende configuratie van
een optionele plugin verschijnt als discovery failure. Engine verzint daardoor
geen negatieve toestand: ontbrekende of verouderde dekking blijft `UNKNOWN` of
`STALE`.

Observeren muteert geen target, maar een geconfigureerde provider kan daarvoor
wel lokale of remote read-API's aanroepen. Controleer de plugindeclaraties en
privacyconfiguratie voordat je het commando tegen echte systemen gebruikt.

`status` toont de lokale store, plugins, targets, laatste snapshot, goals,
learning candidates, routines, autonomieprofielen en de geselecteerde executive
brain. De huidige CLI schrijft dit altijd als JSON; `--json` is geaccepteerd om
de gewenste outputvorm expliciet te maken.

## 4. Voer de publieke contracttests uit

Deze suites gebruiken alleen `unittest` en werken na de gelockte sync:

```console
uv run python -m unittest discover -s packages/engine-sdk/tests -v
uv run python -m unittest discover -s packages/engine-runtime/tests -v
```

Ze controleren onder andere manifestvalidatie, canonical hashing, de
gegenereerde plugin, CLI-opbouw, modelconfiguratie en setup-preview. Dit is
software- en contractbewijs, geen certificering van fysieke veiligheid.

## 5. Maak een lokale voorbeeldplugin

Kies een lege doelmap:

```console
uv run engine-plugin init mijn-wereld --template world --destination /tmp
cd /tmp/mijn-wereld
uv run --project /pad/naar/engine engine-plugin validate .
uv run --project /pad/naar/engine engine-plugin inspect .
uv run --project /pad/naar/engine engine-plugin test .
```

Vervang `/pad/naar/engine` door de absolute repositoryroot. Je kunt ook in een
shell vanuit de Engine-workspace blijven en het pluginpad als argument geven:

```console
uv run engine-plugin validate /tmp/mijn-wereld
uv run engine-plugin inspect /tmp/mijn-wereld
uv run engine-plugin test /tmp/mijn-wereld
```

De templates zijn `world`, `specialist` en `full`. `world` bevat een
warehousefake met provider, controller, executor en effectoracle; `specialist`
bevat alleen een specialist; `full` combineert beide.

## Geen model nodig voor de kern

Discovery, observatie, de deterministische executive en de contracttests hebben
geen LLM nodig. `engine setup` compileert vrije tekst naar een voorgestelde
`GoalSpecV2` en vereist in de huidige runtime wél een geconfigureerd structured-
outputmodel. Zonder model faalt dit commando expliciet.

Voor een OpenAI-compatibel endpoint:

```console
export ENGINE_MODEL_BASE_URL=https://provider.example/v1
export ENGINE_MODEL_API_KEY=...
export ENGINE_MODEL_ID=provider-model-id
uv run engine model canary
```

Een loopbackendpoint mag zonder API-key worden gebruikt via
`ENGINE_LOCAL_MODEL_BASE_URL` en `ENGINE_LOCAL_MODEL_ID`. Een remote URL zonder
key faalt gesloten. `model canary` doet een echte netwerkcall; voer het niet uit
als je geen externe transmissie bedoelt.

## Volgende stappen

- Lees de [plugininterface](./plugin-interface.md) voordat je rollen implementeert.
- Gebruik de [pluginchecklist](./plugin-checklist.md) vóór enrollment.
- Zie de [CLI-referentie](./cli.md) voor alle actuele subcommando's.
- Lees [status en bewijs](../reference/status-en-bewijs.md) voordat je een ACK of
  modeluitvoer als succes interpreteert.
