# Engine — one-pager positionering

> Status: builder / investor pitch. Geen herdefinitie van `GOAL.md`.  
> Datum: 2026-08-10.  
> Concurrentie-context: `threath.md`.

---

## One-liner

**Engine is the living control kernel for intentional action across software and physical worlds — hearts, brains, and typed capabilities owned outside any model session.**

Nederlands:

> Engine is de levende besturingskern voor intentionele actie over software- en fysieke werelden: hart, breinen en getypeerde capabilities die buiten elke modelsessie blijven bestaan.

---

## Probleem

Personal agents (OpenClaw, Hermes, coding harnesses) maken een model *actief* in chat, shell, browser en files. Dat is waardevol — en structureel ontoereikend zodra de vraag wordt:

- wat is de **waarheid** na een actie?
- wie **bezit** het doel als de provider sessie wegvalt?
- hoe blijft een doel **waar over tijd** (maintain), niet alleen “done in deze turn”?
- hoe bedien je **heterogene targets** (filesystem, sim, huis, later robot) met één lus zonder per domein een nieuw “agent product” te forken?

De markt optimaliseert op **wow in chat**. Production breaks op **epistemiek, continuïteit en multi-world control**.

---

## Oplossing

Engine scheidt wat de markt samensmelt:

| Scheiding | Betekenis |
| --- | --- |
| Proposal ≠ authority | LLM/specialist stelt voor; hart voert uit en boekt |
| Prediction ≠ observation | Effect is pas waar na onafhankelijke observe/oracle |
| Deliberation ≠ realtime | Hart is always-on deliberatief; hard-realtime blijft in target-controllers |
| Missing ≠ false | Geen telemetrie → `UNKNOWN`, geen stille ontkenning |
| State ≠ weights / prompt | Doelen, snapshots, receipts leven in Engine-store |

**Object van de runtime:** werelden en doelen — niet “de user in WhatsApp”.

```text
menselijk doel
  → GoalSpec (duurzaam)
  → Heart cycle (observe → think → act → observe)
  → general brain kiest specialist of world capability
  → receipt + post-state + oracle
  → ACHIEVE complete  |  MAINTAIN → quiet monitoring
```

---

## Wat 0.1 al bewijst (niet de productclaim)

- Eén **Heart** met duurzame goals, experience en SQLite-reconstructie na restart.
- **ACHIEVE** + **MAINTAIN** (monitor → drift → repair zonder model-spam op stabiele state).
- Algemeen brein-slot (deterministic + live local LLM) en specialist brains.
- Twee heterogene fixtures op dezelfde kern: sandbox filesystem + discrete grid.
- Homey/HomeOps-pluginpad: fail-closed act, re-observe ≠ HTTP ack, charter oracle.
- Generiek pluginleren is fake-world bewezen in zowel Homey als de
  warehouse-reference: dezelfde cursor/evidence/shadow/GoalSpec/rollback-route,
  met verschillende domeinbetekenis.
- Eerlijke evidence discipline (token-cuts gemeten; multi-brain pilot deels `INCONCLUSIVE`).

---

## Concurrentie in één adem

| | OpenClaw | Hermes | Engine |
| --- | --- | --- | --- |
| Categorie | Personal agent OS / gateway | Self-improving personal agent | World-acting control kernel |
| UX vandaag | Chat apps, minutes to magic | CLI/desktop + messaging | Kernel + plugin CLIs |
| State | Workspace + sessions | Skills + user model + memory | Goals, snapshots, receipts |
| Leren | Skills marketplace / ad-hoc | **Core product** (skill loop) | Getypeerde pluginervaring → begrensde GoalSpec-preference; mini-brain later |
| Fysiek multi-domain | Rand | Rand | **Structureel in de belofte** |
| Wint op | Ecosystem, distribution | Compounding workflows | Continuity, oracles, multi-world |

**We compete on a different axis.** Engine is not “better OpenClaw”.  
Engine is what you need when OpenClaw-class agents are the wrong abstraction for operational truth.

```text
        personal chat / tools
                ▲
    OpenClaw ───┼─── Hermes
                │
         software agents
    ────────────┼────────────
                │
              Engine
     heart + brains + worlds
     FS / sim / home / later body
```

---

## Wie het is voor

**Nu (builder):** teams die een local-first runtime willen waarin doelen, state en acties reconstrueerbaar zijn over model- en process-failure, met adapters als enige domein-specifieke laag.

**Later (product):** operators van software+home/edge systemen die “houd dit waar” nodig hebben — niet alleen “doe dit één keer vanuit chat”.

**Niet voor (nu):** wie in vijf minuten een Telegram-butler wil. Gebruik OpenClaw/Hermes. Eventueel later **vóór** Engine als intent-surface.

---

## Waarom nu

1. Agent-runtimes zijn commodity; **control semantics** zijn dat nog niet.
2. Fysiek/home/edge integraties via shell-MCP zijn ad-hoc en onbetrouwbaar als source of truth.
3. Regulation, audit en multi-tenant later eisen receipts/oracles die transcript-agents niet hebben.
4. Local models + edge make a durable heart economically viable without a vendor session.

---

## Business / adoptie (eerlijk)

| Fase | Wat we verkopen / openen | Wat we niet claimen |
| --- | --- | --- |
| 0.1 | Kernel + evidence + reference plugins | Universal safety, marketplace, “AGI butler” |
| 0.2 | Installable world plugins + conformance | Certification, hard-realtime control |
| 1.x | Operator product around maintain-goals | Replacement of PLCs / flight stacks |

Moat is niet “meer tools”. Moat is **typed multi-world lifecycle + observed truth + living goals**, plus de discipline om dat niet te verwateren tot chat-harness feature parity.

---

## Risico’s (expliciet)

| Risico | Mitigatie |
| --- | --- |
| Feature-creep naar OpenClaw | `GOAL.md` anti-drift; 30d roadmap locked op 0.1 identity |
| Paper-engine (docs > demo) | Done = R1–R3 demo + oracles, niet ADR-count |
| Twee kernels (v1/v2) | Eén canonical path freezen voor 0.1 cut |
| Under-adoption | Flagship Homey maintain demo als narrative; chat later optional |
| Safety theater blocks body | Safety parallel, not 0.1 identity (`GOAL.md`) |

---

## Ask / next

1. **Freeze 0.1** against `GOAL.md` I/B/W/H/R criteria.  
2. **Ship the decisive physical proof:** one bounded Homey lighting zone, five measured lux/watt loops.  
3. **Do not build** messaging gateway, skill marketplace, or self-writing skill OS in this window.

Detailplan: `docs/ROADMAP_30D.md`.

---

## Pitch in 20 seconden

> OpenClaw and Hermes made personal agents real. Engine is the next layer down: a heart that owns goals and world state, brains that only propose, and adapters that act — with independent observation deciding what actually happened. Same loop for files, sims, and homes. Models are replaceable organs. Continuity is not a prompt.
