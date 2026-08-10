# Grok-analyse: Engine-concept

> Status: conceptanalyse op basis van `plan.md`, `AGENTS.md`, `RULES.md` en `ARCHITECTURE_GUARDRAILS.md`.  
> Geen implementatieclaim. Datum: 2026-08-10.  
> Diepere uitwerking (inclusief “breinen als tools”): zie `grok-deep.md`.

---

## 1. Wat het concept is

Engine is een **lokale, capability-gebaseerde besturingsruntime** die menselijke intentie omzet in begrensde, getypeerde, auditeerbare acties op software én fysieke systemen.

De kernbelofte is niet “AI bestuurt alles”, maar:

> Eén veilige, auditeerbare control plane kan heterogene targets bedienen via expliciete capabilities, terwijl LLM’s optionele voorstellers blijven en policy/safety/executors de autoriteit houden.

Dat is een **product- en architectuurhypothese**, geen productclaim.

---

## 2. De thesis in één zin

**Scheiding van rollen is de productfeature.**  
LLM = voorstel. Runtime = waarheid, policy, autorisatie, receipt. Device controller = realtime. Safety plane = onafhankelijke stop.

Canonieke lifecycle:

```text
OBSERVE → PROPOSE → VALIDATE → POLICY → AUTHORIZE → DISPATCH → EXECUTE → OBSERVE → RECONCILE → RECORD
```

---

## 3. Wat sterk is

### 3.1 Correcte reactie op de agent-hype

| Val | Engine-antwoord |
| --- | --- |
| Chat = state | `WorldSnapshot` + provenance |
| Model = authority | `ProposedAction` ≠ `Authorization` |
| Model = success | onafhankelijke observatie / `UNKNOWN` |
| Retry = safe | idempotency + crash recovery |
| Sim = certified | expliciet verboden generalisatie |
| Alles is één actieschema | lifecycle generiek, semantiek per target |

Intellectueel stevig; past bij systemen waar fouten duur of gevaarlijk zijn.

### 3.2 Drie-vlakkenarchitectuur

1. **Deliberatieve control plane** — doelen, policy, audit (menselijke tijdschaal)
2. **Device/data plane** — adapters, telemetrie, lokale controllers
3. **Onafhankelijke safety plane** — e-stop, interlocks, fail-closed

Industriële control-thinking toegepast op LLM-workflows — precies waar de markt vaak te licht is.

### 3.3 Falsifieerbare eerste slice

0.1-claims zijn smal en meetbaar:

1. twee adapters, zelfde lifecycle/contracts
2. LLM volledig vervangbaar door fixtures
3. replay = materialization
4. deny stale/unauth/malformed vóór execution
5. effect nooit uit modeltekst afgeleid

Je kunt falen zonder het hele verhaal te moeten redden.

### 3.4 Umwelt-boundary is helder

Engine mag zonder Umwelt werken; Umwelt is optionele world-model/planning via `WorldModelPort`.  
Geen shared DB, geen circulaire core-dependency.

### 3.5 Governance is al volwassen

`AGENTS.md`, `RULES.md`, guardrails, preregistered gates, stop conditions, ADR-policy: zwaarder dan de code, passend bij safety-adjacent software.

---

## 4. Fragiliteit en zwaarte

### 4.1 De generieke-runtime-val

Hypothese is weerlegd wanneer apparaatverschillen zoveel special-case vragen dat alleen een dunne logginglaag overblijft, of wanneer bestaande domeinruntimes + kleine integraties eenvoudiger en veiliger zijn.

**Risico:** elegante meta-runtime die in elk domein verliest van een dunne, domeinspecifieke adapter.  
**Mitigatie in plan:** filesystem → sim-arm → één low-energy arm; nooit generieke robotica claimen. Product-why (wie, welk pijnprobleem) is nog open.

### 4.2 Contractoppervlak groot vóór eerste waarde

~15 canonieke types, 4 testlagen, 10+ gates, 11 tickets. Voor P1 mogelijk over-engineered; voor P3 mogelijk te licht op safety-engineering.

**Aanbeveling:** P1 bevriest een minimale subset (`Observation`, `ActionRequest`, `PolicyDecision`, `Authorization`, `ExecutionReceipt`, snapshot-binding); rest bij adapter #2 of hardware.

### 4.3 Authorization UX ondergespecificeerd

Technisch (scoped, expiring, deny-by-default) is correct. Productmatig: wie approvet, hoe, wat “exact action class” betekent voor een mens — open. Zonder goede UX: te veel prompts of te brede session allows.

### 4.4 Local-first vs. multi-device reality

Sterk voor privacy/edge/offline. Multi-host, remote telemetry, multi-user approval, skill distribution duwen naar netwerk en trust boundaries — terecht out of 0.x scope, maar bepalen later of Engine edge daemon, desktop orchestrator of platform is.

### 4.5 Mini-brains te vroeg in de narrative

P4 “alleen na baseline-bewijs” is correct; marketing moet de eerste story houden op typed capabilities + policy + receipts + replaceable proposers.

### 4.6 Simulator fidelity-trap

Sim-arm bewijst lifecycle, niet physical safety. Gate E10 (is hardware verantwoord?) moet hard blijven.

---

## 5. Positionering

| Vergelijkbaar met | Verschil |
| --- | --- |
| Agent frameworks | Engine weigert recursive agent loop als core control |
| Tool-calling LLMs | Tools krijgen geen self-auth; receipts + observation first-class |
| ROS / robot middleware | Engine is deliberatief + policy, niet realtime control stack |
| Home automation | Rijkere evidence grades, authorization, replay/oracle |
| Policy engines | Plus execution, adapters, effect reconciliation |
| World models (Umwelt) | Engine voert uit; Umwelt modelleert/plant optioneel |

**Eerlijke positionering:** trust & execution fabric voor mixed software/physical actions, met LLMs als pluggable intent-layer — niet “robot brain” of “autonomous agent” in de marketing-zin.

---

## 6. Producthypothese

**Meest overtuigende first wedge:** software-werelden (sandbox, ops, data movement, desktop automation) waar acties rollbackbaar zijn en policy/audit al pijn doen.

**Moeilijkste wedge:** fysieke robots — architectuur juist, liability en domain semantics zwaar.

**Falsificatiepad is geloofwaardig.**

---

## 7. Open beslissingen (kritiek)

1. Eerste concrete gebruiker + use-case
2. Max impact fysieke pilot
3. Event-sourced vs snapshot+log
4. Approval principal model
5. Licentie/distributie van skills

Zolang (1) open is, is implementatie-risico hoger dan architectuur-risico.

---

## 8. Oordeel

| Dimensie | Score | Commentaar |
| --- | --- | --- |
| Intellectuele scherpte | Zeer hoog | Scheidingen precies en consistent |
| Safety-denken | Zeer hoog | fail-closed, independent stop, sim≠cert |
| Implementeerbaarheid 0.1 | Hoog *als* scope strak | E00–E07 in weken haalbaar |
| Product-market fit | Onbewezen | use-case nog open |
| Over-abstractierisico | Middel–hoog | grote vocabulary vóór first adapter |
| Differentiatie | Sterk als trust fabric | Zwak als “generic robot OS” |

**Samenvatting:** sterk, disciplinevol concept voor “hoe laat je AI meewerken zonder het de waarheid of de actuator te geven”. Grootste dreiging is niet technische naïviteit, maar generiek-worden zonder first user, of te veel contractoppervlak vóór meetbare waarde.

---

## 9. Aanbevolen focus (baseline uit analyse)

1. Eén primary use-case kiezen vóór type-explosion
2. P0: threat model + frozen lifecycle + sealed 0.1 gates
3. P1 zonder LLM: filesystem + deny-by-default + replay + crash recovery
4. Daarna sim-arm + optionele LLM achter hetzelfde proposal-contract
5. Story: proposal fabric + execution authority

---

## 10. Spanning die dieper moet (doorverwijzing)

De owner heeft frictie met:

- “human stap eerst” als productnarratief, en
- “geen AI brain” als te restrictieve framing,

en trekt richting: **Engine mag wel een AI-brein-achtige laag zijn — mits breinen tools zijn, met contracts, limieten en audit.**

Die spanning is **niet** “safety loslaten vs. AI verbieden”. Het is een **rolmodel- en productpositioneringsvraag**:

- Is Engine een **mens-gestuurde runtime met optionele AI-voorstellen**?
- Of een **AI-gestuurde runtime met verplichte non-AI authority bounds**?
- Of een **toolbox van breinen** achter één execution fabric?

Die uitwerking staat in **`grok-deep.md`**.
