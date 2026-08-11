# Engine — 30-dagen roadmap (0.1 dichttrekken)

> Status: execution plan. Geen herdefinitie van Engine.  
> Anker: `GOAL.md` (I1–I5, B1–B4, W1–W4, H1–H3, R1–R3).  
> Positionering: `docs/POSITIONING.md`. Concurrentie: `threath.md`.  
> Datum: 2026-08-10.

> Canonieke-padcorrectie: de v2-actielifecycle plus `engine.plugin/v3` is de productie-route. De generieke
> `engine-runtime` runner en de pluginneutrale learning-lifecycle vormen samen
> de afgeronde verticale softwaretranche; de resterende beslissende gate is de
> vooraf begrensde fysieke Homey-proef met onafhankelijke lux- en wattmeting.

---

## Doel van de 30 dagen

**Zeg hardop en demo-baar:**

> Engine 0.1 bestaat: het hart houdt doelen, state en ervaring vast; het algemene brein plant en kiest; minstens één specialist en gedeelde tools worden via het hart aangeroepen; twee verschillende werelden worden door **dezelfde** levende lus bestuurd; meerstapsdoelen slagen op oracles zonder mens per stap — inclusief maintain/monitor en herstart.

**Niet het doel:** OpenClaw-parity, skills hub, WhatsApp gateway, mini-brain training, full policy matrix, TASK/STREAM production, Umwelt, physical certification.

---

## Non-goals (expliciet verboden in dit venster)

| ID | Verboden werk | Waarom |
| --- | --- | --- |
| NG1 | Messaging gateway (Telegram/WhatsApp/…) | OpenClaw-speelveld; UX-creep |
| NG2 | Skills marketplace / hot-reload skill OS | Hermes/OpenClaw-speelveld |
| NG3 | Self-writing skills als productkern | Later groeipad; niet 0.1 identity |
| NG4 | Full auth/policy matrix als blocker | `GOAL.md` D1 |
| NG5 | Nieuwe wereldarchitectuur per target | `GOAL.md` D6 |
| NG6 | Concept rewrite / nieuwe one-liner | `GOAL.md` D8 |
| NG7 | Onbegrensde v1/v2 dual-kernel features | Eén canonical 0.1 path |
| NG8 | Hardware e-stop / certification theater | Parallel later; niet 0.1 done |

**Toegestaan als steiger (mag niet de demo definiëren):** deterministic brains, fixture specialists, sandbox isolation, Homey observe-only.

---

## Success gate (week 4 review)

| Gate | Pass-criterium | Evidence |
| --- | --- | --- |
| G-demo | Eén commando/suite: FS + grid, shared Heart | `R1` |
| G-identity | Restart + durable goals/state/experience | `I1–I3` |
| G-live | LiveEngine without human-per-step | `I4` |
| G-brain | General → specialist → tool → observe path | `B1–B4` |
| G-truth | Receipts + oracle completion; ≥1 partial path | `H1–H3` |
| G-worlds | Domain only in adapters/specialists | `W1–W4` |
| G-story | Written note: shared vs unique | `R2` |
| G-owner | Owner watches goal-in → autonomous → oracle-out | `R3` |
| G-position | POSITIONING one-pager unchanged by implementation drift | docs review |

**Resterende fysieke gate:** één begrensde Homey-zone, vijf gesloten lussen met
verse lux- en wattmetingen. Fake- en reference-world tests bewijzen contracten
en herstel, maar gelden niet als fysiek bewijs.

**Fail / cut:** if a criterion cannot pass, record explicit scope-cut with owner — do not silently shrink identity.

---

## Canonical path (freeze early)

| Decision | Choice for 0.1 |
| --- | --- |
| Primary Heart path | `src/engine/world_heart.py` + `world_store.py`, samengesteld door het installeerbare `engine-runtime` |
| Worlds for gate | geïnstalleerde `engine.plugins` entrypoints; Homey-fake en warehouse-reference delen exact dezelfde Heart-runner |
| Plugin SDK | `engine-sdk` is het enige publieke plugincontract; plugins hebben geen runtime-afhankelijkheid nodig |
| v1 modules (`heart.py`, `runtime.py`) | alleen compatibiliteit voor bestaande fixtures; geen nieuwe productfeatures |
| Learning | ADR-0004: optionele `ExperienceProvider` → durable evidence → candidate → shadow → nieuwe `GoalSpec`-versie |
| General brain | deterministic voor bekende stabiele situaties; ieder OpenAI-compatibel model alleen bij novelty, conflict of ambiguïteit |

Nieuwe action-lifecycle features gaan via de v2-contracten; pluginautonomie gaat
uitsluitend via `engine.plugin/v3`. Een derde wereld wordt
toegevoegd door installatie, manifest en protocollen, zonder wijziging aan
Heart of runtime.

---

## Week 1 — Freeze & close identity gaps (dagen 1–7)

**Theme:** anti-paper, anti-dual-kernel, checklist against `GOAL.md`.

| Day | Work | Done when |
| --- | --- | --- |
| 1 | Map every `GOAL.md` criterion → test or demo command; mark PASS/GAP/UNKNOWN | Matrix table in this file or `artifacts/evidence/goal-audit.md` |
| 2 | Canonical path freeze note; list files that must not diverge | Note merged; geen nieuwe v1-productfeatures |
| 3 | Close any GAP on I1–I3 (restart reconstruction of goal + snapshot + experience influence) | Automated test green |
| 4 | Close I4–I5 + H1–H2 (LiveEngine path, brain chooses, receipts, oracle not self-report) | Tests + short log artifact |
| 5 | H3 partial/failure path visible and recovered in at least one world | Test asserting state machine reaction |
| 6 | B1–B4 path: one scripted multi-step with specialist + tool + provenance IDs | Test or deterministic demo segment |
| 7 | Week-1 review: remaining gaps only on W/R polish or docs — no identity holes | Owner checkpoint |

**Exit:** identity (I/B/H) is test-backed, not narrative-backed.

### Week 1 anti-patterns

- Domeinsemantiek aan Heart of runtime toevoegen in plaats van aan een plugin.
- Een plugin, model of Cell een vrije agentloop, eigen permissions of direct
  executor-/toolgebruik geven.
- “Improving” policy/auth instead of oracle/restart tests.
- Rewriting `GOAL.md`.

---

## Week 2 — Two worlds, one demo (dagen 8–14)

**Theme:** `W*` + `R1` as product surface.

| Day | Work | Done when |
| --- | --- | --- |
| 8–9 | Single entrypoint (prefer extending `engine.demo` / `live_heart_demo`) runs **both** worlds on one process story | One command |
| 10 | Maintain story on at least one world: stable → monitor → inject drift → repair → monitor | `live_heart_demo` (or successor) reliable |
| 11 | Grid partial + restart segment still in the main demo path | Documented in demo output |
| 12 | Experience influences a later choice (already partially true) — assert in test, show in demo log | I3 evidence explicit |
| 13 | Optional LLM path remains **same interface** (G8); deterministic path is CI default | CI does not require GPU/LLM |
| 14 | Week-2 review: R1 green; list only polish for week 3 | Checkpoint |

**Exit:** “two worlds, one Engine” is a single runnable story.

---

## Week 3 — Evidence, Homey as body signal, stop creep (dagen 15–21)

**Theme:** make the *difference from OpenClaw/Hermes* felt without building their product.

| Day | Work | Done when |
| --- | --- | --- |
| 15–16 | `R2` write-up: shared core vs per-world unique (honest, short) | Update `PROTOTYPE.md` or `RESEARCH_FINDINGS` section |
| 17 | Goal-audit artifact consumed: PASS list + known limitations | `artifacts/evidence/goal-audit.md` final for 0.1 |
| 18–19 | Homey: dezelfde v2 runner als reference-world; mutations blijven fail-closed | generieke runner- en learningtests groen |
| 20 | Explicit non-claims list aligned with demo (no certification, no TASK/STREAM, no multi-brain superiority) | `PROTOTYPE.md` / POSITIONING sync |
| 21 | Kill list review: any PR open that smells like NG1–NG8 → close or park | Clean backlog |

**Exit:** positioning matches shipped reality; Homey is signal not blocker.

---

## Week 4 — Owner gate & 0.1 seal (dagen 22–30)

**Theme:** `R3` + ship/seal, not new architecture.

| Day | Work | Done when |
| --- | --- | --- |
| 22–24 | Polish demo UX for owner watch (clear phases printed: observe/think/act/oracle/status) | Owner can follow without reading source |
| 25 | Full deterministic suite green; record command lines in README top | Copy-paste works |
| 26 | Optionele live model-canary via de OpenAI-compatibele v2-adapter; nooit vereist voor core correctness | Evidence JSON als credentials beschikbaar zijn |
| 27 | Owner review against success gate table | Pass / explicit cuts signed |
| 28 | Tag or label **Engine 0.1** in docs (`PROTOTYPE.md` status line) | Status not “preflight-only” if criteria pass |
| 29 | Post-0.1 backlog: ActionRequest-hardening, TASK/STREAM waar nodig, en fysieke uitbreiding pas na de één-zone-proef | Backlog file or section — no scope drift |
| 30 | Retrospective: what was cut, what OpenClaw-creep was refused, next 30d hypothesis | Short note |

**Exit:** 0.1 sealed or honest fail with cuts.

## Autonomy v3 vervolgvolgorde

De owner-volgorde na deze generieke softwaretranche is:

1. runtime authority, lease-fencing, crash recovery en resource-reservering
   blijven hardenen;
2. `engine.plugin/v3` en de generieke autonomycontracten stabiel houden;
3. de reference-world closed loop als deterministische referentie onderhouden;
4. iedere ingebouwde plugin exact v3-conform houden, ook met lege autonomyrollen;
5. pas daarna live pluginrollouts en fysieke claims uitbreiden.

Provider-subscriptions, eventbronnen en executorworkers blijven toegestaan als
Heart hun lifecycle bezit en zij niet zelf doelen of acties kiezen. Hogere
risicoklassen, overlappende enrollment-arbitrage, Engine-owned cross-plugin
workflows, procesisolatie en meerdere cognition-hops vereisen nieuw ownerbesluit,
ADR en bewijs.

Engine Cell blijft post-autonomy: eerst een gemeten tekort van een
deterministische/klassieke baseline, daarna één lokale runner, held-out
evaluatie, resource envelope, specialistadapter en authorityloze shadow.

---

## Workstream ownership (suggested)

| Stream | Focus | Primary surfaces |
| --- | --- | --- |
| Kernel | Heart, store, runner | `src/engine/world_heart.py`, `world_store.py`, `packages/engine-runtime/` |
| Worlds | Installed plugins; fake + reference for deterministic gates | `plugins/` |
| Brains | General model adapter + plugin specialists | `brains_v2.py`, `packages/engine-runtime/src/engine_runtime/models.py` |
| Evidence | Tests, demos, artifacts | `tests/`, `artifacts/evidence/` |
| Body signal | Homey bounded closed-loop proof | `plugins/engine-homey/` |
| Position | Docs freeze | `docs/POSITIONING.md`, `GOAL.md` (read-only) |

Agents: implement on Kernel/Worlds/Brains/Evidence; **do not** open NG streams without owner.

---

## Daily definition of progress

A day counts as progress only if at least one of:

1. a `GOAL.md` criterion moves GAP → PASS with test/demo evidence; or  
2. a dual-path ambiguity is removed (canonical freeze); or  
3. a non-goal PR is rejected with reason; or  
4. owner-visible demo clarity improves.

Docs-only days without R2/R3 value do **not** count (`GOAL.md` D7).

---

## Mid-point kill criteria (dag 14)

Stop or escalate to owner if:

- restart does not reconstruct goals/state (I1/I2 still red); or  
- second world still requires a second cognitive architecture (W3/W4 red); or  
- demo still requires human-per-step (I4 red); or  
- team is shipping messaging/skills instead of Heart fixes.

Do not “rescue” by rewriting the goal.

---

## Post-0.1 (explicitly after seal)

Ordered backlog — **not** this 30-day plan:

1. Durable `ActionRequest` hardening (snapshot precondition, deadline, idempotency).  
2. Homey act-mode bounded pilot with preregistered protocol (low-risk lights only).  
3. Multi-zone Homey enrollment uitsluitend als configuratie, na de één-zone-gate.  
4. Optional intent surface (could integrate *with* OpenClaw/Hermes later as clients — Engine remains authority on goals/state/act).  
5. TASK/STREAM lifecycle only when a target requires it.

---

## One-week “if we only had 7 days”

Collapse to:

1. Goal-audit PASS matrix.  
2. Canonical Heart path freeze.  
3. One command: FS+grid ACHIEVE + one MAINTAIN demo.  
4. Restart test green.  
5. Owner watch (R3).  
6. POSITIONING unchanged.

Everything else is noise.

---

## Checklist (print)

```text
[ ] I1 restart goals
[ ] I2 durable world state
[ ] I3 experience influences later choice
[ ] I4 LiveEngine no human-per-step
[ ] I5 brain chooses; heart executes
[ ] B1 general brain slot
[ ] B2 ≥1 specialist
[ ] B3 full cognitive cycle in one goal
[ ] B4 provenance of specialist + tool outputs
[ ] W1 filesystem multi-step + oracle
[ ] W2 grid multi-step + oracle
[ ] W3 same heart/brain/catalog/store
[ ] W4 domain only in adapters/specialists
[ ] H1 receipt + post-state / UNKNOWN
[ ] H2 oracle completion not self-report
[ ] H3 partial/failure path handled
[ ] R1 one shared-core demo command
[ ] R2 shared vs unique write-up
[ ] R3 owner-visible run
[ ] No NG1–NG8 merged
[ ] 0.1 status line updated
```
