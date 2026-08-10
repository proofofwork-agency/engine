---
title: Pluginchecklist
description: Enrollment- en reviewchecklist voor een engine.plugin/v2-plugin.
sidebar_position: 6
---

# Pluginchecklist

Gebruik deze checklist vóór je een plugin laat observeren of muteren. Een vinkje
betekent dat er code én passend bewijs is; een manifestclaim alleen is niet
genoeg.

## Identiteit en packaging

- [ ] `plugin.id` is stabiel, dotted, lowercase en niet afgeleid van vrije tekst.
- [ ] `version`, `engine_api` en `contract_version = "engine.plugin/v2"` zijn gezet.
- [ ] `pyproject.toml` declareert exact één passende `engine.plugins`-entrypoint.
- [ ] `engine-plugin.toml` zit in wheel en editable install.
- [ ] Import en factory zijn inert: geen netwerk, mutatie of background thread.
- [ ] Statisch manifest en `plugin.manifest` zijn exact gelijk waar de runtime dat eist.
- [ ] Target- en entity-ID's zijn canoniek en stabiel over restart.
- [ ] De pluginstore heeft eigen `identity` en positieve `schema_version`.

## Behoeften en secrets

- [ ] Netwerk-, filesystem-, secret- en privacybehoeften zijn minimaal gedeclareerd.
- [ ] Geen secret verschijnt in manifest, observatie, receipt, log of modelcontext.
- [ ] Externe transmissie van private data vereist expliciete opt-in.
- [ ] De plugin werkt fail-closed als credentials of consent ontbreken.
- [ ] Je deployment legt aanvullende OS/containerisolatie vast.

De huidige Engine-runtime dwingt `[needs]` nog niet af met een algemene sandbox
en verifieert geen cryptografische artefactsignatures. Zet die open gaps niet als
afgeronde beveiligingscontrols in je pluginreadme.

## Wereldobservatie

- [ ] `WorldProvider` declareert poll- en freshnessintervallen.
- [ ] Targetrevisions zijn monotoon en survive/reconstrueren na restart waar nodig.
- [ ] Entities, relations en observations verwijzen alleen naar geldige stabiele ID's.
- [ ] Elke observation heeft bron, tijd, evidence grade, unit waar relevant en dekking.
- [ ] `quality` en `confidence` blijven apart van evidence grade.
- [ ] Ontbrekende data wordt `UNKNOWN`/onbeschikbaar, niet automatisch `false`.
- [ ] Stale data wordt als `STALE` behandeld voor muterende beslissingen.
- [ ] Providerfouten behouden de laatst bekende state plus expliciete failure/staleness.
- [ ] Een event plant een wake; een verse observation blijft authoritative.

## Capabilities

- [ ] Iedere family heeft stable ID, versie en beschrijving.
- [ ] `input_schema` beschrijft het concrete request; `effect_schema` het semantische voorstel.
- [ ] `control_layer`, `invocation_mode`, risk en privacy zijn expliciet.
- [ ] Units, preconditions, deadlines, limieten en recovery zijn expliciet.
- [ ] Idempotency is eerlijk: `false` als herhalen een effect kan dupliceren.
- [ ] `effect_measurements` noemen de observaties die succes kunnen dragen.
- [ ] Dynamisch onbekende families blijven opaque/read-only.

## Mutatiepad

- [ ] Iedere muterende plugin declareert provider, controller, executor en oracle.
- [ ] De controller kan target, entity, goal of capability niet verwisselen.
- [ ] Het request bindt actuele snapshot-, world- en targetrevision.
- [ ] Parameters passeren JSON Schema en capabilitylimieten.
- [ ] Preconditions falen gesloten bij `UNKNOWN`, `STALE` of conflict.
- [ ] De executor controleert request-gebonden authorization.
- [ ] Authorization heeft exacte scope en korte expiry.
- [ ] Lost ACK, timeout, duplicate ACK en partial execution zijn getest.
- [ ] Receiptstates zijn expliciet; ambiguïteit wordt `unknown`.
- [ ] De oracle gebruikt prestate, receipt én verse poststate.
- [ ] ACK-only kan nooit `achieved = true` opleveren.
- [ ] Recovery- of safe-state-succes wordt opnieuw geobserveerd.

## `immediate`, `task` en `stream`

- [ ] `immediate`: terminale receipt en post-observation zijn getest.
- [ ] `task`: durable external handle, poll, deadline cancel en restart recovery zijn getest.
- [ ] `stream`: cursor, reconnect, deduplicatie, deadline en restart zijn end-to-end getest.

Engine heeft nu een referenceproof voor `task`. Voor `stream` bestaat contract- en
storescaffolding, maar nog geen algemene end-to-end referentie. Claim geen
streamproductierijpheid op basis van het enum alleen.

## Brains

- [ ] Specialist-ID en `supported_families` zijn stabiel en gedeclareerd.
- [ ] Advies is typed en kan unsupported/defer uitdrukken.
- [ ] Een specialist retourneert alleen advies/proposal en bezit geen executor.
- [ ] Modeloutput wordt als onbetrouwbare data geschema-valideerd.
- [ ] Provider/model-ID, projectiehash, latency en output worden auditable vastgelegd.
- [ ] Core correctness en de veilige fallback werken zonder modelprovider.

## Experience en routines

- [ ] Experience is optioneel; afwezigheid breekt de gewone lifecycle niet.
- [ ] De provider gebruikt een opaque cursor en duplicate-vrije signal-ID's.
- [ ] Preferences zijn onder `<plugin-id>.preference.*` namespaced.
- [ ] Preferencewaarden hebben een JSON Schema en capabilitybinding.
- [ ] Signals bevatten provenance en blijven `OBSERVED` of `INFERRED` zoals terecht.
- [ ] Een signal kan geen mandate, target, family, risk of privacy uitbreiden.
- [ ] Routine templates hebben pattern-, guard- en goalschema plus vaste priority.
- [ ] Iedere scoped guardleaf heeft een exacte entityselector.
- [ ] Shadow dispatch count is structureel nul.
- [ ] Promotie gebruikt echte kansen, independently observed agreement en conflictchecks.
- [ ] Automatische promotie vereist exacte low-risk ownerdelegatie; anders approval.
- [ ] Iedere promotie heeft een exacte rollbackpatch en invalidateert verouderde plancache.

## Tests

- [ ] `engine-plugin validate .` slaagt.
- [ ] `engine-plugin inspect .` toont alleen bedoelde declarations.
- [ ] `engine-plugin test .` slaagt met de gegenereerde/gedeelde contracttest.
- [ ] Deterministische fake dekt observe, controller, executor en oracle.
- [ ] Conformance draait tegen iedere adapterimplementatie.
- [ ] Restart/replay levert dezelfde relevante state op.
- [ ] Stateful tests dekken ongeldige volgordes en crashgrenzen.
- [ ] Faulttests dekken netwerkverlies, timeout, duplicate response en partial failure.
- [ ] Geen test gebruikt sealed evaluatiedata als debugfixture.
- [ ] Fysieke tests beginnen low-energy, begrensd en met onafhankelijke stopmogelijkheid.

## Documentatie en claims

- [ ] README noemt ondersteunde targets/versies en exacte units.
- [ ] README noemt failure-, fallback- en recoverygedrag.
- [ ] Simulatorbewijs wordt niet als fysieke veiligheid of certificering gepresenteerd.
- [ ] Niet-geïmplementeerde marketplace, signing, sandboxing of stream-E2E staat als gap.
- [ ] Pluginsemantiek lekt niet als speciale branch naar Heart of runtime.
- [ ] Een wijziging aan lifecycle, authority of adaptercontract heeft de vereiste ADR.

