# GOAL — Engine 0.1 realisatie (anti-drift)

> Status: actief anker.  
> Dit document **definieert niet opnieuw** wat Engine is. Het legt vast *welk doel* de eerste realisatie haalt, en *wat telt als afwijken*.  
> Conceptbron: owner-intentie + `plan.md`. Bij conflict wint de owner-uitleg van Engine als levend systeem (hart én brein).  
> Analyses en agentnotities zijn commentaar; zij mogen dit doel niet stilletjes vervangen.

---

## 0. Wat Engine is (niet onderhandelbaar in dit goal)

Engine is **het volledige levende systeem** — hart én intelligentie — dat denkt, ervaart en handelt over software- en fysieke werelden.

```text
ENGINE
├── Hart
│   ├── actieve doelen
│   ├── event-/cognitielus
│   ├── aandacht en prioriteiten
│   ├── duurzame world state
│   ├── ervaring en geheugen
│   └── voortgang en continuïteit
│
├── Algemeen brein
│   ├── begrijpt situaties
│   ├── vormt plannen
│   ├── kiest tools
│   └── kiest specialistische breinen
│
├── Specialistische breinen
│   ├── vision / code / planning / beweging / …
│   └── (interne cognitieve tools mogen verborgen blijven)
│
└── Tools (gedeelde wereldtools van Engine)
    ├── filesystem, browser/API, simulator, sensoren, apparaten, …
```

**Werkverdeling (vast):**

1. Het **algemene brein** redeneert en kiest (o.a. specialist of wereldtool).
2. Het **hart** houdt doelen, state, ervaring en de cyclus levend; bouwt context; voert aanroepen uit; bewaart resultaten.
3. **Specialistische breinen** leveren begrensde cognitieve outputs.
4. **Wereldtools** veranderen of observeren de wereld; Engine bezit de gedeelde catalogus.
5. Een **mens hoeft niet iedere cyclus** te starten of goed te keuren.
6. **Safety/autorisatie** kunnen later of parallel bestaan; zij **definiëren Engine niet**.
7. **Mini-brains** zijn een groeipad (ervaring → consolideren → registreren), **niet** de voorwaarde voor 0.1.

**Engine is niet:**

- alleen een harness (model + tools per beurt, zonder eigen continuïteit);
- alleen een workflow-engine;
- alleen een policy/safety-laag;
- een systeem dat pas “Engine” is als alle guardrails af zijn.

**Korte identiteitszin:**

> Engine is het levende systeem waarin breinen en tools samen kunnen denken, ervaren en handelen — met één hart dat continuïteit, state en aanroepen organiseert, en intelligentie die kiest wat nodig is.

---

## 1. Het doel (één zin)

**Realiseer Engine 0.1 als werkend hart-én-brein:** één duurzame cognitieve lus die, met een algemeen brein, minstens één specialistisch brein (mag deterministic/fixture zijn), gedeelde wereldtools en blijvende state/ervaring, **zonder mens per stap** meerstapsdoelen voltooit in **minstens twee heterogene** sandbox-/simulatiewerelden — en aantoont dat die werelden dezelfde kern delen.

---

## 2. Klaar-definitie (Done = dit alles waar)

### 2.1 Identiteit bewezen (anti-harness)

| # | Criterium | Fail als… |
| --- | --- | --- |
| I1 | Doelen blijven bestaan over modelaanroepen en over minstens één procesherstart | goal leeft alleen in de prompt/sessie |
| I2 | World state is duurzaam en van Engine, niet “wat het model zich herinnert” | herstart of leeg context → vergeten wereld |
| I3 | Ervaring/receipts beïnvloeden latere keuzes in dezelfde run (en na herstart waar relevant) | elke stap is amnesie + nieuwe chat |
| I4 | Hart kan de lus voortzetten op events/voortgang/budget, niet alleen op menselijke “enter” | geen run zonder continue mens-impuls |
| I5 | Algemeen brein kiest tool- of specialist-aanroepen; hart voert uit en boekt resultaat | ad-hoc scripts buiten de lus, of pure tool-router zonder doelen/state |

### 2.2 Intelligentie als onderdeel van Engine (anti-“LLM optional identity”)

| # | Criterium | Fail als… |
| --- | --- | --- |
| B1 | Er is een **algemeen brein**-slot in de kern (echte LLM en/of sterke fixture die dezelfde interface deelt) | intelligentie alleen als los script naast de runtime |
| B2 | Minstens **één specialistisch brein** is aanroepbaar via de kern (mag fixture: bv. “ranker”, “path helper”, “structure checker”) | alleen platte tools, geen brain-selectie |
| B3 | Zelfde goal-run kan **algemeen → specialist → wereldtool → observe → verder denken** doorlopen | één-shot tool call zonder cognitieve cyclus |
| B4 | Specialistische output en tool-output landen in Engine-state/ervaring met herleidbare herkomst | resultaten verdwijnen in transcript |

### 2.3 Twee werelden, één kern (anti-glue-fork)

| # | Criterium | Fail als… |
| --- | --- | --- |
| W1 | Wereld A: sandbox-filesystem (of gelijkwaardige software-wereld) met meerstaps goal + oracle | alleen toy print-demo |
| W2 | Wereld B: discrete sim (grid / sim-arm / pick-place) met meerstaps goal + oracle | B is copy-paste fork van A’s “runtime” |
| W3 | **Zelfde** hartlus, goal-representatie, brain-aanroeppad, tool-catalogusmechanisme, state/ervaring-boeking | twee programma’s met gedeelde mapnaam |
| W4 | Domeinverschil zit in **adapters/tools/specialisten**, niet in een tweede cognitieve architectuur | “Engine-FS” en “Engine-Arm” als aparte productgeesten |

### 2.4 Handelen + waarheid van effect (zonder safety-theater als blocker)

| # | Criterium | Fail als… |
| --- | --- | --- |
| H1 | Elke wereldmutatie levert een **receipt** + **observatie/post-state** (of expliciet onbekend) | succes = model zegt “done” |
| H2 | Goal completion wordt door **oracle/state** bepaald, niet door self-report van het brein | demo-transcript als bewijs |
| H3 | Minstens één gecontroleerde partial/failure-path is zichtbaar in state (tool faalt / half resultaat) en de lus reageert | stille halfstaat |

### 2.5 Bewijs dat dit “een ding” is (niet de productclaim)

| # | Criterium | Fail als… |
| --- | --- | --- |
| R1 | Eén demo-script/commando (of kleine suite) draait beide werelden op de **gedeelde kern** | alleen handmatige losse stappen |
| R2 | Korte written note: wat de kern deelt vs. wat per wereld uniek is (eerlijk) | claim “universeel” zonder splitsing |
| R3 | Owner kan de run zien: goal in → autonome stappen → goal met oracle uit | alleen architectuurpraat |

**Niet required voor dit goal (mag bestaan, mag niet blokkeren):**

- volledige policy/auth matrix, multi-tenant isolation, skill signing;
- hardware e-stop plane, fysieke arm;
- Umwelt-integratie;
- getrainde mini-brains;
- productie-UI;
- “veilig genoeg voor de wereld”-certificering.

Sandbox-isolatie (temp dir, geen host-ruïne) is hygiëne, geen identiteitsdefinitie.

---

## 3. Succeszin (wat je op dag X mag zeggen)

> Engine 0.1 bestaat: het hart houdt doelen, state en ervaring vast; het algemene brein plant en kiest; minstens één specialist en gedeelde tools worden via het hart aangeroepen; twee verschillende werelden worden door **dezelfde** levende lus bestuurd; meerstapsdoelen slagen op oracles zonder mens per stap.

Als je dat niet hardop en demo-baar kunt zeggen, is het goal niet gehaald — ongeacht hoeveel guardrail-docs er staan.

---

## 4. Anti-driftregels (hard)

Iedere contributor/agent **moet stoppen en expliciet maken** bij neiging tot:

| Drift | Verboden stille herschrijving | Toegestaan alleen als… |
| --- | --- | --- |
| D1 Safety-first lege kern | “Eerst wet/auth/crash-oracles, daarna denken” als 0.1-pad | owner zet safety-track **naast** of **na** dit goal |
| D2 Research-kernel only | Engine reduceren tot observe/propose/execute zonder hart/brein-identiteit | owner vraagt smalle meting; concept blijft staan |
| D3 Harness-only | “Gewoon LLM + tools zoals Claude Code” als eindtoestand 0.1 | tijdelijke steiger, met I1–I4 nog open |
| D4 Human-every-step | Elke actie vereist mens | high-risk later; niet default 0.1 |
| D5 Brain buiten Engine | Intelligentie als los product naast “dumb runtime” | interface-grenzen, maar intelligentie hoort bij Engine |
| D6 Twee Engines | Per wereld een nieuwe architectuur | adapter/specialist, zelfde hart |
| D7 Paper-Engine | Alleen docs/ADR’s als voortgang | code + demo + oracle |
| D8 Concept rewrite | Nieuwe one-liner die hart/brein/tools vervangt | **nooit** zonder owner |

**Regel:** analyses mogen **bevragen en meten**. Zij mogen Engine **niet herdefiniëren**. Twijfel → voorleggen aan owner, niet “verbeteren” in stilte.

---

## 5. Realisatiepad (alleen volgorde, geen herdefinitie)

Doel is realisatie van **jouw** Engine, zo smal mogelijk in *scope van werelden*, zo volledig mogelijk in *identiteit*.

```text
G0  Bevries dit GOAL.md als anker (nu)
G1  Hart-skelet: Goal + loop + duurzame state + experience/receipt log
G2  Tool-catalogus + één FS-wereldadapter (sandbox)
G3  Algemeen-brein interface + minstens fixture-brein dat plant/kiest
G4  Eén specialist-brein interface + aanroep via hart (fixture mag)
G5  Meerstaps FS-goal end-to-end op oracle, zonder mens per stap
G6  Tweede wereld (sim) op ZELFDE hart/brain/tool-mechanisme
G7  Meerstaps sim-goal + herstart-continuïteit-demo
G8  Optioneel: echt LLM in algemeen-brein-slot (zelfde interface)
G9  Goal review met owner: done of expliciete scope-cut
```

Safety-docs en bredere `plan.md`-fasen blijven referentie voor **latere** schillen. Zij **vervangen G1–G7 niet** als eerste finish line.

---

## 6. Eerste meetbare milestone (binnen dit goal)

**M1 — “Eén wereld leeft”**  
FS-sandbox: goal in, hart-lus, algemeen brein (fixture of LLM), ≥1 specialist-aanroep of bewuste skip met reden in experience, tools, receipts, oracle-pass, herstart behoudt goal+state.

**M2 — “Twee werelden, één Engine”**  
Zelfde binaire/package: sim-wereld erbij; tweede oracle-pass; geen tweede architectuur.

**M3 — “Brein is van Engine”**  
LLM of sterke fixture in algemeen slot; aantoonbaar tool- en specialist-keuze; state niet in provider-memory required.

M1 alleen = voortgang.  
M2 = kern van “is dit Engine?”.  
M3 = intelligentie-identiteit hard.

---

## 7. Owner-lock

- **Concept owner:** project owner (jij).  
- **Dit goal wijzigen:** alleen owner.  
- **Agents:** implementeren en meten tegen §2; bij spanning met `plan.md`/analyses: **GOAL.md + owner-concept winnen voor 0.1-richting**; constitutionele safety-regels voor *echte* schade/outward actions blijven gelden als gedragsgrenzen voor contributors, niet als excuus om de cognitieve kern uit te stellen.

---

## 8. Eén checkvraag bij elke PR / agent-sessie

> Brengt dit de **levende lus** (hart + algemeen brein + tools/specialisten + state/ervaring + doelvoltooiing op ≥1 wereld dichter bij M2) — of bouwen we opnieuw een schil, harness of herdefinitie?

Zo nee: niet mergen als “Engine 0.1 voortgang” zonder owner-ok.
