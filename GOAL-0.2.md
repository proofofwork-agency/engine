# GOAL-0.2 — Engine 0.2 realisatie (ogen, cross-body brein, verdiende handen)

> Status: actief anker voor 0.2, aanvullend op het bevroren `GOAL.md` (0.1).  
> Dit document **herdefinieert Engine niet**. `GOAL.md` §0 blijft de identiteit:
> Engine is het levende systeem — hart én intelligentie — met pluggable
> lichamen (plugins), pluggable cognitie (LLM's/Cells) en ingebouwde authority.  
> Conceptbron: owner-intentie, 2026-08-11. Bij conflict wint de owner-uitleg.

Governance: `docs/ROADMAP_30D.md` vereist voor cross-plugin contextworkflows
een expliciet ownerbesluit, een ADR en bewijs. **De owner-goedkeuring van dit
goal plus `docs/adr/ADR-0012-cross-plugin-evidence-and-privacy.md` is dat
besluit.** ADR-0008-grenzen blijven staan: cross-plugin mutatie blijft
geweigerd, maximaal één cognition-hop, geen wildcards.

---

## 1. Het doel (één zin)

**Engine 0.2 bestaat wanneer hetzelfde levende Heart het echte huis wekenlang
continu heeft geobserveerd, zijn ritmes goed genoeg heeft geleerd dat zijn
shadow-beslissingen preregistered overeenkomen met werkelijk huishoudgedrag,
zijn eerste geverifieerde cross-body beslissing heeft genomen (actie in het
ene lichaam, gerechtvaardigd door duurzaam getypeerd bewijs uit een ander
lichaam), en DELEGATED autoriteit op één fysieke lichtzone heeft verdiend via
de bevroren vijf-lus lux/watt-gate — zonder één handgeschreven
automatiseringsregel.**

---

## 2. Klaar-definitie (Done = dit alles waar)

### 2.1 Ogen open (anti-snapshot-theater)

| # | Criterium | Fail als… |
| --- | --- | --- |
| O1 | Het Heart draait ≥ 14 dagen continu op het echte huis in `OBSERVE`, onder supervisie (launchd); slaapgaten zijn toegestaan, iedere herstart herstelt continuïteit en wordt met oorzaak gelogd | observatie bestaat alleen als losse snapshots of demo-runs |
| O2 | Storegroei blijft binnen het in ADR-0011 bevroren budget (doel < `50 MB/dag`, hard fail > `150 MB/dag`), met werkende retention en snapshot-pinning | de store groeit onbegrensd of pruning breekt reconstructie |
| O3 | Eén onafgevangen fout in een cycle, provider, learner of subscribe doodt de daemon niet; backoff en circuit-events zijn duurzaam zichtbaar | één exception beëindigt het organisme |
| O4 | Gedragsstroom is duurzaam: waarnemingen, handmatige-override-signalen en confirmaties overleven proces- en Mac-herstart | override in de Homey-app produceert geen bewijs |
| O5 | `engine status` en de daily heartbeat vertellen na herstart de waarheid (storegrootte, lease, laatste cycle, failures) | statusrapportage is in-memory theater |

### 2.2 Shadow-competentie (anti-post-hoc)

| # | Criterium | Fail als… |
| --- | --- | --- |
| S1 | Shadow-beslissingen worden duurzaam gescoord tegen daadwerkelijk waargenomen huishoudgedrag, per opportunity, met timestamps (slaapgat-robuust) en `dispatch_count == 0` | scoring gebeurt achteraf, in-memory of op fake-data |
| S2 | EXP-2026-004 is bevroren vóór het gescoorde venster opent; burn-in-data telt niet mee; het venster wordt exact één keer geconsumeerd | drempels of baselines bewegen na het zien van data |
| S3 | Agreement ≥ `60%` absoluut én ≥ beste-baseline + `10` punten (always-defer, hour-of-week-mimic, persistence), strikte false-intervention ≤ `10%`, over ≥ `50` gesloten opportunities in ≥ `10` dagen | Engine verliest van een klok, of wint alleen door nooit iets te willen |
| S4 | Een negatief resultaat wordt als canoniek no-go vastgelegd, zoals EXP-2026-003 | een gefaalde gate wordt weggeredeneerd |

### 2.3 Cross-body beslissing (anti-prompt-lijm)

| # | Criterium | Fail als… |
| --- | --- | --- |
| X1 | Een Homey-actievoorstel wordt gerechtvaardigd door getypeerd bewijs uit `engine.context` (`EvidenceRefV1`): ≥ 1 eigen-plugin-referentie én ≥ 1 contextreferentie, resolvebaar binnen de eigen projectie, grade `OBSERVED`/`DERIVED`, vers | bewijs is een prompt-string, niet-resolvebare id's kunnen dispatchen |
| X2 | Privacygrants worden afgeleid van de bron (per observatietype), niet van zelfdeclaratie; een `local`-grant geeft nooit exacte coördinaten vrij | consumer-zelfdeclaratie blijft de enige privacycheck |
| X3 | Contextbewijs overleeft een vol huis: source-fair quota's, per-bron truncatievlaggen | 442 observaties verdringen context stilletjes uit de projectie |
| X4 | De volledige lifecycle loopt eerst 5/5 in simulatie (incl. één injected no-effect-run), daarna één keer live `SUPERVISED` met ownergoedkeuring en geverifieerd effect | sim-bewijs wordt als live-bewijs gepresenteerd |
| X5 | Cross-plugin mutatie blijft onmogelijk; alleen bewijs kruist lichamen; de cross-body route gebruikt `cognition_route = "deterministic"` (modelroute is stretch, geen gate) | een tweede loop, een extra cognition-hop of mutatie over de plugingrens |

### 2.4 Verdiende handen (anti-ACK-waarheid)

| # | Criterium | Fail als… |
| --- | --- | --- |
| F1 | De bevroren fysieke gate slaagt: één zone, vijf opeenvolgende gesloten lussen met onafhankelijke lux- én wattverificatie, conform `plugins/engine-homey/DEPLOYMENT.md` | de gate wordt versoepeld of achteraf geherinterpreteerd |
| F2 | Eén van de vijf lussen bevat een fysiek geïnjecteerde no-effect-storing; Engine registreert ACK-zonder-sensoreffect als failure | een ACK telt als effect |
| F3 | Nul modelcalls tijdens stabiele monitoring; collaterale zones blijven 5/5 onveranderd | de demo denkt hardop zonder reden of raakt de gang aan |
| F4 | Daarna 7 dagen `DELEGATED` voor uitsluitend de bewezen zone: iedere dispatch met receipt + oracle, nul policy-schendingen, `CLOSED_UNKNOWN` alleen met owner-review | delegatie wordt breder dan de bewezen zone |

**Niet required voor dit goal (mag bestaan, mag niet blokkeren):**

- calendar/agenda-plugin als derde lichaam (stretch na M6);
- Cells (alleen na een preregistered deficit uit S-scoring, met nieuw experiment-id);
- model-brain op de cross-body route (stretch; deterministische route is de gate);
- multi-zone of andere capabilityfamilies voorbij de bewezen zone;
- procesisolatie van plugins;
- Umwelt-integratie.

---

## 3. Succeszin (wat je op dag X mag zeggen)

> Engine 0.2 bestaat: het organisme heeft wekenlang met eigen ogen naar het
> echte huis gekeken, zonder één handgeschreven regel geleerd wat normaal is,
> in schaduw bewezen dat zijn beslissingen kloppen, zijn eerste beslissing
> genomen op bewijs dat van het ene lichaam naar het andere kruiste — en pas
> daarna, via de bevroren fysieke gate, echte handen verdiend voor één zone.

---

## 4. Anti-driftregels (aanvullend op GOAL.md D1–D8)

| Drift | Verboden stille herschrijving | Toegestaan alleen als… |
| --- | --- | --- |
| D9 Regel-smokkel | Handgeschreven automations/scenes om milestones te halen | beslislogica is versioned, gefingerprinte, bewijs-citerende strategiecode; parameters komen uitsluitend uit owner-enrollments |
| D10 Bewijs-lijm | Cross-body als prompt-injectie, cross-plugin mutatie of tweede loop | getypeerd bewijs kruist onder enrollment + afgeleide privacygrants; actie blijft in het eigen lichaam |
| D11 Kernel-drift | Markt/control-layer-framing die de organisme-these stilletjes vervangt | owner besluit expliciet tot herpositionering (omgekeerde van D1) |

---

## 5. Realisatiepad (volgorde, geen herdefinitie)

```text
A0  Dit anker + ADR-0011 bevriezen (owner sign-off)
A1  Change-only revisions + kwantisatie + poll-config
A2  Snapshot-normalisatie + compressie
A3  Retention + pinning + store-CLI
A4  Daemon-overleving: isolatie, backoff, re-subscribe
A5  Heartbeat, duurzame cursors, launchd-runbook
A6  14-daagse OBSERVE-soak op het echte huis          -> M4
B0  Override-detectie verbreden (Homey)
B1  Shadow-outcome-scorer (Heart-owned, plugin-neutraal)
B2  Baselines + shadow-report CLI
B3  EXP-2026-004 bevriezen (owner sign-off)
B4  Gescoord venster + beslissing                     -> M5
C1  Zonnestand (DERIVED) in engine.context
C2  Source-fair quota's + privacy-afleiding + goal_id-check
C3  EvidenceRefV1 + provenance-validatie
C4  Context-lezende Homey-strategie + volledige sim
D1  ADR-0013 hardening (admission, closure, conflict)
C5  Live SUPERVISED cross-body beslissing             -> M6
D2  Fysieke gate: vijf gesloten lussen, lux/watt
D3  7 dagen DELEGATED één zone + seal                 -> M7
```

---

## 6. Milestones

**M4 — "Ogen open"**  
Het echte huis, `OBSERVE`, ≥ 14 dagen onder supervisie: duurzame gedrags- en
overridestroom, begrensde storegroei met pinning, daemon die storingen
overleeft, eerlijke status en heartbeat. Evidenceklasse:
`PRODUCTION_OBSERVATIONAL` — dit promoveert geen actuatieclaim.

**M5 — "Shadow-competentie"**  
Preregistered EXP-2026-004 op de echte gedragsstroom: agreement- en
false-intervention-gates uit §2.2, exact één keer geconsumeerd. Een eerlijke
no-go is een geldig resultaat en wordt canoniek vastgelegd.

**M6 — "Eerste cross-body beslissing"**  
Eén actie in het Homey-lichaam, gerechtvaardigd door vers getypeerd bewijs uit
`engine.context`, eerst 5/5 in simulatie, dan één keer live `SUPERVISED` met
geverifieerd effect en gearchiveerd bewijs onder `artifacts/evidence/M6/`.

**M7 — "Verdiende handen"**  
De bevroren fysieke gate (5/5, lux/watt, no-effect-injectie) en daarna 7 dagen
schone `DELEGATED` voor uitsluitend die zone. Hiermee is 0.2 verzegeld.

M4 alleen = het organisme leeft.  
M5 = het organisme begrijpt zijn huis.  
M6 = de kern van "is dit een organisme met één brein en meerdere lichamen?".  
M7 = vertrouwen is verdiend, niet aangenomen.

---

## 7. Owner-lock

- **Concept owner:** project owner (jij).
- **Dit goal wijzigen:** alleen owner. `GOAL.md` (0.1) blijft bevroren.
- **Agents:** implementeren en meten tegen §2; getallen in §2.2 en ADR-0011
  zijn na owner sign-off bevroren; een gefaalde gate wordt nooit achteraf
  verplaatst. Bij spanning met analyses of marktdruk: dit anker + owner-concept
  winnen voor 0.2-richting.

---

## 8. Eén checkvraag bij elke PR / agent-sessie

> Brengt dit het organisme dichter bij ogen (M4), oordeel (M5), een tweede
> lichaam dat meedenkt (M6) of verdiende handen (M7) — of bouwen we opnieuw
> een schil, een regel, of een herdefinitie?

Zo nee: niet mergen als "Engine 0.2 voortgang" zonder owner-ok.
