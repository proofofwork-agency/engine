# Engine — diepere research

> Vervolg op `glm.md`. Deze notitie positioneert Engine tegen vier families van bestaande systemen (ROS 2, seL4/capability-security, DO-178C en LLM-agentframeworks), stelt de witte vlek vast die Engine claimt, verscherpt de risico's op basis van die vergelijking, duikt in de open architectuurbeslissingen, en sluit af met een risicoregister en concrete dingen om te monitoren.
>
> Onderzoeksmethode: bronnen opgehaald via Wikipedia (DO-178C, Robot Operating System, Capability-based security) en seL4-verificatiedocumentatie, gekruist met de eigen Engine-governance (`plan.md`, `AGENTS.md`, `RULES.md`, `ARCHITECTURE_GUARDRAILS.md`, `RESEARCH_PROTOCOL.md`). Engine zelf is `SPECULATIVE` — geen code of metingen aanwezig.

## 1. Positionering tegen vier systeemfamilies

Engine wordt pas scherp als je ziet *welke eigenschap het van elk familie leent, en welke het nadrukkelijk afwijst*.

### 1.1 Tegenover ROS / ROS 2

ROS is volgens de eigen "ROS equation" **Plumbing + Tools + Capabilities + Ecosystem**. De kern is opzettelijk dun: nodes verbinden via topics (pub/sub), services (request/reply) en actionlib (preemptable tasks), met een parameter-server en rosbag-record/replay. ROS 2 voegde DDS-middleware, real-time-ondersteuning en embedded-targets toe, maar bleef een *middleware* zonder autoriteitsmodel.

| Dimensie | ROS / ROS 2 | Engine |
| --- | --- | --- |
| Delingsambitie | heterogene robots via dunne IPC-plumbing | heterogene systemen via capability/policy/receipt-plumbing |
| Autoriteitsmodel | **ambient authority** — iedere node kan (naamsconventies daargelaten) naar ieder topic publiceren | deny-by-default, scoped, verlopende autorisatie per target/actie/snapshot |
| Bewijs/observatie | ongetypeerde messages, losseQuality-of-Service | getypeerde `Observation` met bron/tijd/kwaliteit/dekking + `ExecutionReceipt` |
| Realtime | geen RTOS, real-time code wordt *erbij* geïntegreerd, niet bezeten | expliciete scheiding deliberatief vs. realtime; realtime blijft bij device-controllers |
| LLM-rol | niet gespecificeerd (ROS is model-agnostisch) | perifere, onbetrouwbare, verwisselbare voorstelgenerator |

**Het scherpe verschil:** ROS organiseert *communicatie*, Engine organiseert *autorisatie + bewijs rond actie*. ROS' dunne-kern-bet werkt omdat message-passing domein-agnostisch is. Engine claimt een dikkere, domein-bewustere laag (autoriteit en bewijs moeten per-target redeneren). Dat is precies de spanningsbron: als Engine niet dun genoeg kan zijn om breed te dragen, maar niet dik genoeg om ROS + een kleine policy-node te overtreffen, blijft er geen product over. Dit is de eigen falsificatievoorwaarde (`plan.md:43`), nu scherper: ROS bewijst dat "dunne plumbing" levensvatbaar is; de vraag is of *autoriteitsplumbing* ook dun kan zijn.

### 1.2 Tegenover seL4 / capability-based security

seL4 is de meest formeel bewezen kernel: machine-gecheckte bewijzen van functionele correctie van specificatie tot binaire code, wat klassen fouten (buffer-overflows, memory-leaks) uitsluit en verder gaat dan Common Criteria, ISO 26262 en DO-178C op hun strengste niveau — onder expliciete aannames (assembly, boot-code, hardware-interface, DMA). Capability-security definieert een capability als een *onvervalsbare, overdraagbare token van autoriteit* die een object refereert met een set toegangsrechten, ontworpen rond least-privilege en als antwoord op het *confused deputy problem*.

Engine leent drie ideeën uit deze familie:

1. **Scoped autorisatie als capability.** Engine's `Authorization` (gebonden aan target, actie, limits, expiry) is functioneel een capability in de Levy/Miller-zin — niet een ambient recht maar een draagbaar, begrensd, verlopend bewijs.
2. **Het confused-deputy-probleem is exact het LLM-als-voorstelgenerator-risico.** Een LLM die namens een gebruiker voorstelt, is een *confused deputy*: hij kan worden misleid om een actie voor te stellen die diens ambient authority misbruikt. Engine's antwoord — autoriteit expliciet, scoped, verlopend, onafhankelijk van de voorsteller — is het canonieke capability-antwoord. De conceptuele fit is sterk.
3. **Onafhankelijke enforcement.** seL4 dwingt isolatie af in de kernel; Engine wil de safety-plane onafhankelijk houden van commando-, netwerk- en modelpad.

**Het scherpe verschil:** seL4 isoleert *processen* (geheugen/CPU). Engine isoleert *actie-autoriteit en bewijs rond fysieke/soft actie*. seL4's bewijs geldt alleen de kernel, niet userland; Engine kan realistisch zijn hele runtime niet formeel bewijzen. Dus: capability-*denken* is solide basis voor Engine, maar seL4-*bewijsniveau* is voor één implementer in 16 weken onbereikbaar. Het reconstructie-oracle (`RESEARCH_PROTOCOL.md:130-134`) is het realistische substituut.

### 1.3 Tegenover DO-178C

DO-178C is het primaire luchtvaart-certificeringskader voor software. Bepalende elementen: Development Assurance Level A–E (op basis van falingscategorie: Catastrophic → No-effect), waarbij Level A 71 doelen stelt waarvan 30 *met onafhankelijkheid* (verificateur ≠ auteur); bidirectionele traceerbaarheid tussen certificeringsartefacten (requirement ↔ code ↔ test ↔ resultaat); het expliciete doel "Executable Object Code satisfies the software requirements *and provides confidence in the absence of unintended functionality*"; entry/exit-criteria per proces; SOI-review-gates (Stages of Involvement).

Engine leent hiervan:

- **Traceerbaarheid als eerstekans burger.** `BUILDER_CHECKLIST.md` en `ARCHITECTURE_GUARDRAILS.md` §25 eisen dat iedere beslissing terug te leiden is tot snapshot → proposal → policyversie → autorisatie → adapter → observatie → receipt. Dat is DO-178C's bidirectionele traceerbaarheid, toegepast op een runtime i.p.v. een certificeringsdossier.
- **"Onbedoelde functionaliteit"-doel.** De hele deny-by-default + scoped-authorisatie + getypeerde-contracten-philosophy is het runtime-equivalent van DO-178C's "absence of unintended functionality."
- **Onafhankelijkheid.** DO-178C gebruikt *menselijke* onafhankelijkheid (andere reviewer). Engine codificeert onafhankelijkheid *architecturaal* (aparte safety-plane). Dat is in principe sterker.

**Het scherpe verschil — en het belangrijkste hiaat:** DO-178C is een *certificeringsproces*, geen runtime. Het wordt afgegeven door bevoegde instanties (FAA, EASA), niet door interne testing. `GOVERNANCE.md:31` definieert `CERTIFIED` expliciet als "alleen wanneer een bevoegd extern proces het daadwerkelijk toekent." Engine kan intern DO-178C-*achtige* rigor claimen, maar zonder extern certificeringstraject blijft dat bewering, niet status. De kloof tussen "interne rigor" en "CERTIFIED" is de hele certificeringsindustrie — en dat traject is per domein (luchtvaart, automotive ISO 26262, medisch IEC 62304) anders en zwaar. Engine's "MUST NOT claim certification from internal testing alone" (`AGENTS.md` §10) is hier terecht streng, maar betekent dat fysieke/veiligheidskritische adoptie een tweede, veel zwaarder traject vereist dat buiten de 16-weken-roadmap valt.

### 1.4 Tegenover LLM-agentframeworks (LangChain/AutoGen-klasse)

Deze frameworks maken de LLM tot de control loop: een recursieve tool-use-cyclus waar het model zelfstandig observeert, beslist, aanroept en evalueert. Engine wijst dit expliciet af (`RULES.md` MUST NOT 2, `AGENTS.md` §2.2). Het verschil is niet gradueel maar inversioneel:

- Agentframework: model bezit de loop; tools zijn onpriviligeerde functies die het model aanroept; veiligheid wordt *opgelegd* (guardrails, sandboxing achteraf).
- Engine: getypeerde pijplijn bezit de loop; het model is een onpriviligeerde voorstelfunctie; veiligheid is *structureel* (deny-by-default vóór uitvoering, autorisatie los van voorsteller).

Dit is oprecht een ander ontwerppunt. De markt beweegt momenteel sterk naar de model-eist-de-loop-kant; Engine positioneert zich bewust contra-trend richting veiligheidskritieke systemen. Dat is een nichewedstraat, geen massamarkt.

## 2. De witte vlek die Engine claimt

Uit de vier vergelijkingen volgt Engine's reële witte vlek, en waarom deze verdedigbaar is:

> **Niemand combineert momenteel (a) ROS-achtige heterogene dekking via dunne plumbing met (b) capability-style scoped autoriteit en (c) DO-178C-achtige traceerbare receipts/evidence-grades, terwijl de LLM tot perifere, verwisselbare voorstelgenerator wordt gedegradeerd.**

De families specialiseren zich langs verschillende assen:
- ROS 2 heeft (a), mist (b) en (c).
- seL4/capability heeft (b), is een kernel geen actuatieruntime, draagt niet bij aan (a) of (c) voor soft/fysieke actie.
- DO-178C heeft (c) als *proces*, niet als runtime, en vereist externe certificering.
- Agentframeworks hebben geen van drie, en positioneren de LLM verkeerd.

De claim dat deze drie samen een coherentere veilige besturingslaag vormen dan elk apart is plausibel en onbezet. Dat is de sterkste versie van de producthypothese.

## 3. Verscherpte risico's uit de vergelijking

### 3.1 Het "ROS + policy-node"-dreigement (sterkste concurrent)

ROS 2 + een kleine, doelgebouwde policy/audit-node kan een groot deel van Engine's waarde leveren met een orde van magnitude minder contractuele schuld. MoveIt toont dat domeinrijke lagen (motion planning) succesvol *bovenop* ROS leven; een "PolicyNode" die deny-by-default en receipts toevoegt is geen onredelijke architectuur. Engine moet aantonen dat *het integreren van autoriteit/bewijs in de kern* structureel veiliger is dan *het eraan vastknopen*. Als het verschil marginaal is, wint de dunne-oplossing. Dit is het executierisico voor de hele producthypothese.

### 3.2 De formaliseringslast is seL4-achtig in ambitie, niet in bereik

Engine's reconstructie-eis (`reference_reduce == runtime_replay == full_materialization`, plus property-based stateful tests met crash-injectie) benadert de *mental discipline* van formele verificatie zonder het *bewijs* te leveren. Dat is wetenschappelijk eerlijk (en expliciet als zodanig gemarkeerd), maar betekent dat Engine noch de lage kosten van ROS (geen autoriteitsmodel) noch de sterke garanties van seL4 (formeel bewijs) bereikt. De niche is "bewijsbare-oracle-rigor zonder formele verificatie" — een middenweg die zijn waarde alleen aantoont door de gates daadwerkelijk te halen.

### 3.3 Certificering is een tweede, verborgen roadmap

`plan.md`'s 9–16 weken leveren *interne rigor*. Fysiek veiligheidskritieke adoptie (de tafelarm in P3 is nog laag-risico) vereist daarna domeincertificering die buiten de scope valt. De repo is hier eerlijk over (`GOVERNANCE.md`), maar commerciële beweringen over "veilig" (`RESEARCH_PROTOCOL.md:301` verbiedt dit zonder operationele definitie) mogen dit gat niet dichtmetselen.

### 3.4 De approval-burden-economie (onopgelost, productkritiek)

DO-178C lost het approval-probleem deels op door het te institutionaliseren (DER's, SOI-gates) — traag en duur, maar geaccepteerd in luchtvaart. Engine wil nuttig zijn op menselijke tijdschalen *zonder* die zwaarte. Elke muterende actie vereist scoped autorisatie met expiry. Zonder een goededesignede autorisatie-UX (pre-approvals voor capability-klassen? delegation? sessie-scope?) wordt Engine een trage afstandsbediening. `plan.md:333` laat dit bewust open; `RESEARCH_PROTOCOL.md:261` noemt het als abandon-gate. Capability-security biedt patronen (delegation, attenuated capabilities) die hier kunnen helpen — de ontwerptaak is onvoltooid.

### 3.5 De ambient-authority-risico's die Engine nog niet volledig adresseert

Capability-theorie waarschuwt voor *ambient authority* (rechten afgeleid van identiek-zijn met een principal, niet van een expliciete token). Engine's adapters draaien waarschijnlijk met OS-credentials (bestandstoegang, seriële poorten, netwerk). Als de adapter-identiteit ambient autoriteit draagt buiten de Engine-autorisatie om, is de capability-belofte hol. `RULES.md` MUST 21 (isoleer untrusted code, begrens fs/process/net/tijd) raakt dit, maar er is geen expliciet dreigingsmodel dat zegt: *de adapter mag niet meer kunnen dan de Engine-autorisatie toestaat, ongeacht zijn OS-rechten*. Dat vereist privilege-separation (de adapter draagt de capability *door* aan de device, heeft zelf geen ambient recht). Dit verdient een ADR vóór P1.

## 4. Diepgang op open beslissingen (`plan.md` §13)

### 4.1 Event-sourced vs. snapshot-plus-log

`RESEARCH_PROTOCOL.md:130-134` eist equivalentie tussen replay en materialisatie *ongeacht* de keuze. De keuze is dus minder over correctheid dan over operatielelijkheid:
- **Event-sourced** (alleen append): sterke audit/replay, natuurlijke `ExecutionReceipt`-stream, eenvoudigere concurrency (geen in-place mutatie), maar dure current-state-queries.
- **Snapshot-plus-log**: snelle operatiele queries, maar het log en de snapshot kunnen uit sync raken, wat het reconstructie-oracle juist moet vangen.

**Aanbeveling:** event-sourced core met periodieke materialized snapshots als *cache* onder een expliciet cache-contract (`ARCHITECTURE_GUARDRAILS.md` §24). De snapshots mogen nooit op het correctheidspad staan — het oracle blijft de replay. Dit sluit aan bij de seL4-les dat er één autoritatief pad moet zijn.

### 4.2 Authorization-UX en wie approvals mag geven

Dit is productkritiek en onbeslist. Capability-security biedt drie overdraagbare patronen:
1. **Delegation** — een principal mag een capability (verder afgezwakt) doorgeven.
2. **Attenuation** — een capability kan worden versmald (minder rechten, kortere expiry) bij overdracht.
3. **Capability-klassen / pre-authorization** — een principal keurt vooraf een *klasse* van acties goed (binnen envelope), zodat runtime alleen nog binnen-envelope checkt.

Patroon 3 lost de approval-burden op voor veilige klassen (read-only, idempotent, binnen workspace) terwijl hoog-risico acties mens-in-de-loop behouden. `PolicyDecision`'s `REQUIRE_APPROVAL`/`DEFER` ondersteunen dit. De openstaande ontwerptaak: een *risk-class-taxonomie* die bepaalt welke acties pre-authorized mogen zijn en welke altijd menselijke goedkeuring eisen — dit hoort in de P0-threat-model (`E00`).

### 4.3 Simulator-fidelity en welke claims hij ondersteunt

`RESEARCH_PROTOCOL.md` labelt evidence-omgevingen strikt (`SIMULATION` mag geen fysieke claims). De tafelarm-sim moet dus *contracten en foutpaden* bewijzen (state machines, timeout, disconnect, partial), niet *fysica* (wrijving, speling, sensor-ruis). De simulatie-oracle moet dit expliciet *niet* modelleren en dat melden — anders ontstaat de "simulator passed → robot is safe"-val (`ARCHITECTURE_GUARDRAILS.md` §1). Gazebo/PyBullet bieden fyzieke fidelity, maar fidelity is hier een *val*: een sim die fyziek overtuigend lijkt verleidt tot ongeoorloofde beweringen. Eerlijker is een *deterministische, contract-niveau* sim (geen fyzieke engine) voor P1/P2, met fyzieke fidelity pas in P3 op echte hardware.

### 4.4 Edge-hardware en offline-eisen

Pi-klasse hardware voor P3 is redelijk voor één arm. Maar de *onafhankelijkheidseis* (safety-plane los van commando-/modelpad) is op één bordje lastig: een software-watchdog op dezelfde Pi deelt CPU, stroom en faalmodus met de commando-stack. Echte onafhankelijkheid vereist of (a) een aparte microcontroller-noodstop, of (b) de arm's eigen controller (veel armen hebben ingebouwde motor-controllers met stroom/snelheidslimieten). `plan.md:101` eist een "geaudit autorisatiepad buiten het model" voor override, en §F van de checklist eist een "onafhankelijke emergency-stop/watchdog waar vereist." Concreet: P3 moet een *fysieke*, hardwarematige noodstop hebben plus het arm-eigen controller-begrenzingsmechanisme — geen Pi-software-stop alleen.

## 5. Risicoregister

| # | Risico | Kans | Impact | Mitigatie in repo | Aanbeveling |
| --- | --- | --- | --- | --- | --- |
| R1 | "Dunne-laag"-instorting: Engine wordt cosmetische logging bovenop ROS-achtige plumbing | midden | fataal voor hypothese | `plan.md:43` eigen falsificatie; 0.1-slice claim #1 | Toets expliciet of de *generieke* laag >50% domeinlogica draagt; zo niet, versmald of stop |
| R2 | "ROS + policy-node" is structureel eenvoudiger voor de meeste use-cases | hoog | versmalt product aanzienlijk | abandon-gate `RESEARCH_PROTOCOL.md:255` | Meet Engine-vs-ROS+policy op gelijke budget in de slice; documenteer eerlijk |
| R3 | Ambient authority in adapters ondermijnt capability-belofte | midden | silent safety-falen | `RULES.md` MUST 21 (isoleer untrusted code) | Privilege-separation-ADR vóór P1; adapter draagt capability *door*, heeft zelf geen ambient recht |
| R4 | Approval-burden maakt Engine onbruikbaar op menselijke tijdschalen | midden-hoog | productfalen | abandon-gate `RESEARCH_PROTOCOL.md:261` | Risk-class-taxonomie + pre-authorization voor veilige klassen; meet goedkeuringsfrequentie als metric |
| R5 | Sim-fidelity verleidt tot ongeoorloofde fysieke beweringen | midden | claim-inflatie | `RESEARCH_PROTOCOL.md` evidence-labels; `ARCHITECTURE_GUARDRAILS.md` §16 | Deterministische contract-sim, geen fyzieke engine, vóór P3 |
| R6 | Reconstructie-oracle verdubbelt implementatiekosten; snelheid daalt onder governance-last | hoog | roadmap-overschrijding | — | Beschouw het oracle als release-blocker maar niet als *productiepad*; materialized snapshots als cache onder contract |
| R7 | Certificering is verborgen tweede roadmap; interne rigor ≠ CERTIFIED | zeker (per definitie) | blokkeert veiligheidskritische adoptie | `GOVERNANCE.md:31`, `RESEARCH_PROTOCOL.md:301` | Communiceer scope eerlijk; positioneer 0.x als "onderzoeks-/software-veilig," niet "robotveilig gecertificeerd" |
| R8 | LLM levert geen toegevoegde waarde boven canned proposals (claim #2 keert zich) | midden | versmalt waardeprop tot "capability-runtime zonder AI" | slice claim #2 test dit | Accepteer dat "capability-runtime zonder AI" een legitieme, mogelijks sterkere scope is |
| R9 | Één implementer + 4 testlagen + 14 types + reconstructie = onrealistische 16 weken | hoog | uitloop, oppervlakkige tests | — | Bevries P0-contracten streng; snoei v0.1-types tot strikt noodzakelijke; verplaats mini-brain naar "alleen na bewijs" |
| R10 | LLM-providerkoppeling lekt in correctheid ondanks het axioma | midden | schendt kernclaim | slice claim #2, `BUILDER_CHECKLIST.md:106` | Provider-onafhankelijke conformance-suite als CI-gate; elke provider draait dezelfde fixtures |

## 6. Wat te monitoren naarmate P0 vordert

1. **Verhouding generieke vs. domeinspecifieke code** in de eerste twee adapters. Als >70% domeinlogica, is R1 acuut — heroverweeg scope vóór P2.
2. **Goedkeuringsfrequentie per eenheid nuttige actie.** Een hoge ratio is een vroeg signaal van R4.
3. **Of canned proposals en LLM-proposals dezelfde policy/execution-uitkomst geven.** Dit is de levenstest van het LLM-vervangbaarheidsaxioma (R8/R10).
4. **Of het reconstructie-oracle ooit faalt onder property-based tests.** Een oracle-fout is een fundamenteel correctheidsbug, niet een optimalisatie-issue.
5. **Of de adapter ambient autoriteit gebruikt buiten Engine-autorisatie om.** Zelfs één pad hiervan is een R3-schending die vóór P1 dicht moet.

## 7. Conclusie

Engine's witte vlek is reëel en onbezet: de combinatie van ROS-heterogeniteit, capability-autoriteit en DO-178C-traceerbaarheid met de LLM gedegradeerd tot voorstelgenerator. De governance is ongewoon volwassen. De beslissende risico's zijn echter niet abstract maar executief: (R1/R2) of autoriteitsplumbing dun genoeg kan zijn om breed te dragen zonder in te storten tot logging, (R3) of de adapter-privileges de capability-belofte niet ondermijnen, en (R4) of de approval-burde economisch leefbaar is. De 0.1-slice is correct gebouwd om R1 en R8 direct te toetsen; R3 en R4 vereisen ontwerpbeslissingen (privilege-separation-ADR, risk-class-taxonomie) die thuishoren in P0, niet later. De roadmap is bij optimistische lezing haalbaar, bij realistische lezing 1,5–2× zwaarder door testlast en governance — de eerlijke status blijft `SPECULATIVE` tot de gates meten.
