# Grok final review — Engine

> Laatste review in deze reeks.  
> Datum: 2026-08-10.  
> Bronnen: owner-intentie, `GOAL.md`, `plan.md`, governance-docs, eerdere notes (`grok.md`, `grok-deep.md`).  
> **Geen herdefinitie van Engine.** Dit is een oordeel over coherentie, risico’s, en of 0.1 realiseerbaar is *binnen jouw concept*.

---

## 1. Wat vaststaat (owner-lock)

Engine is, in jouw woorden en in `GOAL.md`:

> Het **levende systeem** waarin **hart** en **breinen** en **tools** samen denken, ervaren en handelen.

Vast:

| Onderdeel | Rol |
| --- | --- |
| **Hart** | doelen, event/cognitielus, aandacht, duurzame world state, ervaring, continuïteit; voert aanroepen uit |
| **Algemeen brein** | begrijpt, plant, kiest tools en specialisten |
| **Specialistische breinen** | begrensde cognitie; mogen interne tools hebben |
| **Wereldtools** | gedeelde catalogus van Engine (FS, sim, sensoren, apparaten, …) |
| **Mens** | niet elke cyclus; charter/doel kan starten, lus loopt door |
| **Safety** | mag bestaan; **definieert Engine niet** |
| **Mini-brains** | groeipad (ervaring → consolideren); **niet** 0.1-voorwaarde |

Engine is **niet** alleen harness, workflow-engine, of policy-schil.

Dit is de maatstaf. Latere zinnen die “Engine = veilige execution fabric zonder brein-identiteit” of “Engine = research-kernel met safety later” heten **drift**, geen verbetering.

---

## 2. Eindoordeel in één alinea

**Het concept is coherent, ambitieus, en realiseerbaar in een smalle 0.1-vorm — mits code de identiteit bewijst vóór de governance-berg product wordt.**  
De onderdelen (algemeen model dat specialisten en tools kiest; duurzame state; multi-world tools) zijn elk bekend uit onderzoek en product; **jouw samenstelling** (hart met eigen continuïteit + multi-brain + gedeelde wereldhandel over heterogene targets) is de echte inzet en is **nog niet gebouwd**.  
De repo is nu **constitution-zwaar en implementatie-leeg**. Dat is geen weerlegging van Engine; het is wel het grootste praktische risico: dat analyses en guardrails de plaats innemen van de levende lus.  
`GOAL.md` corrigeert die volgorde zonder het concept te verkopen: **eerst hart-én-brein op twee sandbox-werelden, oracles, geen mens per stap.**

**Verdict: groen licht om te bouwen tegen `GOAL.md`. Geel licht op document-spanning. Rood licht op verder plannen zonder M1-code.**

---

## 3. Wat sterk is (en behouden moet blijven)

### 3.1 Identiteit is scherp genoeg om te bouwen

Hart vs. algemeen brein vs. specialist vs. wereldtool is een **werkverdeling**, geen metafoor-soep.  
“Intelligentie kiest; hart organiseert aanroep en continuïteit” is implementeerbaar als interfaces + één scheduler-loop.

### 3.2 Onderscheid harness vs. hart is de juiste differentiator

Claude Code / typische agent-CLIs: beurt → model → tools → klaar.  
Engine: doelen en state **overleven** beurten, herstarts, en lege provider-context; events/voortgang kunnen de lus voeden.  
Als 0.1 dát niet toont, heb je een nette harness met een mooie naam — en jij hebt terecht gezegd dat dat Engine niet is.

### 3.3 Breinen-hiërarchie is productief, niet religieus

- Eén algemeen brein (voorlopig één LLM of sterke fixture op dezelfde poort).  
- Specialisten als first-class capabilities.  
- Interne toolbox per specialist vs. gedeelde wereldtools bij Engine.  

Dat is een heldere compositieregel en voorkomt “alles is één prompt”.

### 3.4 `GOAL.md` is het juiste anti-drift instrument

Niet een nieuwe filosofie, maar: **done-criteria + verboden stille herschrijvingen + M1/M2/M3**.  
Zonder dat document winnen de zwaarste docs (`RULES`, safety gates) de default-aandacht van agents. Met `GOAL.md` is de finish line de levende lus.

### 3.5 Governance is een *asset later*, geen *identiteit nu*

`AGENTS.md` / `RULES.md` / guardrails bevatten echte engineering-waarheden (state ≠ chat, observation ≠ prediction, geen raw PWM uit LLM, fail-closed op echte schade).  
Die blijven waardevol als **contributor-gedrag** en als **latere schil**.  
Zij mogen 0.1 niet herdefiniëren tot “pas Engine als de wet af is”.

---

## 4. Wat zwak of gevaarlijk is (zonder concept te wijzigen)

### 4.1 Document-spanning: `plan.md` vs. owner + `GOAL.md`

| Toon in `plan.md` (vroege secties) | Owner / `GOAL.md` |
| --- | --- |
| LLM vooral optionele voorsteller | Intelligentie is **onderdeel van** Engine |
| Keten opent met menselijk doel + gates-zwaar pad | Hart-lus + brein kiest; mens niet per stap |
| Kernbelofte = veilige auditeerbare besturingslaag | Kern = levend systeem dat denkt, ervaart, handelt |
| Lange P0 safety/contract preflight | M1/M2: werkende kern op twee werelden |

Dit is **geen reden om Engine te herschrijven**. Het is wel een **coördinatierisico**: agents lezen `plan.md` + `RULES.md` en bouwen de schil.  
**Mitigatie (procedureel, geen concept-edit):** bij 0.1-werk is `GOAL.md` richtinggevend; `plan.md` is achtergrond en latere schillen tot owner `plan.md` zelf bijwerkt.

### 4.2 Constitution zonder lichaam

Er is (op reviewmoment) geen runtime-code die I1–I5 of W1–W4 bewijst.  
Elke week extra prose zonder M1 verhoogt de kans op paper-Engine (drift D7).

### 4.3 Ambitie van “één generiek brein over vele werelden”

Onderzoek (HuggingGPT, MRKL, Toolformer, CoALA, e.d.) dekt **stukken**.  
Jouw volledige stack — blijvende identiteit, multi-world state, aandacht, ervaring, specialisten, apparaten — is **niet** “al opgelost”.  
Dat is goed: daar zit de inzet. Het is ook het punt waar 0.1 **smal in werelden** moet blijven (FS + één sim), anders verdamp je in domein-semantiek.

### 4.4 Twee faalmodi die jouw concept van binnen uithollen

Zonder het concept te veranderen, zijn dit de manieren om het alsnog te *verliezen* in de praktijk:

1. **Harness-collapse** — alles in de LLM-session; hart is een dunne wrapper.  
2. **Safety-collapse** — maanden auth/policy vóór één autonome meerstaps goal.  
3. **Fork-collapse** — “Engine-FS” en “Engine-sim” als twee geesten.  
4. **Oracle-collapse** — demo’s die slagen omdat het model “done” zegt.

`GOAL.md` §2 is precies de vaccinatie daartegen. Gebruik die tabellen letterlijk als acceptatie.

### 4.5 Eerdere Grok-analyses: wat behouden, wat negeren

| Eerdere lijn | Status t.o.v. jouw lock |
| --- | --- |
| Scheiding proposal/authority/observation als *engineering hygiene* | Behouden als bouwkwaliteit, niet als herdefinitie |
| “Brains as tools” / L2 cognition fabric | Deels overlap; mag **niet** Engine reduceren tot tool-host zonder hart-identiteit |
| “Research-kernel, safety = 0” als nieuwe thesis | **Afwijzen als herdefinitie**; smalle lab-scope mag, identiteit niet strippen |
| Safety-first roadmap als eerste finish | **Afwijzen voor 0.1-volgorde**; safety blijft later/parallel hygiëne |
| Falsificatie “gedeelde laag > glue” | Behouden als **meetvraag onder jouw goal (W3/W4)**, niet als excuus om brein te schrappen |

---

## 5. Is dit “überhaupt een ding”?

### Binnen jouw definitie

| Claim | Oordeel |
| --- | --- |
| Hart met duurzame goals/state/ervaring + lus | **Ja, bouwbaar**; klassiek + agent-memory, maar zelden strak gedaan |
| Algemeen brein kiest specialisten en tools | **Ja**; bewezen patroon (router/orchestrator-LLM) |
| Gedeelde wereldtools + adapter per target | **Ja**; tool/MCP/ROS-achtig |
| Zelfde kern over FS + sim | **Ja als 0.1-hypothese**; hier faalt of slaagt “Engine” i.p.v. toolkit |
| Zonder mens per stap meerstaps oracles | **Ja in sandbox**; dit is de demo die telt |
| Later fysiek + safety-schil | **Open en zwaarder**; hoort niet in de 0.1-finish, hoort wél in de langetermijn-belofte van jouw concept |
| Mini-brains uit ervaring consolideren | **Interessant groeipad**; niet nodig om 0.1 waar te maken |

**Zwakke claim** (“code roept twee adapters aan”): te dun voor jouw Engine.  
**Jouw 0.1-claim** (hart + brein + twee werelden + oracle + continuïteit): precies zwaar genoeg om te weten of het een ding is.  
**Volledige productclaim** (veilige generieke besturing van software én fysiek met rijke cognitie): te vroeg om te vieren; niet te vroeg om naartoe te *richten* nadat M2 staat.

---

## 6. Spanning met governance — praktische leesregel

Voor **contributors die code schrijven in deze repo**:

1. **Identiteit & 0.1-richting:** `GOAL.md` + owner.  
2. **Geen stille concept-rewrite** in analyses of “verbeterde” one-liners.  
3. **Geen outward/physical damage, geen sandbox-escape** — ook niet “voor research”. Dat is fatsoen, geen herdefinitie van Engine.  
4. **Diepe safety/auth/ADR-berg:** niet de blocker voor M1/M2; wel relevant vóór echte hardware en productie.  
5. **`plan.md`:** waardevolle inventaris van contracts en latere fasen; waar de toon Engine verengt tot safety-runtime, wijkt 0.1-werk **niet** af van owner — het volgt `GOAL.md` en flagt de spanning.

Zo respecteer je zowel jouw “geen herschrijven” als de nuttige harde grenzen (niet de host slopen, niet alsof sim = certificaat).

---

## 7. Wat “goed” eruitziet over 1–3 weken

Niet meer docs. Wel:

1. **Hart-skelet** — Goal store, loop, persistent snapshot/experience, restart-test.  
2. **Tool-catalogus + FS-adapter** — sandbox only.  
3. **GeneralBrain port** — fixture die plant/kiest; zelfde port later LLM.  
4. **Één SpecialistBrain port** — bv. structure/path helper; aanroep via hart.  
5. **M1 oracle** — meerstaps FS-goal, autonoom, groen.  
6. **Sim-wereld op dezelfde lus** — M2.  
7. Korte note: shared vs. per-world — eerlijk, geen marketing.

Als stap 1–5 niet gebeuren omdat “eerst E00 threat model”, is de drift al bezig.

---

## 8. Scorecard (final)

| Dimensie | Score | Toelichting |
| --- | --- | --- |
| Conceptuele helderheid (owner) | **Hoog** | Hart/brein/tools/werkverdeling is bouwbaar |
| Onderscheid t.o.v. harness/agents | **Hoog** | Continuïteit + multi-brain + multi-world is de inzet |
| Interne doc-consistentie | **Middel** | `plan.md`/RULES trekken safety-first; `GOAL.md` trekt kern-first |
| 0.1-realiseerbaarheid | **Hoog** | Als scope = 2 sandbox-werelden + fixtures toegestaan |
| Research/productruimte | **Hoog** | Volledige Engine is niet “al gedaan” door HuggingGPT/CoALA |
| Huidige executierisico | **Hoog (negatief)** | Geen body; prose kan de aandacht opeten |
| Anti-drift gereedschap | **Goed** | `GOAL.md` is voldoende als owner het hard handhaaft |
| Klaar om te stoppen met her-analyseren | **Ja** | Volgende bewijs is code + oracle, niet `grok-*.md` |

---

## 9. Aanbeveling (één pad, geen herontwerp)

1. Behandel **`GOAL.md` als 0.1-contract**.  
2. Bouw **M1 → M2**; optioneel M3 (LLM in algemeen slot).  
3. Houd safety/governance als **bibliotheek voor later en als non-destruct hygiëne nu** — niet als herdefinitie.  
4. Wijzig `plan.md` alleen wanneer jij de toon wilt alignen; agents mogen dat niet “even fixen” tot jouw concept.  
5. **Stop concept-reviews** tot er een failing/passing oracle-run is. Deze `grok-final.md` is het einde van de Grok-analysereeks, niet het begin van een nieuwe filosofie.

---

## 10. Slotzin

Engine, zoals jij die bedoelt, is geen “veilige tool-host met optionele AI” en geen “kaal experiment zonder brein”.  
Het is een **levend besturings-en-cognitiesysteem**: hart voor continuïteit en handen, breinen voor keuze en specialisatie, tools voor de wereld.

Of dat een ding is, bewijs je niet met dikkere guardrails en niet met slimmere herformuleringen — maar met **één lus, twee werelden, oracles, en een herstart waarin Engine zichzelf nog kent.**

Daarna pas: bredere werelden, rijkere specialisten, mini-brain-consolidatie, en de safety-schil die *jouw* Engine buiten het lab mag dragen.

---

## Documenten in deze reeks

| Bestand | Rol |
| --- | --- |
| `grok.md` | Eerste conceptanalyse (deels verouderd in toon t.o.v. owner-lock) |
| `grok-deep.md` | Diepere brains-as-tools discussie (deels bruikbaar, mag niet herdefiniëren) |
| `GOAL.md` | **Actief 0.1-anker** — volg dit |
| `grok-final.md` | Deze final review — einde analysecyclus |

**Primair voor bouwen:** `GOAL.md`.  
**Primair voor latere schillen/contracts-inventaris:** `plan.md` + governance.  
**Primair voor “wat is Engine?”:** owner + `GOAL.md` §0.
