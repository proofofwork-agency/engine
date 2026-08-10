# Engine — plan voor een bestuurbare wereld-runtime

> Status: producthypothese / preflight. De additieve World Plugin v2 verticale
> slice is inmiddels geïmplementeerd, fake-world getest en live read-only tegen
> een samengestelde Homey+contextwereld geobserveerd; zie
> `WORLD_PLUGIN_V2.md`. Overige fasen en fysieke claims in dit document blijven
> preflight en zijn niet als gemeten resultaat te lezen.

## 1. Korte definitie

Engine is een lokale, capability-gebaseerde runtime die menselijke intentie omzet in begrensde, controleerbare handelingen op software en fysieke systemen.

Engine laat een LLM doelen interpreteren en acties voorstellen, maar laat het model nooit zelfstandig bepalen wat waar is, welke bevoegdheden het heeft, of hoe een realtime actuator wordt aangestuurd. De runtime valideert elk voorstel tegen actuele waarnemingen, getypeerde capabilities, policy, risico en autorisatie. De echte uitvoerder en onafhankelijke safety-laag blijven de autoriteit.

De beoogde keten is:

```text
menselijk doel
  -> intentieparser / LLM (optioneel voorstel)
  -> GoalSpec
  -> actuele WorldSnapshot + CapabilityGraph
  -> kandidaat-acties / skillselectie
  -> schema-, policy-, risico- en autorisatiegates
  -> uitvoerder / adapter
  -> apparaat of softwarewereld
  -> waarneming + ExecutionReceipt + EffectDelta
  -> nieuwe WorldSnapshot
```

De kernbelofte is niet “AI bestuurt alles”, maar:

> Eén veilige en auditeerbare besturingslaag kan uiteenlopende systemen via expliciete capabilities bedienen, zonder dat LLM-context, een leverancier of een verborgen agentloop de bron van waarheid wordt.

## 2. Producthypothese

Engine is waardevol wanneer dezelfde runtime voor verschillende werelden deze algemene functies levert:

- capability-ontdekking en getypeerde actiecontracten;
- actuele toestand met provenance en onzekerheid;
- toestemming, policy, limieten en onafhankelijke stops;
- dry-run/simulatie waar mogelijk;
- uitvoering met idempotency, time-outs en herstel;
- audit, replay en vergelijking tussen verwacht en werkelijk effect;
- verwisselbare LLM-, algoritme- en specialistische modelproviders;
- lokale/edge-uitvoering wanneer latency, privacy of netwerkuitval dat vereist.

De hypothese is weerlegd of moet worden versmald wanneer apparaatverschillen zoveel speciale logica vereisen dat alleen een dunne gemeenschappelijke logginglaag overblijft, of wanneer bestaande domeinruntimes plus kleine integraties structureel eenvoudiger en veiliger zijn.

## 3. Wat Engine nadrukkelijk niet is

Engine 0.x is niet:

- een LLM dat direct PWM-, motor-, stuur- of vluchtcommando's genereert;
- een vervanging van PLC's, flight controllers, motorcontrollers, ROS-control of automotive ECU's;
- een universeel foundation model voor iedere machine;
- een chatgeschiedenis die zich als operationele toestand voordoet;
- een onbeperkte recursive-agentloop;
- een marketplace voor ongeteste scripts;
- een veiligheidscertificering;
- een claim dat één skill zonder domeinbewijs overdraagbaar is naar alle apparaten.

## 4. Architectuurgrenzen

### 4.1 Deliberatieve control plane

De control plane werkt op menselijke tijdschalen. Hij beheert:

- doelen en constraints;
- WorldSnapshots en observaties;
- CapabilityGraph en SkillManifests;
- kandidaat-acties en bounded workflows;
- policy-, risico- en autorisatiebesluiten;
- audit, replay en evaluatie;
- optionele LLM-cognitie;
- optionele Umwelt-dynamics en planning.

Deze laag mag stoppen, uitstellen en opnieuw waarnemen. Hij mag geen hard-realtime garanties veinzen.

### 4.2 Device/data plane

De device/data plane beheert:

- adapters en protocollen;
- commandovertaling;
- telemetrie en heartbeats;
- deadlines, retries en idempotency;
- lokale feedbackcontrollers;
- toestand van de verbinding;
- gecontroleerd afbreken en herstel.

Adapters voeren alleen reeds toegestane acties uit. Zij kiezen geen productstrategie.

### 4.3 Onafhankelijke safety plane

Voor fysieke systemen is safety geen prompt en geen modeloutput. De safety plane moet onafhankelijk kunnen weigeren of stoppen op basis van onder meer:

- fysieke en softwarematige noodstop;
- workspace-, snelheid-, kracht-, hoogte- en geofence-limieten;
- watchdog en heartbeat;
- maximumduur en energie-/resourcebudget;
- mens- of obstakeldetectie wanneer vereist;
- fail-closed gedrag bij ontbrekende of conflicterende toestand;
- apparaat-specifieke interlocks.

Een hogere laag kan een safety-regel nooit overrulen zonder een expliciet, geaudit autorisatiepad dat buiten het model ligt.

## 5. Canonieke contracten voor de eerste versie

De eerste implementatie hoort kleine, provider-onafhankelijke typen te bevriezen:

- `WorldSnapshot`: onveranderlijke, versieerbare toestand aan een waarnemingsgrens;
- `Observation`: getypeerd bewijs met bron, tijd, kwaliteit en dekking;
- `Capability`: actie die een target onder voorwaarden aanbiedt;
- `CapabilityGraph`: targets, capabilities, afhankelijkheden en huidige beschikbaarheid;
- `GoalSpec`: gewenst resultaat, constraints, budget en stopvoorwaarden;
- `ProposedAction`: onbetrouwbaar voorstel zonder uitvoeringsrecht;
- `ActionRequest`: volledig getypeerde concrete actie tegen een snapshot;
- `PolicyDecision`: allow, deny, require-approval of defer met redenen;
- `Authorization`: kortlevend bewijs voor exact doel, actie, target en grenzen;
- `ExecutionReceipt`: wat werkelijk is aangevraagd, gestart, gestopt en waargenomen;
- `EffectDelta`: waargenomen of voorspelde toestandverandering;
- `SkillManifest`: versie, invoer/uitvoer, targetscope, safety-envelope en evaluatiebewijs;
- `AdapterManifest`: protocol, capabilities, versie, simulator en conformance-status.

Identiteiten mogen niet afhangen van embeddings of beschrijvende modeltekst. Iedere muterende actie bindt aan een actuele snapshot of expliciete preconditions; stale acties worden geweigerd of opnieuw gevalideerd.

## 6. Skills en mini-brains

Een skill is een begrensde uitvoeringsstrategie voor één capability. Mogelijke implementaties:

- deterministische controller;
- klassiek plannings- of optimalisatiealgoritme;
- bestaand apparaat-SDK;
- extern model;
- klein lokaal neuraal netwerk (“mini-brain”);
- samengestelde, maar begrensde workflow.

Een mini-brain is dus geen algemene geest en geen tweede bron van waarheid. Het is een specialistisch skillpakket met minimaal:

- exact input- en outputschema;
- ondersteunde hardware en quantisatieformaat;
- trainingsdata- en licentieprovenance;
- dataset-, code-, config- en checkpointhashes;
- latency-, geheugen- en energieprofiel;
- confidence/uncertainty of expliciete ondersteunde scope;
- safety-envelope en fallback;
- deterministische of eenvoudige baseline;
- simulator-, replay- en hardware-evaluatie;
- rollbackbare versie en ondertekend artifact.

Mini-brains komen pas op het kritieke pad als een preregistreerde proef laat zien dat ze een eenvoudige controller of bestaand model aantoonbaar verbeteren onder hetzelfde budget. Training gebeurt standaard off-device; het edge-apparaat voert inference uit. Online updates zijn een latere, afzonderlijke hypothese.

## 7. Relatie met Umwelt

Engine en Umwelt hebben overlappende concepten, maar verschillende verantwoordelijkheden.

| Onderwerp | Engine | Umwelt |
| --- | --- | --- |
| Hoofdtaak | veilig capabilities uitvoeren op heterogene systemen | een wereld betrouwbaar representeren, dynamics leren en kort plannen |
| Autoriteit | policy, autorisatie, executor en echte observaties | duurzame WorldState en echte reconstructie/uitvoering |
| LLM-rol | intentie en kandidaat-acties voorstellen | contextprojecties, hypothesen en codevoorstellen |
| Realtime control | delegeert naar gevalideerde devicecontrollers | buiten de huidige softwarewereld-scope |
| Learned component | optionele specialistische skills/mini-brains | optionele representatie, action-conditioned dynamics en planning |
| Productgrens | adapters, permissions, operations, safety en edge | world-model- en onderzoeksprimitieven |

De gewenste integratie is een versieerbare poort, geen gedeelde database en geen broncodeverstrengeling:

```text
Engine Runtime
  -> WorldModelPort
       -> DeterministicWorldModel (standaard, voldoende voor Engine 0.1)
       -> UmweltAdapter (optioneel, wanneer Umwelt-gates zijn gehaald)
```

Engine mag dus zonder Umwelt werken. Umwelt kan later drie functies leveren:

1. rijkere reconstructie en query van actuele wereldtoestand;
2. voorspelde `EffectDelta + uncertainty + defer` voor voorgestelde acties;
3. bounded kandidaat-evaluatie of korte planning.

Engine blijft verantwoordelijk voor capability-contracten, permissions, safety, uitvoering en audit. Umwelt mag nooit rechtstreeks een actuator autoriseren. Omgekeerd mag Engine geen brede claims over geleerde dynamics overnemen voordat Umwelt die onder zijn eigen protocol heeft gemeten.

Een software-repository kan de eerste veilige Engine-wereld zijn: acties zijn goedkoop te sandboxen en meestal rollbackbaar. Een gesimuleerde en daarna fysieke tafelrobot bewijst vervolgens dat dezelfde runtimegrenzen ook buiten software standhouden. Dat maakt de relatie praktisch zonder de Umwelt 0.1-scope open te breken.

## 8. Kleinste falsifieerbare implementatieslice

De eerste slice bewijst niet “alles bestuurbaar”. Hij toetst vijf smallere claims:

1. één runtime kan twee verschillende adapters via hetzelfde capability-, policy- en receiptcontract bedienen;
2. een LLM kan volledig worden vervangen door vooraf vastgelegde voorstellen zonder kernfunctionaliteit te verliezen;
3. replay van observaties reconstrueert dezelfde canonieke toestand;
4. ongeautoriseerde, stale, slecht getypeerde en buiten-envelope acties worden vóór uitvoering geweigerd;
5. werkelijk effect wordt onafhankelijk waargenomen en nooit uit modeltekst afgeleid.

### Referentiewerelden

- `sandbox-filesystem`: geïsoleerde tijdelijke workspace met read/write/move/rollback-capabilities;
- `sim-arm`: deterministische tafelrobot-simulator met observe/move/grasp/release/stop;
- pas na passage: één fysieke arm achter een lokale adapter op een Raspberry Pi of vergelijkbaar edge-apparaat.

De twee eerste adapters moeten dezelfde runtimeketen gebruiken, maar hoeven geen kunstmatig identieke domeinacties te hebben. Generiek zijn de lifecycle, contracts, policy en audit; semantiek blijft domeinspecifiek.

## 9. Voorgestelde 0.1-acceptatiegates

Deze gates zijn release-blockers in het concept, maar krijgen pas de status `SEALED` na P0-review. Voor de eerste beslissende run worden exacte fixtures, seeds, time-outs en hardwaremanifesten vastgelegd. Minimaal gelden:

- **Contract:** 100% van de geldige conformance-fixtures geeft dezelfde canonieke serialisatie; alle ongeldige fixtures worden met de verwachte foutcode geweigerd.
- **Reconstructie:** event replay en full snapshot materialization zijn canoniek equivalent op alle controlled fixtures.
- **Isolatie:** geen state, authorization, cache of receipt lekt tussen twee gelijktijdige target-sessies.
- **Authority:** nul mutaties zonder geldige, target- en actiegebonden authorization.
- **Staleness:** iedere muterende actie tegen een achterhaalde snapshot wordt geweigerd of expliciet opnieuw gevalideerd.
- **Safety:** iedere geïnjecteerde envelope-overtreding wordt vóór device-uitvoering geweigerd; simulator-stop blijft binnen een vooraf bepaalde deadline.
- **Observation:** ieder succesvol muterend receipt heeft onafhankelijk waargenomen post-state of eindigt expliciet `UNKNOWN/INCONCLUSIVE`.
- **LLM-vervangbaarheid:** dezelfde vooraf vastgelegde `ProposedAction` levert provider-onafhankelijk hetzelfde policy- en executionresultaat.
- **Failure recovery:** procesherstart tussen dispatch en receipt leidt tot precies één aantoonbare eindstatus; nooit stille dubbele uitvoering.
- **Audit:** iedere beslissing is terug te leiden tot snapshot, proposal, policyversie, authorization, adapterversie en observatiebewijs.

Exacte numerieke latencygrenzen voor echte hardware worden niet gegokt; ze worden in de P0-preflight per target en risicoklasse vastgesteld. “Nul ongeautoriseerde acties” en “geen verzonnen observatie” zijn wel direct release-blocking.

## 10. Teststrategie

Vier testlagen zijn verplicht:

### Unit

- canonieke serialisatie en hashing;
- schema- en preconditionvalidatie;
- policybesluiten;
- authorization-scope en expiry;
- state reducer;
- idempotency en foutmapping.

### Contract en conformance

- alle adapters draaien dezelfde black-box suite;
- alle skills draaien manifest- en safety-envelope-tests;
- provider-adapters mogen geen SDK-typen in core-contracten lekken;
- foutcodes en receipt-lifecycle zijn stabiel.

### Reconstruction en stateful testing

- willekeurige geldige actiereeksen vergelijken incremental/replay met full materialization;
- shrinking moet de kleinste afwijkende reeks opleveren;
- crashpoints worden tussen alle lifecycle-overgangen geïnjecteerd;
- twee onafhankelijke stores/workspaces bewijzen isolatie;
- caches blijven uit het correctness-pad totdat een apart cachecontract bestaat.

### Safety en hardware-in-the-loop

- simulator fault injection voor timeout, disconnect, delayed telemetry en partial failure;
- fysieke tests beginnen met lage energie, beperkte workspace en menselijke noodstop;
- elk target heeft een expliciete safe state;
- softwarematige stop wordt nooit als vervanging voor een noodzakelijke fysieke interlock beschouwd;
- hardwaretestresultaten zijn target-specifiek en worden niet automatisch gegeneraliseerd.

LLM-output wordt in tests alleen als onbetrouwbare fixture gebruikt. Een model beoordeelt nooit zijn eigen succes wanneer een schema, simulator, sensor of uitvoeringsresultaat beschikbaar is.

## 11. Fasen en realistische volgorde voor één implementer

### P0 — Contract- en risico-preflight (1–2 weken)

- use-case en risicoklasse begrenzen;
- contracts, lifecycle en fouttaxonomie bevriezen;
- threat model en authorizationmodel schrijven;
- simulatororacle en conformancefixtures definiëren;
- gates preregistreren;
- ADR's voor state identity, receipt semantics en safety boundary.

Exit: geen productcode op basis van onbesliste authority- of safety-semantiek.

### P1 — Deterministische core + sandbox-filesystem (2–3 weken)

- in-memory/duurzame event store met immutable snapshots;
- capability registry;
- policy- en authorizationpad;
- executor met idempotency en receipts;
- filesystemadapter in een strikt geïsoleerde temp-workspace;
- unit-, contract-, reconstruction- en crash-tests.

Exit: core-gates zonder LLM en zonder hardware passeren.

### P2 — Sim-arm en bounded intentie (2–3 weken)

- deterministische arm-simulator en adapter;
- device telemetry, watchdog en stop;
- bounded workflow van GoalSpec naar ProposedActions;
- één optionele LLM-provider achter exact hetzelfde voorstelcontract;
- provider-offline en malformed-output-tests.

Exit: twee heterogene adapters passeren conformance, isolation, authority en replay.

### P3 — Fysieke edge-pilot (2–4 weken)

- één goedkope tafelarm;
- lokale adapter op Pi-klasse hardware;
- vaste workspace, lage snelheden/krachten en onafhankelijke noodstop;
- latency- en resourceprofiel;
- hardware-in-the-loop failure matrix.

Exit: alleen target-specifieke claims; nog geen generieke robot-, drone- of voertuigclaim.

### P4 — Mini-brain-experiment (2–4 weken, alleen na behoeftebewijs)

- kies precies één begrensde perceptie- of controlskill;
- meet deterministische/klassieke baseline;
- verzamel/versioneer gecontroleerde data;
- train en quantiseer off-device;
- vergelijk accuracy, uncertainty, latency, geheugen, energie en failure envelope;
- behoud of verwijder het model volgens vooraf vastgelegde gates.

Deze mapping is ongeveer 9–16 weken voor één implementer tot en met een kleine fysieke pilot, exclusief certificering, product-UI en productiehardening.

## 12. Eerste tickets

1. `E00`: schrijf scope, threat model en risicoklassen.
2. `E01`: definieer canonieke types en serialisatie.
3. `E02`: definieer action/authorization/receipt state machine.
4. `E03`: bouw conformance-fixtures en fouttaxonomie vóór adapters.
5. `E04`: bouw reference state reducer plus replay/full-materialization oracle.
6. `E05`: bouw policy-evaluator met deny-by-default.
7. `E06`: bouw sandbox-filesystemadapter.
8. `E07`: voeg property-based stateful tests, crashpoints en isolation canaries toe.
9. `E08`: bouw deterministische sim-arm en adapter.
10. `E09`: voeg bounded cognition-provider toe met offline fixtures.
11. `E10`: beslis op basis van gates of fysieke hardware verantwoord is.

Elk ticket krijgt vóór implementatie: purpose, setup, state materialization, isolation, stimulus, canonical expected domain, failure taxonomy, reset/shrinkgedrag en CI-tier.

## 13. Belangrijkste open beslissingen

Voor P0 moeten een mens en reviewer expliciet beslissen:

- eerste concrete gebruiker en use-case;
- toegestane maximale impact van de eerste fysieke pilot;
- event-sourced versus snapshot-plus-log persistence;
- authorization UX en wie approvals mag geven;
- capability- en fouttaxonomie;
- simulator fidelity en welke claims hij wel/niet ondersteunt;
- minimale edge-hardware en offline-eisen;
- licentie- en distributiemodel voor skills;
- welke Umwelt-contracten eventueel worden hergebruikt versus via adapter vertaald.

## 14. Niet in de eerste roadmap

- drones, auto's, boten of openbare ruimte;
- high-force of mens-nabije industriële robotica;
- autonome online training;
- generieke multi-agent orchestration;
- zelf-installeren van onbekende skills;
- lange onbewaakte plannen;
- gedeelde Engine/Umwelt database;
- certificeringsclaims;
- een eigen foundation model.

## 15. Beslispunten na elke fase

Na iedere fase is de juiste uitkomst niet automatisch “doorbouwen”. Mogelijke besluiten:

- **doorgaan:** gates gehaald en volgende hypothese blijft zinvol;
- **vereenvoudigen:** een bestaande controller/runtime levert dezelfde waarde;
- **versmallen:** alleen één domein blijkt coherent en verkoopbaar;
- **integreren:** Umwelt of een bestaande robotics/runtime-component verdient een adapter;
- **stoppen:** safety, adaptercomplexiteit of economische waarde ondersteunt de producthypothese niet.

Negatieve resultaten blijven bewaard. Complexiteit mag geen mislukte hypothese redden.
