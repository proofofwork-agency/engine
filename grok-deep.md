# Grok deep-dive: Engine, “AI brain”, en breinen-als-tools

> Diepere uitwerking bij `grok.md`.  
> Bronnen: `plan.md`, `AGENTS.md`, `RULES.md`, `ARCHITECTURE_GUARDRAILS.md`.  
> Inclusief owner-frictie: weerstand tegen “human first” / “geen AI brain”, voorkeur voor Engine als (ook) AI-brein via tools en begrensde breinen.  
> Status: conceptanalyse en ontwerpopties — geen ADR, geen implementatieclaim.

---

## 0. Waarom deze deep-dive

De baseline-analyse in `grok.md` leest Engine als:

> trust & execution fabric; LLM is optionele proposal provider; mens en policy houden authority.

Dat is **trouw aan de huidige documenten**. Het is niet per se de enige productlezing die de *scheidingen* intact houdt.

De owner-frictie is scherp:

1. **“Human stap eerst” voelt verkeerd** als product- en gebruikersmodel — te veel alsof Engine wacht tot een mens elke zet bedenkt.
2. **“Geen AI brain” voelt te smal** — alsof intelligentie buitengesloten is, terwijl de intentie juist is: Engine *mag* slim zijn, zolang slimheid geen eigen autoriteit, waarheid of realtime control claimt.
3. **Voorkeursbeeld:** breinen (LLM’s, planners, mini-brains, tools) zijn **capabilities/tools** die de runtime *ter beschikking* heeft — niet de runtime zélf, en niet de wet.

Dit document neemt die frictie serieus en herformuleert het concept zodat:

- de **safety-separations** van Engine behouden blijven;
- **AI-first / brain-rich** productgedrag legitiem en expliciet wordt;
- “human first” niet verward wordt met “human in every loop step”.

---

## 1. De echte invariant (niet “geen AI”)

Lees de constitution opnieuw. Wat *niet* mag:

| Verboden | Waarom |
| --- | --- |
| LLM = operationele state | chat/transcript is niet reconstructeerbaar als world truth |
| LLM = authorization | model mag eigen bevoegdheid niet minten |
| LLM = success oracle | model mag eigen actie niet “gelukt” verklaren |
| LLM = hard-realtime actuator path | latency/nondeterminism ongeschikt voor stabilisatie |
| LLM = enige safety evaluator | policy ≠ safety hardware; fail-closed buiten model |
| Eén vendor/model verplicht voor correctness | replaceability |

Wat wél mag — en in `plan.md` al staat:

- LLM vertaalt intent → `GoalSpec` / `ProposedAction`
- skills, externe models, **mini-brains** als begrensde strategies
- Umwelt (optioneel) voor reconstructie, predicted effects, bounded planning
- samengestelde bounded workflows

**Conclusie:** Engine verbiedt geen AI-brein. Engine verbiedt een **onbegrensd, self-authorizing, self-certifying, state-owning super-agent**.

De slogan “geen AI brain” is dus **marketing- en framing-ruis** ten opzichte van de echte regel:

> **Geen brain is source of truth, authority, of realtime control.  
> Wel: brains als first-class, vervangbare tools achter contracts.**

Dat sluit beter aan bij de owner-intentie.

---

## 2. “Human first” ontwarren: drie verschillende claims

De documenten mengen soms drie claims die *niet* hetzelfde zijn:

### Claim A — Human as ultimate authority (normatief, blijft)

Bij high-risk, onduidelijke scope, of ontbrekende policy: een mens (of een expliciet geautoriseerd principal-proces) is de laatste approval-boundary.  
Dit is **juridisch en safety-nuttig**. Dit is *niet* “mens typt elke actie”.

### Claim B — Human as primary proposer (product-UX, optioneel)

Elke ronde begint met een mens die intentie geeft.  
Dat is **één UX-modus**, niet de enige.

### Claim C — Human as continuous operator (operationeel, vaak te zwaar)

Mens zit in de hot path van bijna elke mutatie.  
Dat is **tele-operatie**, geen runtime met intelligentie.

**Owner-weerstand raakt vooral B en C, niet A.**

Herschrijving die klopt met zowel safety als AI-product:

```text
Human sets charter (goals, budgets, risk class, stop conditions, approval policy)
  → Engine runs a cognition loop with brains-as-tools
  → every mutation still hits validate / policy / authorize / observe / receipt
  → human is interrupted only when policy says REQUIRE_APPROVAL / DEFER / UNKNOWN-safety
```

Dus: **human-chartered, brain-operated, policy-gated** — niet “human-step-first” op elke tick.

---

## 3. Engine als AI-brain: welke lezing is legitiem?

Drie productlezingen, oplopend in “AI-ness”:

### L1 — Runtime met optionele AI (huidige plan-default)

Mens of fixtures leveren voorstellen; LLM is plug-in.  
Sterk voor falsificatie en P1.  
Zwak als productdroom als de owner juist *wil* dat Engine “denkt”.

### L2 — Cognition fabric: brains are tools (owner-aligned, scheidingen intact)

Engine **is** de plek waar intelligentie georganiseerd wordt:

- meerdere proposers / planners / specialists
- tools en mini-brains als `Skill` / capability-backed cognition services
- één shared world snapshot, policy, auth, executor
- cognition mag lussen *binnen* deliberative time, met budget en stop conditions

Dit is nog steeds geen “model is God”. Het is **orchestrated intelligence under law**.

### L3 — Autonomous agent OS (conflict met Engine tenzij zwaar begrensd)

Open-ended recursive agent, self-expanding tools, long unattended plans, self-granted scope.  
Dit botst hard met `RULES.md` MUST NOT 2, 6, 19, 24 en de stop conditions.

**Aanbeveling:** positioneer Engine expliciet als **L2**, met L1 als 0.1-bewijspad en L3 als out-of-scope anti-pattern.

---

## 4. Breinen-als-tools: het ontwerpmodel

### 4.1 Kernidee

Behandel “denken” symmetrisch aan “handelen op een target”:

```text
Physical/software target  → Adapter + Capability + safety envelope
Cognition service         → BrainAdapter + CognitiveCapability + budget envelope
```

Een brain is **geen** meta-laag boven de wet. Een brain is een **tool** die:

- input consumeert (bounded context projection, niet “heel de chat als state”);
- output produceert als **untrusted artifacts** (`GoalSpec`, `ProposedAction[]`, uitleg, plan-sketch, ranking);
- resources verbruikt (tokens, latency, cost, privacy budget);
- vervangbaar is (offline fixture, other vendor, classical planner);
- nooit zelf `Authorization` of `ExecutionReceipt.success` schrijft.

### 4.2 Typologie van breinen (tools, niet hiërarchie van macht)

| Brain-tool | Typische output | Evidence grade van output | Mag dispatchen? |
| --- | --- | --- | --- |
| Intent parser (LLM) | `GoalSpec` draft | INFERRED | nee |
| Action proposer (LLM/rules) | `ProposedAction[]` | INFERRED | nee |
| Classical planner | ordered candidates | DERIVED (als deterministic) | nee |
| Umwelt dynamics (optioneel) | predicted `EffectDelta` + uncertainty | INFERRED / DERIVED | nee |
| Mini-brain perception | typed observation candidate | INFERRED tot sensor-oracle bevestigt | nee |
| Mini-brain control skill | bounded setpoint / skill params | proposal tot controller accepteert | alleen via authorized skill path |
| Critic / red-team model | risks, deny-hints | INFERRED advisory | nee |
| Deterministic policy explainer | reasons | DERIVED | n.v.t. |

**Belangrijk:** “brain as tool” betekent niet dat een mini-brain stiekem PWM mag sturen. Het betekent dat **cognition en specialisten** in dezelfde *tool economy* zitten als filesystem-write of arm-move: contracts, limits, audit — en voor muterende effecten: authorization.

### 4.3 Twee tool-klassen (voorkom categorie-fout)

Engine heeft baat bij een expliciete splitsing:

**A. World-acting capabilities**  
Muteren targets of claimen observaties over de wereld.  
Pad: proposal → validate → policy → authorize → execute → observe → receipt.

**B. Cognition capabilities**  
Muteren *alleen* deliberative artifacts (voorstellen, scores, uitleg, bounded plans).  
Pad: invoke brain-tool → validate schema → record cognition receipt → optionally feed into proposer pipeline.  
**Geen** world mutation, dus lichtere auth mogelijk — maar wél budget, privacy, en “geen self-auth expansion”.

Zonder deze split wordt alles óf te zwaar (elke thought = full auth) óf te los (brain smokkelt world actions).

### 4.4 Cognition loop (toegestaan) vs. agent chaos (niet)

**Toegestaan — bounded deliberation:**

```text
while budget remaining and not stop_condition:
  snapshot = observe()
  candidates = brain_tools.propose(snapshot, goal, skills)
  ranked = brain_tools.or_rules.rank(candidates)   # untrusted
  for action in ranked:
    decision = policy(action, snapshot)
    if decision == ALLOW and pre-authorized or auto-auth class:
      receipt = execute(action)
      reconcile(expected, observed)
    elif decision == REQUIRE_APPROVAL:
      park for human / principal
    elif DENY / stale / malformed:
      record and continue or abort per goal policy
```

Kenmerken: eindige budgetten, expliciete stop, elke world mutation door dezelfde gates, brains produce only candidates.

**Niet toegestaan — unbounded agent:**

- tool die runtime mag herconfigureren om eigen limits te verhogen
- “remember user said yes” als eeuwig auth token
- success = “model says looks good”
- verborgen recursive subagents buiten audit
- plan dat dagen doorloopt zonder re-observe / re-auth boundaries

### 4.5 “Engine is the brain” — precieze formulering

Gebruik deze zin:

> **Engine is the body of law and the hands.  
> Brains are organs you can swap.  
> The nervous system (runtime) decides what reaches the hands.**

Of productiever:

> Engine is an **AI-operable control runtime**: it can host and orchestrate many brains as tools, while remaining correct if every brain is replaced by fixtures.

Dat laatste is goud: **AI-rich in capability, AI-optional in correctness.**  
Dat verzoent owner-droom met 0.1-falsificatieclaim #2 (LLM replaceable).

---

## 5. Spanning met de huidige docs — eerlijke gap-analyse

| Huidige doc-toon | Owner-trek | Resolutie |
| --- | --- | --- |
| LLM optional proposal provider | Engine *is* (ook) intelligent | “optional for correctness” ≠ “optional for product value” |
| Human intent at front of chain | wil autonome ronden onder charter | human charters GoalSpec + policy; brains run until gate |
| Mini-brains late (P4) | brains/tools centraal in verhaal | narrative: brains-as-tools from day 1 *as interfaces*; learned mini-brains still earn complexity later |
| Anti “recursive agent loop as core” | wil wel cognition loops | allow **bounded** deliberation loops; ban **unbounded self-modifying** agents |
| “Not a robot brain” | wil brain-language | zeg “not an unconstrained brain”; wél “brain host / cognition fabric” |

Niets hiervan vereist de safety checksum te breken:

```text
LLM proposal != authority
prediction != observation
policy != physical safety
deliberation != realtime control
simulation != certification
state != weights
imagine != execute
```

Het vereist wél **product- en vocabulaire-ADR’s** als je L2 officieel maakt.

---

## 6. Herziene producthypothese (L2)

### 6.1 Eén zin

> Engine is a local-first runtime that turns chartered goals into safe, typed, auditable world actions by orchestrating replaceable brains-as-tools under an independent policy/authorization/execution boundary.

### 6.2 Waardepropositie (niet anti-AI)

Mensen kopen dit niet omdat AI *ontbreekt*, maar omdat AI **eindelijk ergens mag rennen zonder de waarheid te stelen**:

- meerdere specialisten (code, planning, vision, device skill) in één audit trail;
- swap model vendor without rewriting authority;
- dry-run / sim the same path the brain would take;
- automatic work under budgets; humans only for residual risk;
- edge/offline: local brains + local law when cloud dies.

### 6.3 Falsificatie blijft hard

L2 is weerlegd of moet versmallen wanneer:

1. cognition tools structureel de gates moeten bypassen om bruikbaar te zijn;
2. alleen één proprietary brain de loop stabiel maakt (correctness gekoppeld aan vendor);
3. domain adapters + ad-hoc scripts goedkoper en veiliger blijven;
4. “bounded loop” in de praktijk altijd unbounded wordt (product pressure).

---

## 7. Concrete architectuurimplicaties van brains-as-tools

### 7.1 Nieuwe / aangescherpte contracten (conceptueel)

Naast bestaande world types:

- `BrainManifest` — model/tool id, version, IO schema, cost/latency envelope, privacy class, supported tasks, eval evidence
- `ContextProjection` — bounded, hashed projection from `WorldSnapshot` (no “full chat is state”)
- `CognitionRequest` / `CognitionReceipt` — what was asked, which brain, latency/cost, output artifact hash
- `ProposalBundle` — ranked `ProposedAction[]` + provenance (which brain, which projection)
- `DeliberationBudget` — max steps, tokens, wall time, auto-auth risk ceiling, stop conditions
- `Charter` / extended `GoalSpec` — human (or org) standing orders: allowed brain set, auto-allow classes, approval principals

World-acting path blijft strikt. Cognition path is first-class en **auditable**, niet “invisible prompt magic”.

### 7.2 Authority model onder AI-operatie

Drie lagen van “mag dit?”:

1. **Charter** — standing permission shape (risk classes, targets, budgets, which brains)
2. **PolicyDecision** — per action against current snapshot
3. **Authorization** — scoped, expiring, exact

Auto-execution is dan geen “AI mag alles”, maar:

> actions within charter ∩ policy ALLOW ∩ valid auth template  
> may proceed without a fresh human click

Dat is hoe je **AI-first UX** krijgt zonder Claim A te laten vallen.

### 7.3 Human interrupt als exception path

Mens verschijnt bij:

- `REQUIRE_APPROVAL` risk class
- safety-relevant `UNKNOWN` / `CONFLICTING` / `STALE`
- budget exhaustion with goal incomplete
- brain disagreement above threshold (optional)
- first use of a new capability class (trust onboarding)

Niet bij: elke low-risk filesystem read in een sandbox met pre-approved charter.

### 7.4 Mini-brains vs. LLM tools — zelfde economy, andere bar

| | LLM brain-tool | Mini-brain skill |
| --- | --- | --- |
| Rol | brede deliberatie, taal, voorstellen | smalle perception/control specialty |
| Wanneer in pad | product value early (P2) | na baseline proof (P4) |
| Authority | never | never (only via skill+auth) |
| Replaceability | fixtures mandatory | baseline controller mandatory |
| Realtime | no | only inside validated controller envelope |

**Owner-wens “breinen als tools” kan vanaf dag 1 in de interfaces.**  
Learned on-device mini-brains blijven wetenschappelijk lui tot ze verdiend zijn. Dat is geen tegenstelling.

### 7.5 Umwelt in dit plaatje

Umwelt is dan zelf een **brain/world-model tool**:

- rijkere state queries
- predicted effects
- short planning candidates

Nog steeds: Engine authorizes and executes. Umwelt advises.  
Brains-as-tools maakt die relatie *natuurlijker* dan “Engine is dumb without Umwelt” of “Umwelt takes the loop”.

---

## 8. Wat dit doet met de 0.1-slice

**Niet veranderen (release-blocking):**

- two adapters, same lifecycle
- LLM replaceable by fixtures for identical policy/execution outcome
- replay reconstruction
- deny unauth/stale/malformed
- independent observation of effects

**Wél aanscherpen in narrative en tickets:**

- introduce `CognitionRequest`/`Receipt` even if the “brain” is a pure function fixture
- one bounded deliberation loop with budget (can be deterministic: rank static proposals)
- charter/auto-auth classes for sandbox low-risk actions (so “AI-operated” is real even offline)
- explicit BrainManifest for the fixture proposer and later one LLM provider

P1 kan nog steeds **zonder netwerk-LLM**.  
Maar P1 bewijst dan niet “Engine zonder intelligentie”, maar **“Engine met pluggable cognition tools, waarvan de eerste een deterministic fixture is.”**

Dat is psychologisch en productmatig een groot verschil, en technisch bijna dezelfde code.

---

## 9. Risico’s van de brains-as-tools lezing

### 9.1 Tool-washing van authority

Risico: “het is maar een tool” terwijl de tool de enige bron van plannen is en policy rubber-stamped.  
Mitigatie: policy on **action effects and risk**, not on “which brain said so”; red-team/deny fixtures; never let brain id expand privileges.

### 9.2 Context projection creep

Risico: projecties groeien tot shadow state.  
Mitigatie: hashed projections, size limits, ban “full transcript is world”; reconstruction never depends on provider memory.

### 9.3 Budget theater

Risico: budgets in docs, infinite in product.  
Mitigatie: hard stop in executor of deliberation scheduler; receipts show budget consumption; tests inject budget=0/1.

### 9.4 Multi-brain chaos

Risico: committee of models, no owner of plan quality.  
Mitigatie: één deliberative scheduler; brains propose; **deterministic merge rules** or single active proposer role per step; all ranked proposals retained for audit.

### 9.5 Product overclaim

Risico: “Engine is an AI brain” in de markt → liability en verkeerde verwachtingen bij hardware.  
Mitigatie: publieke zin altijd met clause: *operates brains as tools under independent authorization and observation*.

---

## 10. Aanbevolen herformulering van de thesis

### Oud (doc-default, safety-first tone)

> Local-first runtime turns human intent into safe actions; LLMs remain optional proposal providers.

### Nieuw (owner-aligned, separations preserved)

> Local-first runtime turns **chartered goals** into safe, typed, auditable actions by **orchestrating replaceable brains and skills as tools**, while **law (policy/auth), hands (executor/adapters), and independent safety** remain outside any model’s control.  
> Correctness must survive replacing every brain with fixtures; product value may still be brain-rich.

### Checksum-uitbreiding (conceptueel)

```text
brain != authority
brain != state
brain != observation
brain != realtime controller
brain == tool (schema, budget, receipt, replaceable)
charter != per-action approval (but enables auto-allow classes)
deliberation loop != unbounded agent
AI-rich product != AI-dependent correctness
```

---

## 11. Open beslissingen specifiek voor deze lezing

Voordat L2 “officieel” wordt, moet een mens (owner) kiezen:

1. **Default mode:** human-step-each-goal vs. charter-and-run vs. hybrid profiles per risk class  
2. **Auto-allow taxonomy:** welke actieklassen mogen zonder click onder een charter?  
3. **Cognition vs world tool split:** first-class in 0.1 types of later?  
4. **Multi-brain policy:** single proposer vs. parallel propose + merge  
5. **Privacy:** welke projections mogen welk external brain raken (opt-in matrix)  
6. **Story surface:** externe language “AI control runtime” vs. “execution fabric” vs. beide per audience  
7. **Relatie tot Umwelt:** brain-tool van dag 1 (port only) of pas na Umwelt gates  

Geen van deze keuzes mag de sealed safety gates van §9 in `plan.md` verzwakken.

---

## 12. Dieper oordeel

### 12.1 Over de owner-frictie

De frictie is **terecht**. De docs beschermen de juiste invariants, maar de *toon* kan lezen als:

- wantrouw AI tot het nutteloos is, en  
- zet de mens op elke trede.

Dat is een goede **builder-discipline** voor P0/P1, en een slechte **productidentiteit** als de droom AI-operable systems is.

### 12.2 Over “Engine mag een AI brain zijn”

**Ja — als “brain host / cognition fabric”.**  
**Nee — als “unconstrained autonomous mind that owns truth and actuators.”**

De productiefste synthese is:

> **Engine is the AI-ready body of law for action.  
> Intelligence is plentiful, swappable, and subordinate.  
> That subordination is what makes serious intelligence deployable.**

Zonder subordination krijg je demos.  
Met subordination krijg je iets dat naast PLC’s, policy en audit kan bestaan — en dát is schaarser dan nóg een agent loop.

### 12.3 Over “human first”

Vervang door:

> **Human sovereign, not human bottleneck.**  
> Humans write charters and handle residual risk.  
> Brains do volume cognition.  
> Runtime does truth, permission, and hands.

### 12.4 Prioriteit t.o.v. implementatie

Blijf P0/P1 technisch **brain-optional for correctness**.  
Maak P0/P1 conceptueel en contractueel **brain-ready**: manifests, cognition receipts, budgets, charter/auto-allow.  
Dan vecht de architectuur niet met de productdroom, en faalt 0.1 nog steeds eerlijk als de fabric niet werkt zonder modelmagie.

---

## 13. Mogelijke volgende documentstappen (niet uitgevoerd hier)

1. Korte ADR-draft: “Brains as tools / L2 cognition fabric” (accept/reject door owner)  
2. Herformulering van `plan.md` §1 en §3 (niet de safety bans, wél de productzin)  
3. Minimale type-lijst voor cognition path in 0.1  
4. Charter + auto-allow risk matrix voor sandbox-filesystem  
5. Expliciete anti-L3 appendix (wat nooit product wordt)

---

## 14. Slot

Engine hoeft geen keuze te maken tussen “veilig maar dom” en “slim maar roekeloos”.

De diepere lezing is:

- **slim via tools**  
- **veilig via wet en handen buiten de tools**  
- **menselijk via charter en residual approval**  
- **falsifieerbaar via brain-replaceability**

Dat is geen verzwakking van `AGENTS.md`.  
Het is de productlezing die de owner-intuïtie (“breinen ter beschikking”) en de builder-constitution (“proposal ≠ authority”) op één lijn zet.

Zie ook: `grok.md` (baseline-analyse), `plan.md` (hypothese), `AGENTS.md` (constitution).
