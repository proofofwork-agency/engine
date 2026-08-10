# Engine

> Een experimentele, local-first runtime die duurzame doelen omzet in getypeerde, controleerbare acties over software- en fysieke werelden.

Engine onderzoekt één centrale vraag: kan één levende runtime menselijke intentie, duurzame wereldstate, verwisselbare intelligentie en veilige uitvoering samenbrengen zonder een LLM tot state store, autoriteit of waarheidsbron te maken?

Engine bestaat uit een **Heart**, één actief **algemeen brein**, nul of meer **specialistische brains** en installeerbare **world plugins**. Het Heart houdt doelen en state levend. Brains kiezen of adviseren. Policy en autorisatie bepalen wat mag. Executors handelen. Een verse observatie en effect-oracle bepalen wat werkelijk gebeurde.

> **Status:** experimenteel. De v2-contracten, SDK, runtime, reference-world, contextplugin en een gesimuleerd Homey-pad zijn geïmplementeerd en getest. Dit is geen productieplatform, safety-certificering of bewijs van brede fysieke autonomie.

## Waarom Engine anders is

Veel agents kunnen tools aanroepen. Engine probeert een moeilijkere grens expliciet te maken:

```text
intentie
  → duurzaam GoalSpec
  → observeren
  → brain/specialist stelt effect voor
  → schema + preconditions
  → policy + risico
  → exacte autorisatie
  → dispatch
  → verse observatie
  → effect-oracle + duurzaam receipt
```

De kernregels zijn:

- modelcontext is niet de echte wereldstate;
- een voorstel is geen uitvoeringsrecht;
- een acknowledgement is geen bewezen effect;
- softwarepolicy vervangt geen fysieke safetylaag;
- deliberatieve AI hoort niet in een hard-realtime control-loop;
- state en ervaring zijn niet hetzelfde als modelweights.

## Heart en brains

```text
ENGINE
├── Heart
│   ├── doelen, snapshots en continuïteit
│   ├── contextprojectie en event-/poll-lus
│   ├── policy-, execution- en receiptcoördinatie
│   └── duurzame ervaring en reconstructie
├── één algemeen executive brain
│   ├── deterministisch, of
│   └── model-backed via strict structured output
├── nul of meer specialistische brains
└── world plugins
    ├── providers en capabilities
    ├── domain controllers en executors
    ├── effect-oracles
    └── optionele experience/routine providers
```

Het algemene brein kiest de volgende cognitieve stap. Een specialist levert begrensd, getypeerd advies. Geen van beide verleent autorisatie of verklaart zijn eigen actie succesvol.

Meerdere specialistische brains en meerdere plugins/targets zijn ondersteund. Meerdere gelijktijdige algemene brains, voting, swarms en automatische providerfailover zijn nog niet geïmplementeerd.

## Wat bestaat nu?

| Onderdeel | Status |
| --- | --- |
| Duurzame goals, snapshots, mandates, receipts en reconstructie | Geïmplementeerd en getest |
| `ACHIEVE`- en `MAINTAIN`-goals | Geïmplementeerd en getest |
| Deterministisch en OpenAI-compatible general-brain-slot | Geïmplementeerd; live model vereist eigen configuratie |
| Meerdere plugins, targets en specialists in één world snapshot | Geïmplementeerd en getest |
| `IMMEDIATE` lifecycle | Geïmplementeerd en getest in fakes |
| Durable `TASK` start/poll/cancel/restart | Geïmplementeerd in de reference-world |
| `STREAM` lifecycle | Contract/scaffolding; nog geen end-to-end reference proof |
| Begrensd preference- en routinelearning | Geïmplementeerd en getest; geen weight training |
| Homey | Live read-only observatie; mutaties alleen fake-getest |
| Fysieke safety, hard realtime en certificering | Buiten de huidige bewijsgrens |

De volledige, onderbouwde status staat in de [status- en bewijspagina](docs-site/docs/reference/status-en-bewijs.md).

## Snel starten

Vereisten:

- Python 3.12 of nieuwer;
- [`uv`](https://docs.astral.sh/uv/);
- Node.js 20 of nieuwer, alleen voor de documentatiesite.

Installeer alle workspacepackages:

```bash
uv sync --all-packages --locked
source .venv/bin/activate
```

Bekijk de drie meegeleverde plugins en observeer de samengestelde wereld:

```bash
engine plugins list
engine plugins inspect engine.reference-world
engine world observe
engine status --json
```

`engine world observe` kan pluginconfiguratie vereisen. Imports en pluginfactories horen inert te zijn; werkelijk netwerk-, database- of devicewerk begint pas bij gebruik van de provider.

Start de deterministische testsuite:

```bash
uv run --with pytest pytest -q
```

De lokale gate bij het opzetten van deze repository was: `131 passed, 2 skipped, 34 subtests passed`. De skips waren expliciet geconfigureerde live-modelcanaries; core correctness vereist geen live model.

## Een plugin maken

De publieke plugininterface zit in `engine-sdk` en is onafhankelijk van de runtime:

```bash
source .venv/bin/activate

engine-plugin init my-world --template full
engine-plugin validate my-world
engine-plugin inspect my-world
engine-plugin test my-world

uv pip install --python .venv/bin/python -e my-world
engine plugins list
```

Templates:

- `world`: provider, controller, executor, oracle en experience provider;
- `specialist`: alleen een begrensde specialistische brain;
- `full`: world plus specialist.

Een v2-plugin levert een statisch `engine-plugin.toml` en een Python-entrypoint in de groep `engine.plugins`. Dynamisch ontdekte maar niet gedeclareerde capabilities worden opaque/read-only; Engine vertrouwt ze niet automatisch voor mutatie.

Lees verder in [Plugin-interface](docs-site/docs/developers/plugin-interface.md), [SDK](docs-site/docs/developers/sdk.md) en [Pluginchecklist](docs-site/docs/developers/plugin-checklist.md).

## CLI in één oogopslag

```text
engine plugins list|inspect
engine world observe
engine setup [--activate]
engine run
engine status [--json]
engine learning status|correct|rollback
engine routines list|inspect|approve|reject|rollback
engine yolo enable|status|disable
engine model canary
```

`engine setup` is standaard een preview. Alleen `--activate` schrijft een goal en standing mandate. `engine model canary` doet een echte netwerkcall wanneer een provider is geconfigureerd.

## Documentatie lokaal draaien

De volledige Nederlandstalige documentatie staat in `docs-site/`:

```bash
cd docs-site
npm ci
npm run start
```

Een productiebuild maak je met:

```bash
npm run build
```

De site behandelt onder meer:

- [wat Engine is](docs-site/docs/concepts/wat-is-engine.md) en [niet is](docs-site/docs/concepts/wat-engine-niet-is.md);
- [Heart en brains](docs-site/docs/concepts/heart-en-brains.md);
- [alle modi](docs-site/docs/concepts/modi.md);
- [hoe Engine wel en niet leert](docs-site/docs/concepts/leren.md);
- [plugininterface, SDK en CLI](docs-site/docs/developers/plugin-interface.md);
- [eerlijke vergelijking met andere projecten](docs-site/docs/reference/vergelijking.md);
- [einddoel en bewijsgrenzen](docs-site/docs/concepts/einddoel.md).

## Repository-indeling

```text
src/engine/               Heart, world store, brains, policy en learning
packages/engine-sdk/      Publieke plugincontracten en engine-plugin CLI
packages/engine-runtime/  Composition root, discovery, lease en engine CLI
plugins/                  Reference-world, context en Homey plugins
tests/                    Kern-, lifecycle-, reconstructie- en faulttests
docs/adr/                 Architecture Decision Records
docs-site/                Docusaurus-documentatiesite
artifacts/                Experimentele protocollen en geselecteerd bewijs
```

## Wat Engine nadrukkelijk niet claimt

- Geen universele autonome agent die ieder apparaat kan besturen.
- Geen vervanging voor Home Assistant, openHAB, ROS 2, targetdrivers of safetyhardware.
- Geen hard-realtime control-loop.
- Geen fysiek veiligheidscertificaat op basis van simulaties.
- Geen zelftrainend model, online weight updates of zelfschrijvend skill-OS.
- Geen bewijs dat meerdere algemene brains beter zijn; die compositie bestaat nog niet.
- Geen publiek pluginmarketplace, cryptografische signing of afgedwongen pluginsandbox.

## Bijdragen

Lees eerst [AGENTS.md](AGENTS.md), [RULES.md](RULES.md) en [GOAL.md](GOAL.md). Niet-triviale wijzigingen moeten de relevante invarianten, contracten, tests en fysieke/externe effecten vooraf benoemen. Verplaats nooit een safety-, oracle- of acceptatiegrens om een uitkomst te laten slagen.

De korte checksum:

```text
LLM proposal != authority
prediction != observation
policy != physical safety
deliberation != realtime control
simulation evidence != real-world certification
state != weights
imagine != execute
```
