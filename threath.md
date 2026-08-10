# Engine t.o.v. OpenClaw en Hermes

> Status: positionering / concurrentie-bewustzijn.  
> Geen herdefinitie van Engine. Owner-lock en `GOAL.md` blijven leidend.  
> Datum: 2026-08-10.

Kort: **OpenClaw en Hermes zijn (2026) de dominante open personal/dev-agent stacks.** Engine deelt met hen de *agent-runtime*-golf, maar mikt op een **andere primair object**: een levend hart+brein over **meerdere werelden (software én fysiek)**, niet op “persoonlijke assistent in je chats/terminal”.

---

## 1. Wat OpenClaw en Hermes zijn

### 1.1 OpenClaw — “Agent OS” / gateway-runtime

OpenClaw is een **self-hosted personal AI assistant-runtime**: embedded agent-loop, tool wiring, prompt assembly, sessions, skills, multi-channel delivery (WhatsApp, Telegram, …) achter een **gateway-daemon** (hub-and-spoke).

| Aspect | OpenClaw |
| --- | --- |
| Centrum | Gateway + embedded agent runtime |
| Wereld | Desktop/software: files, shell, browser, messaging |
| State | Workspace (`AGENTS.md`, `MEMORY.md`, …) + session SQLite/JSONL |
| Skills | Hot-reload, ClawHub marketplace |
| Productclaim | Runtime is het product; model is verwisselbaar |
| Sterkte | Breed ecosysteem, kanalen, “always-on assistant” |
| Zwakte (publiek) | Vroege permissive defaults, CVEs, supply-chain rond skills |

Architectuur-leesregel: **control plane voor berichten + tools + sessions** — dichter bij “Claude Code / agent harness als OS” dan bij robot/world control.

### 1.2 Hermes Agent (Nous Research) — learning-loop agent

Hermes is een **self-improving agent framework**: execute → reflecteer → distilleer **skills uit ervaring** → verfijning → retrieval; plus **user modeling** over sessies. CLI-first, optionele gateway, container backends, skill-curator.

| Aspect | Hermes |
| --- | --- |
| Centrum | Learning loop + skill library |
| Wereld | Zelfde klasse als OpenClaw (tools, terminal, browser, messaging) |
| State | SQLite memory, pluggable memory, skills als procedureel geheugen |
| Skills | Agent-managed: create/update; curator; self-evolution (aparte pipeline) |
| Productclaim | Agent wordt beter op *jouw* workflows over tijd |
| Sterkte | Ervaring → herbruikbare procedures (dicht bij Engine’s mini-brain-groeipad) |
| Zwakte | Jonger ecosysteem; nog steeds vooral *software-agent*, geen multi-world body |

---

## 2. Naast Engine (zonder herdefinitie)

Owner-lock (`GOAL.md`):

> Engine = **hart** (doelen, lus, state, ervaring, continuïteit) + **algemeen brein** + **specialisten** + **gedeelde wereldtools** — levend systeem dat denkt, ervaart en handelt; mens niet per stap; safety definieert Engine niet.

| Dimensie | OpenClaw | Hermes | **Engine (owner-concept)** |
| --- | --- | --- | --- |
| Primaire metafoor | Agent OS / gateway assistent | Self-improving personal agent | **Levend hart + multi-brein over werelden** |
| Wat “draait” | Daemon + chat/session turns | Agent loop + skill loop | **Hart-lus met duurzame goals/state** |
| Intelligentie | Meestal 1 model (+ subagents) | 1 agent + skill library | **Algemeen brein kiest specialisten + tools** |
| Tools | Built-in + skills marketplace | Tools + agent-written skills | **Engine-owned world catalog; specialisten mogen interne tools** |
| Geheugen | MEMORY.md / semantic / sessions | Skills + user model + FTS | **World state + ervaring/receipts als hart-eigendom** |
| Werelden | Software/personal (files, chat, browser) | Idem | **Heterogeen: FS + sim + later fysiek** in één kern |
| Continuïteit | Sessions, cron, workspace | Cross-session skills/user model | **Goals/state overleven modelcalls én process restart** |
| Leren | Beperkt in-framework | **Kernproduct** (skill distillatie) | Groeipad (ervaring → mini-brain); **niet 0.1-blocker** |
| Observatie/waarheid | Tool results in transcript | Outcomes + skill eval | **Receipt + post-state/oracle, niet model-self-report** |
| Fysiek / multi-domain body | Nee (niet de inzet) | Nee | **Ja, structureel in de belofte** |
| Mens in de loop | Chat-gestuurd; approvals later/hardened | Approvals/YOLO-modes | **Charter/start ok; niet elke cyclus** |

---

## 3. Overlap (zelfde “golf”)

Alle drie antwoorden op:

> Hoe wordt een model *iets dat doet*, met tools, geheugen en een loop — lokaal, model-agnostisch?

Concreet gedeeld:

1. **Runtime > model** — OpenClaw zegt dat hard; Hermes en Engine ook.
2. **Tools + skills** — aanroepbare capabilities buiten pure chat.
3. **Persistentie over turns** — sessions / memory / skills.
4. **Lokaal / self-host** — edge-vriendelijk verhaal.
5. **Hermes ↔ Engine mini-brain-pad** — “eerst duur redeneren, later procedure consolideren” is architecturaal **het dichtst bij Hermes’ skill-loop**, niet bij OpenClaw’s marketplace-first skills.

Als iemand Engine reduceert tot “nog een agent met tools”, klinkt het als OpenClaw/Hermes — en dan is de markt al vol.

---

## 4. Verschil (waar Engine *niet* OpenClaw/Hermes is)

### 4.1 Object van de runtime

| | |
| --- | --- |
| OpenClaw / Hermes | **Persoon + software-acties** (berichten, repo, browser, shell) |
| Engine | **Werelden**: getypeerde targets, multi-domain state, later apparaten |

OpenClaw’s “workspace” is agent-cwd + markdown-geheugen.  
Engine’s “world state” is **operationele toestand van targets** (FS-structuur, sim-arm pose, later sensoren) die het hart bezit — niet “wat er in MEMORY.md staat over de user”.

### 4.2 Hart vs. harness

OpenClaw positioneert zich als embedded runtime t.o.v. external harness — maar de loop blijft **agent-turn / channel / session**-centraal.

Engine’s hart is strenger:

- doelen leven buiten de modelsessie;
- aandacht/events kunnen de lus voeden;
- herstart zonder provider-memory mag de wereld niet wissen;
- brein is orgaan, geen enige eigenaar van continuïteit.

**OpenClaw ≈ sterke harness-runtime voor assistants.**  
**Engine ≈ body+mind voor world-acting** (assistant kan een *modus* zijn, niet de definitie).

### 4.3 Multi-brein is bij Engine first-class architectuur

OpenClaw: multi-agent routing, subagents, ACP — vooral **meerdere assistent-instances / threads**.  
Hermes: multi-agent + skill libraries per specialist — dichterbij, nog steeds **agent-framework**.

Engine: **één hart**, algemeen brein **kiest** vision/code/motion/… als specialisten, wereldtools zijn van Engine. Dichter bij HuggingGPT/MRKL-compositie *binnen* één levend systeem dan bij “twee Telegram-bots”.

### 4.4 Leren: Hermes is de naaste buur — niet de vervanging

| | Hermes | Engine |
| --- | --- | --- |
| Wat wordt geleerd | Skills (procedures/docs), user model | Ervaring; later mini-brains als **geregistreerde capabilities** |
| Wanneer | In-product loop vanaf dag 1 | Groeipad; 0.1 mag fixture-breinen |
| Waarheid na actie | Outcome/feedback | **Onafhankelijke observatie + oracle** op world state |

Hermes bewijst dat “ervaring → skill” product-waarde heeft.  
Engine mag dat **absorberen als later orgaan**, zonder Hermes *te worden* (user-modeling personal assistant).

### 4.5 Safety-verhaal is omgekeerd gepositioneerd

OpenClaw: product-first, security deels reactief (CVE’s, marketplace-incidenten).  
Hermes: meer layered approvals/containers als design.  
Engine-docs historisch: zware safety-constitutie **vóór** body — gecorrigeerd door `GOAL.md` (kern eerst; safety definieert Engine niet).

Voor Engine 0.1 telt: niet “wie de meeste security-lagen claimt”, maar of de **levende lus op twee werelden** bestaat. OpenClaw/Hermes zijn al “dingen in de software-assistant-categorie”; Engine’s open vraag is multi-world hart+brein.

---

## 5. Positioneringsdiagram

```text
                    personal chat/tools
                            ▲
                            │
              OpenClaw ─────┼──── Hermes
              (gateway OS)  │    (learn skills)
                            │
                     software agents
                            │
        ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┼ ─ ─ ─ ─ ─ ─ ─ ─ ─
                            │
                     Engine (owner-inzet)
              hart + multi-brein + world tools
              FS / sim / later fysiek
              state & ervaring van de runtime
                            │
                            ▼
                   multi-world action
```

- **Horizontaal** bij OpenClaw/Hermes: *wie is de beste personal/dev agent?*
- **Verticaal** bij Engine: *bestaat er één levend systeem dat over heterogene werelden denkt en handelt?*

Die assen overlappen in software-sandbox, maar **vallen niet samen**.

---

## 6. Dreigingen en kansen (threat landscape)

### 6.1 Dreiging: category collapse

Als Engine 0.1 vooral wordt:

- gateway + LLM + shell/fs tools + markdown memory

…dan is Engine **laat OpenClaw/Hermes**, met minder ecosystem.

**Anti-middel:** `GOAL.md` M2 (tweede *ongelijksoortige* wereld + zelfde hart) en anti-harness I1–I4.

### 6.2 Dreiging: “gewoon Hermes/OpenClaw erop zetten”

Hermes of OpenClaw als *algemeen brein* achter een dunne tool-laag = slim, maar dan **is die runtime het hart** en Engine de adapter.

Dat botst met “Engine is het levende systeem”.

**Toegestaan:** Hermes/OpenClaw-model als **één brain-adapter** achter Engine’s Brain-port — hart blijft van Engine.

### 6.3 Dreiging: feature-jacht op hun speelveld

Telegram-adapters, ClawHub-achtige marketplaces, user-modeling personalization — winnen op *hun* as en vertragen M1/M2.

**Anti-middel:** die features pas ná bewezen multi-world hart, of expliciet als optionele schil.

### 6.4 Kans: scherpe differentiatie in één zin

> OpenClaw is de **assistent-OS** (kanalen, sessions, skills marketplace).  
> Hermes is de **lerende personal agent** (ervaring → skills).  
> Engine is het **hart-en-brein voor handelen in meerdere werelden** — software nu, fysiek later — met specialisten en tools onder één continuïteit.

### 6.5 Kans: leren van beiden zonder te kopiëren

| Van | Neem over (patroon) | Niet overnemen als identiteit |
| --- | --- | --- |
| OpenClaw | Model-swappable runtime, skill packaging, long-running process | Chat-gateway als centrum van Engine |
| Hermes | Skill distillatie na succes; curator; experience compounds | “User model” als kern-IP van Engine |
| Beide | Provider-agnostic, local-first, tool receipts in practice | Marketplace/CVE-theater vóór M1 |

---

## 7. Hoe staat dit in verhouding? (samenvatting)

1. **Zelfde tijdperk** — agent runtimes die meer willen zijn dan een chat-wrapper.
2. **Niet dezelfde productcategorie** — zij optimaliseren *personal/dev agent experience*; Engine *levend multi-world action system*.
3. **Hermes is conceptueel dichter** op Engine’s ervaring→specialist/mini-brain-pad dan OpenClaw.
4. **OpenClaw is productmatig dichter** op “runtime is the product / model swappable” en always-on daemon — nuttig als *referentie voor packaging*, gevaarlijk als *blueprint voor identiteit*.
5. **Engine wint of verliest** niet op ClawHub-skills of Telegram-adapters, maar op: **één hart, brein+specialisten, duurzame world state, twee heterogene werelden, oracle — zonder mens per stap** (`GOAL.md`).
6. **Gebruik ze als concurrentie-bewustzijn en optionele brain/channel-adapters**, niet als herdefinitie van Engine en niet als excuus om alleen software-assistant te blijven.

---

## 8. Praktische leesregel

| Als je denkt… | Check |
| --- | --- |
| “We bouwen OpenClaw maar veiliger” | Drift — dat is hun product |
| “We bouwen Hermes maar met robots” | Dichterbij, nog te smal: hart + multi-world contracts ontbreken |
| “We bouwen de lus die OpenClaw/Hermes niet centreren: world state + multi-domain body + multi-brain onder één hart” | **On-concept** |

**Bottom line:** OpenClaw en Hermes bewijzen dat de markt **agent-runtimes** wil. Zij vullen de *assistant*-hoek. Engine, zoals ge-locked in `GOAL.md`, claimt de *world-acting living system*-hoek. Overlap is reëel in FS/tools/LLM; **differentiatie is pas geloofwaardig na M2** — niet na meer vergelijkingsessays.

---

## 9. Uitvoerbare anti-clonepoort voor World Plugin v2

Positionering telt vanaf v2 alleen wanneer deze criteria als tests of bewaarde
run-artifacts aantoonbaar zijn. Een groene tool-call-demo is geen vervanging.

| ID | Releasepoort | Verplicht bewijs | No-go |
| --- | --- | --- | --- |
| AC1 | Goal buiten chat/modelsession | restarttest hervat dezelfde `GoalSpecV2` uit Engine SQLite zonder providergeheugen | doel verdwijnt of wordt uit transcript herbouwd |
| AC2 | Plugin levert een wereld | conformance toont entities, relations, observations, coverage en effectoracle | plugin levert alleen functienamen/JSON-tools |
| AC3 | Heart is geen recursive agentloop | stabiele `MAINTAIN`-run doet exact nul algemene én specialistmodelcalls | ieder poll/event start een modelturn |
| AC4 | Semantiek blijft domeineigen | dezelfde Heart-code bestuurt Homey-fake en warehouse/grid-reference | `if homey`, kamer- of merkstrategie in `src/engine/**` |
| AC5 | Brain kiest, maar verzint geen lichaam | voorstel verwijst naar bestaande capabilityfamilie; controller maakt exact request | LLM roept willekeurige fysieke API of raw setpoint aan |
| AC6 | Effect is waargenomen | ACK-zonder-post-effect eindigt niet succesvol | ACK/modeltekst geldt als goal completion |
| AC7 | Events zijn aandacht, geen waarheid | gemist/duplicaat event wordt door verse poll-observatie gereconcilieerd | eventpayload wordt canonieke state |
| AC8 | Nieuwe wereld zonder tweede Heart | gegenereerde niet-huiselijke plugin haalt `MAINTAIN` closed loop zonder corepatch | tweede plugin vereist nieuwe runtime/lus |
| AC9 | Capabilitygroei is data/contract | nieuwe instance van enrolled family werkt zonder kamer-/merkcode; onbekende family blijft read-only | dynamische API-discovery verleent automatisch mutatierecht |
| AC10 | Ervaring is outcome-grounded | expliciete correctie wijzigt volgende equivalente keuze; inferred gewoonte passeert vaste evidence+shadowpoort | promptmemory of één handmatige override wordt policy |

### Verplichte benchmarkvelden

De vergelijkende fake-world run tegen vastgezette OpenClaw- en Hermes-versies
schrijft minimaal deze ruwe waarden weg: doelcontinuïteit na restart/providerreset,
gemiste events, foutieve succesclaims bij ACK-zonder-effect, modelcalls en tokens in
stabiele uren, mensinterventies, reactietijd, effect-/budgetresultaat, nieuwe zone
zonder code en overdracht naar de reference-world. Versies, fixtures, operaties en
budgets worden vóór de beslissende run vastgezet; negatieve uitkomsten blijven in
het artifact staan.

### Interpretatie

Engine hoeft niet sneller of goedkoper te zijn op iedere metric. De v2-slice is
wel een mislukte kleinere kloon bij één foutieve succesclaim, verloren doel/state,
modelcalls in stabiele toestand, mutatie buiten enrollment, per-zone maatwerk of
een tweede Heart-architectuur. Deze poort meet eerst of het levende concept werkt;
productiehardening en fysieke certificering zijn geen voorwaarde voor deze fake-
world proof.

---

## 10. Gerelateerde docs

| Bestand | Rol |
| --- | --- |
| `GOAL.md` | 0.1-anker; winconditie t.o.v. category collapse |
| `plan.md` | Langere product-/contractinventaris |
| `grok-final.md` | Eindoordeel concept/realisatie |
| `threath.md` | Dit document — OpenClaw/Hermes threat & positionering |
