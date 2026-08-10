# Überplugin research — wat laat Engine onmiddellijk begrijpen?

> Besluitnotitie, 2026-08-10. Dit positioneert het owner-concept; het herschrijft
> Engine niet en autoriseert geen fysieke uitrol.

## Besluit

**Flagship: Engine HomeOps — missions, not commands.**

De eerste verkoopbare demonstratie moet niet zijn dat Engine één transactie
afmaakt en na een geforceerde crash verdergaat. Hij moet tonen dat Engine leeft:

> “Houd mijn werkplek tussen 350 en 450 lux, onder 25 watt, en verander niets in
> de hal.”

Engine observeert Home Assistant, gebruikt een licht/energie-specialist, bedient
alleen expliciet gewhiteliste lampen en controleert via lux- en vermogensmetingen
of het doel werkelijk waar is. Een geaccepteerd lampcommando zonder gemeten licht
is geen succes. Als iemand een lamp afdekt of uitschakelt, wordt Heart door een
event wakker, observeert opnieuw en herstelt. Wanneer alles stabiel is blijft
Heart monitoren zonder het LLM te blijven aanroepen.

Restart mag één korte fault-injection in een technische verdieping blijven, maar
is niet de hoofdhandeling. De hoofdhandeling is **blijven leven**.

## Wat zeven researchlanes opleverden

| Lane | Sterkste kandidaat | Belangrijkste les |
| --- | --- | --- |
| concept/threat | echte software/ops-wereld | vecht niet op chat/skills alleen |
| cognition | LifeOps/AppWorld | specialistische breinen moeten meetbaar iets toevoegen |
| browser/desktop | Verified Dossier | zeer leesbaar, maar browserstack is al druk en flaky |
| embodied/devices | HomeOps | maintained state + sensoren maakt Heart zichtbaar |
| technische haalbaarheid | Verified App Doctor | snelste sterke apart installeerbare contracttest |
| wetenschappelijke evaluatie | LifeOps/AppWorld | beste onafhankelijke state/collateral-damage oracles |
| launch/distributie | HomeOps | duidelijke community en een niet-chat positionering |

De synthese is daarom geen compromisproduct:

- **HomeOps verkoopt het concept.**
- **AppWorld/LifeOps meet generalisatie.**
- **App Doctor is de technische fallback** als Home Assistant packaging/config
  de eerste twee weken blokkeert.

## Waarom Order Desk niet de überplugin is

De GLM-propositie—een lokale shop-API met 409, oracle en crash-resume—is een
goede conformancefixture. Zij test HTTP, partial failure, reconstructie en
oracle-only completion goedkoop.

Maar als flagship heeft zij een categoriefout: het verhaal is nog steeds een
eindige workflow. OpenClaw, Hermes, Temporal, LangGraph of een zorgvuldig script
kunnen de zichtbare stappen en restart grotendeels nabouwen. De Engine-eigenschap
die zij niet vanzelf centraal zetten is juist dat een doel als gewenste toestand
blijft leven en de wereld, niet de sessie, bepaalt wanneer opnieuw denken nodig
is.

Order Desk blijft dus nuttig als **adaptertest**, niet als productidentiteit.

## De vijfminutendemo

1. De gebruiker activeert één onderhouden doel voor licht, vermogen en een
   `must_not_change`-zone.
2. Heart observeert Home Assistant en projecteert alleen relevante capabilities.
3. Het algemene brein kiest de licht/energie-specialist; Heart voert de gekozen
   capability uit en boekt receipt plus post-state.
4. Home Assistant accepteert lamp A, maar de luxsensor blijft te laag. Engine
   weigert succes, kiest een alternatief en bereikt de band binnen het wattbudget.
5. De interface toont `MONITORING`; enkele stabiele events veroorzaken **nul
   nieuwe modelcalls**.
6. Iemand dekt lamp A af of zet haar extern uit. WebSocket-event wekt Heart;
   Heart observeert (het event zelf is geen waarheid), detecteert drift en
   herstelt via lamp B.
7. Alleen de sensoren plus collateral-change-oracle maken het doel weer groen.

Optionele appendix: kill de Engine-container tijdens één actie, herstart en toon
reconciliatie. Dat bewijst herstelbaarheid, maar Engine hoeft niet te sterven om
interessant te zijn.

## Kleinste eerlijke scope

- Eén Home Assistant-target als composiete wereld; huidige single-target goals
  zijn daarmee geen blocker.
- Alleen `light.turn_on/off`, brightness en `switch.turn_on/off`.
- Lux en wattage read-only; expliciete units, timestamps en availability.
- Entity-whitelist; geen sloten, deuren, camera's, klimaat of willekeurige
  services.
- Lokale HA-demo-entiteiten of een low-risk lamp/plug-rig; simulatie is geen
  fysiek bewijs.
- Deterministische licht/energie-specialist plus hetzelfde algemene brain-slot.
- Eventsubscription met polling fallback. Event wekt alleen; `observe()` blijft
  waarheid.
- Model-onafhankelijke oracle met korte stabilisatieperiode en
  `must_not_change`-controle.
- Apart installeerbaar `engine.plugins`-pakket; geen Home Assistant-branch in
  `Heart`.

## Go/no-go

**Go** voor de flagshipvideo wanneer:

- 5/5 demo-runs het doel halen na de geinjecteerde no-effect verstoring;
- stabiele monitoring geen brain requests produceert;
- eventverlies door polling wordt hersteld;
- commando-ACK zonder sensor-effect nooit completion geeft;
- alle mutaties receipts en post-observaties hebben;
- collateral state in de hal 5/5 onveranderd blijft;
- plugininstallatie geen corebranch vereist.

**No-go** wanneer de demo neerkomt op vaste Home Assistant-automations met een
LLM-label, events als waarheid gebruikt, echte risicovolle apparaten ontsluit,
of restart opnieuw het volledige verkoopverhaal wordt.

## Onderzoeks- en marktpad

1. HomeOps bounded flagship op demo/low-risk entities.
2. LifeOps/AppWorld als gecontroleerde benchmark met officiële state-based
   evaluatie en collateral-damage checks.
3. App Doctor als software/ops-variant en robuuste installable-plugin
   conformancecase.
4. Pas daarna browser, multi-target en echte deviceklassen wanneer ActionRequest,
   TASK/STREAM, config/reconnect en pluginconformance bestaan.

Relevante primaire bronnen uit de research:

- [Home Assistant Apps](https://developers.home-assistant.io/docs/apps)
- [Home Assistant WebSocket API](https://developers.home-assistant.io/docs/api/websocket/)
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/)
- [AppWorld paper](https://aclanthology.org/2024.acl-long.850/)
- [AppWorld repository](https://github.com/StonyBrookNLP/appworld)
