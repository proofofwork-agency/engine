# engine-runtime

Pluginneutrale composition root en productie-CLI voor Engine v2.

```console
engine plugins list
engine plugins inspect engine.reference-world
engine world observe
engine setup --plugin engine.reference-world \
  --target warehouse --entity warehouse:bin:a \
  --capability warehouse.inventory.reserve \
  --learning engine.reference-world.preference.reserve-target-band/v1 \
  --intent "Houd voldoende voorraad beschikbaar"
engine run
engine status --json
engine learning status
engine routines list
engine routines inspect <candidate-or-routine-id>
engine routines approve <candidate-id>
engine routines reject <candidate-id>
engine routines rollback <routine-id>
engine yolo enable --entity homey:home:zone:study
engine yolo status
engine yolo disable
```

`engine setup` is standaard een preview. Alleen `--activate` schrijft het doel
en mandaat. De CLI leest capabilities en preferences uit het statische
pluginmanifest en bevat geen Homey- of warehousevelden. De afzonderlijke
`yolo`-enrollment is in de eerste release bewust Homey-lighting-specifiek: hij
bevriest exacte zone-IDs en de drie statisch gedeclareerde templates. Zonder
expliciete `yolo enable` eindigt een bewezen routine bij `ready_for_approval`.

## General model as brain

De runner gebruikt zonder model een deterministische executive. Een
OpenAI-compatibele provider met strict JSON-schema output kan zowel natuurlijke
intentie naar een voorgestelde `GoalSpec` vertalen als bij novelty, conflict of
ambiguïteit als general brain optreden:

```console
export ENGINE_MODEL_BASE_URL=https://provider.example/v1
export ENGINE_MODEL_API_KEY=...
export ENGINE_MODEL_ID=provider-model-id
engine model canary
```

Voor Meta Model API worden ook `META_MODEL_API_BASE_URL`,
`META_MODEL_API_KEY` en `META_MODEL_ID` gelezen. Modeloutput blijft onbetrouwbare
input: Engine valideert het schema, policy verleent authority, en alleen een
verse pluginobservatie/oracle mag effect bevestigen.

`engine model canary` doet een echte netwerkcall. De tests gebruiken standaard
een lokale HTTP-fixture; een live Meta-canary draait alleen wanneer de drie
`META_MODEL_*` variabelen expliciet zijn gezet.

### Kleine lokale Gemma

Gemma 3 4B IT Q4_K_M is de aanbevolen kleine lokale allrounder voor zowel de
general-brainroute als GoalSpec-compilatie:

```console
llama-server -hf ggml-org/gemma-3-4b-it-GGUF:Q4_K_M --jinja \
  --host 127.0.0.1 --port 18081 --alias local-gemma-4b \
  -c 8192 -np 1 -ngl 99
export ENGINE_LOCAL_MODEL_BASE_URL=http://127.0.0.1:18081/v1
export ENGINE_LOCAL_MODEL_ID=local-gemma-4b
engine model canary
```

Op de geteste M3 Pro duurden een echte Heart-braincall en een Nederlandse
warehouse-GoalSpec beide ongeveer 8–10 seconden. Gemma 3 1B Q4_K_M deed de
braincall in ongeveer twee seconden, maar vertaalde zelfs een eenvoudige
minimum-intentie niet betrouwbaar naar de juiste GoalSpec-waarde. Gebruik 1B
daarom alleen als snelle schema-router, niet als vrije intentcompiler. Dit zijn
lokale smoke-testmetingen, geen algemene modelbenchmark.

Een API-key is alleen optioneel voor `localhost` en numerieke loopback-adressen.
Remote model-URLs blijven fail-closed zonder key. Engine start of downloadt het
model niet stilzwijgend; weights en serverproces blijven expliciet lokaal beheer.
