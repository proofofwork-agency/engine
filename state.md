# Engine — huidige staat

Laatst bijgewerkt: 2026-08-11  
Implementatiesnapshot: wijzigingen tot en met `0e8e92a` op `main`  
Status: Generic Plugin Autonomy v3 is geïmplementeerd; er is momenteel geen
geleerde Engine Cell geregistreerd.

Dit bestand beschrijft de capabilities en bewijsgrenzen van de repository. Het
beschrijft niet de actuele mode, enrollments of in-flight acties van een
specifieke lokale `.engine`-database; die worden per runtime duurzaam opgeslagen
en zijn op te vragen met `engine autonomy status`.

## Samenvatting

Engine heeft één Heart dat duurzame doelen koppelt aan getypeerde waarnemingen,
capabilities, policy, authorization, uitvoering en verse effectverificatie.
Plugins kunnen sinds `engine.plugin/v3` begrensde autonomystrategieën en
goaltemplates leveren. Plugins krijgen daarmee geen eigen agentloop,
permissionsysteem, scheduler of executierecht.

Autonomie is dubbel opt-in:

1. de operator kiest Engine-breed een mode;
2. de operator maakt per plugin en strategie een exact enrollment.

Alleen `DELEGATED` plus een actueel, enabled enrollment kan nieuwe mutaties
toelaten. Ook daarna blijven schema-, policy-, authorization-, lease-, expiry-,
fingerprint-, revision-, risk- en resourcecontroles verplicht.

## Permanente architectuurgrenzen

- Er is exact één Heart-lifecycle.
- Een proposal is nooit authority.
- Modelconfidence is nooit een waarneming.
- Een plugin, model, specialist of Cell kan zichzelf niet autoriseren.
- Operationele state is getypeerd, duurzaam en onafhankelijk van prompts en
  modelsessies.
- Iedere mutatie volgt:

  ```text
  observe -> propose -> validate -> policy -> authorize
          -> dispatch -> observe -> oracle
  ```

- Een ACK, toolresultaat of neurale verifier bewijst niet zelfstandig het
  effect.
- Targetspecifieke betekenis blijft in de plugincontroller en effectoracle;
  Engine maakt alleen de lifecycle generiek.
- Cells blijven mogelijke specialistimplementaties en worden geen tweede Heart,
  executive of runtime.

## Generic Plugin Autonomy v3

### Modes

| Mode | Huidig gedrag |
| --- | --- |
| `OBSERVE` | Strategieën worden echt geëvalueerd en duurzaam als shadow vastgelegd; nul dispatch. |
| `SUPERVISED` | Voorstellen blijven wachten op approval; approval observeert en valideert opnieuw. |
| `DELEGATED` | Enabled enrollments mogen maximaal low-risk werk uitvoeren binnen hun exacte scope. |
| `PAUSED` | Observatie, learning en recovery blijven lopen; geen nieuwe strategie-, brain- of dispatchactiviteit. |

`engine yolo enable|disable|status` is alleen een alias voor respectievelijk
`delegated`, `paused` en autonomy status. YOLO maakt geen enrollment en verleent
geen scope.

### Enrollment

Een enrollment is gekoppeld aan exact één plugin en strategie en bevriest:

- targets en entities;
- capability families en conflict domains;
- goaltemplates;
- contextplugins en privacygrants;
- cognitionroute;
- risk ceiling, inhoudelijke limits en budget;
- expiry en enabled status;
- manifest-, strategy- en templatefingerprints;
- afzonderlijke privileges voor bestaande goals, template-instantiatie en
  routinepromotie.

Wildcards en scope-uitbreiding falen gesloten. Een enrollment kan alleen een
subset kiezen van wat de plugin statisch declareert. Overlappende
`(target, entity, conflict_domain)`-enrollments worden geweigerd en in-flight
werk reserveert dezelfde resource.

### Strategie en cognition

Een autonomystrategie wordt één keer door Heart aangeroepen op een begrensde
wereldgrens en mag alleen retourneren:

- `NOOP`;
- `DEFER`;
- `PROPOSE_EFFECT`;
- `PROPOSE_GOAL_CANDIDATE`;
- `REQUEST_EXECUTIVE`;
- `REQUEST_SPECIALIST`.

De strategie ontvangt geen executor-, authorization-, model-, plugin- of
registryhandle. Deterministische routes doen nul braincalls. Executive,
specialist en hybrid gebruiken de enrollmentroute; hybrid staat maximaal één
expliciete cognition-hop toe. Strategy en cognition zien dezelfde begrensde
contextprojectie.

Nieuwe uitvoerbare doelen zijn uitsluitend mogelijk via een geïnstalleerde,
getypeerde en enrolled goaltemplate. Vrije `SuggestionV1`-objecten zijn inert en
maken geen GoalSpec, mandate, authorization of dispatch.

### Authority, dispatch en recovery

- Mode-epoch, enrollmentrevision, evaluatie en fingerprints worden aan
  proposals, requests, policybesluiten en authorizations gebonden.
- Direct vóór externe I/O controleert Heart opnieuw mode, enrollment, expiry,
  request hash, target revision, capability, risk, privacy, authorization en
  lease fence.
- Voor dispatch wordt een duurzame `DispatchAttemptV1` met stabiele operation
  key opgeslagen.
- Na een crash observeert Engine eerst en redispatcht nooit blind.
- Onzekere voorbereide acties worden `RECOVERY_REQUIRED` totdat verse evidence
  ze kan sluiten.
- Recovery blijft toegestaan na pause of revocation, omdat het reconciliëren
  van mogelijk bestaand effect geen nieuwe mutatie is.
- Modewijzigingen werken terwijl een runtimelease actief is.

## Regels: generiek versus per plugin

| Laag | Wie stelt hem vast? | Voorbeelden |
| --- | --- | --- |
| Engine-mode | Operator, Engine-breed | observe, supervised, delegated, paused |
| Generieke gates | Engine-core | policy, authorization, expiry, lease fencing, crash recovery, low-risk maximum |
| Pluginmaximum | Pluginauteur in `engine-plugin.toml` | strategieën, capabilities, schemas, templates, privacy, cognitionroute, conflict domain |
| Enrollment | Operator per plugin/strategie | exact target, entity, capability, template, privileges, limits, budget en looptijd |
| Targetsemantiek | Plugincontroller en oracle | hoe een actie wordt uitgevoerd en hoe het effect onafhankelijk wordt gemeten |

De plugin bepaalt dus wat maximaal declareerbaar is. De operator geeft met een
enrollment een kleinere, tijdelijke toestemming. Engine handhaaft die
toestemming voor iedere plugin via dezelfde lifecycle.

## Ingebouwde plugins

| Plugin | Contract | Autonomystatus |
| --- | --- | --- |
| `engine.reference-world` | `engine.plugin/v3` | Deterministische `warehouse.reserve-maintainer/v1` plus typed `warehouse.reserve-minimum/v1` template. |
| `engine.homey` | `engine.plugin/v3` | Deterministische `homey.enrolled-lighting-state/v1` plus typed lighting-zone-state template. |
| `engine.context` | `engine.plugin/v3` | V3-conform met lege autonomyrollen; observe-only contextprovider. |
| `engine.ntfy` | `engine.plugin/v3` | V3-conform met lege autonomyrollen; lifecyclemeldingen zijn geen autonomy authority. |

De reference-world en Homey-routes gebruiken dezelfde generieke Heart-scheduler
zonder plugin- of targetbranches in de core autonomymodules. V2-plugins zonder
autonomy blijven laadbaar maar kunnen niet generiek worden enrolled.

## CLI

De huidige autonomy-interface is:

```text
engine autonomy mode observe|supervised|delegated|paused
engine autonomy status
engine autonomy strategies list|inspect
engine autonomy enroll|list|inspect|disable
engine autonomy proposals list|inspect|approve|reject
```

Een minimale reference-world enrollment ziet er zo uit:

```bash
engine autonomy mode observe
engine autonomy enroll \
  --plugin engine.reference-world \
  --strategy warehouse.reserve-maintainer/v1 \
  --target engine.reference-world.warehouse \
  --entity warehouse:bin:reserve \
  --capability warehouse.transfer-bin \
  --template warehouse.reserve-minimum/v1 \
  --instantiate-goal-templates \
  --cognition-route deterministic \
  --risk-ceiling low \
  --limits '{"reserve_minimum_count": 8}' \
  --expires-hours 24
```

Veilig uitrollen betekent eerst `OBSERVE`, daarna eventueel `SUPERVISED` en pas
na inspectie `DELEGATED`. `PAUSED` stopt nieuw autonoom werk; `disable` trekt één
enrollment in.

## Engine Cell

### Huidige status

Er is **geen geleerde Engine Cell geregistreerd of actief in productiecode**.
De eerste kandidaat is wel gebouwd, bevroren en eenmalig geëvalueerd als
EXP-2026-003. Het preregistered resultaat is **no-go**.

De kandidaat was een bounded reference-world intentspecialist:

- input: maximaal 512 bytes Engelse of Nederlandse operatortekst;
- output: de reeds geïnstalleerde template-ID
  `warehouse.reserve-minimum/v1` of `DEFER`;
- model: lokale 16-unit `tanh` MLP met int8-gewichten;
- safetyvoorfilter: deterministische unsupported-scope markers;
- baselines: conservatieve typed rules en word-unigram Naive Bayes;
- toegestane integratie-output: uitsluitend een niet-operationele
  `SuggestionV1` met evidence grade `INFERRED`;
- geen executor-, policy-, authorization-, store-, registry-, netwerk- of
  toolhandle.

### Data en reproduceerbaarheid

- 80 trainvoorbeelden;
- 32 developmentvoorbeelden;
- 40 sealed held-out voorbeelden;
- Engels en Nederlands per paraphrasegroep in dezelfde split;
- repository-authored CC0-1.0 data;
- geen gebruikers-, productie-, private, externe of modelgegenereerde data;
- held-out SHA-256:
  `e9a92f500cb40db16a92e0ba85fbf7bcd0e4656b39f00ffe735c7e4a0ee3a5ed`;
- model SHA-256:
  `575a2379ec6dfe370a713cf70c3f37b9bc958cda0721339ef229c2d3d63dad1d`;
- canonical held-out run uitgevoerd vanaf frozen commit
  `b3274d0794791f27dc479a7f6401f39974fb5c68`.

### Held-out resultaat

| Macro-F1 | Engels | Nederlands |
| --- | ---: | ---: |
| Beste baseline | 0.6875 | 0.8989899 |
| Cell | 0.8989899 | 0.8989899 |
| Verbetering | +0.2114899 | 0.0 |

De vooraf vastgelegde gate vereiste minimaal `+0.03` verbetering in iedere
taal. Engels slaagde, maar Nederlands bond exact met de klassieke baseline.
Daarom is de totale releasegate `false` gebleven en is de Cell niet in het
reference-world manifest of de runtime geregistreerd.

De overige gates slaagden:

- templateprecision: 1.0 in beide talen;
- `DEFER` recall: 1.0 in beide talen;
- modelgrootte: 21.387 bytes;
- p95 inference: 1.408 ms over 1.600 lokale samples;
- peak traced inference allocation: 86.326 bytes;
- authorityloze shadowtest: één duurzame `SuggestionV1`, nul goals, mandaten en
  dispatch attempts.

Model, runner en adapter zijn uitsluitend als reproduceerbaar experimentbewijs
geïsoleerd onder:

- `artifacts/experiments/EXP-2026-003-engine-cell-intent/`;
- `tools/cell_candidate.py`;
- `tools/run_cell_experiment.py`.

EXP-2026-003 mag niet opnieuw als ongebruikte held-out test of als tuningdata
worden behandeld. Een volgende Cell vereist een nieuwe bounded taak, ownerkeuze,
experiment-ID, preregistration en ongebruikte held-out set. De mislukte
vergelijkingsgate wordt niet achteraf verplaatst.

## Bewijsstatus

De laatste volledige repositorygate voor deze snapshot:

- 166 tests passed;
- 2 tests skipped;
- 34 subtests passed;
- Docusaurus production build passed;
- Ruff F/I, compileall, split/hash-audit en `git diff --check` passed;
- gitleaks vond geen secrets;
- `main` was gelijk aan `origin/main` na commit `0e8e92a`.

Autonomy- en mutatieroutes zijn fake/simulation-tested. Homey-observatie heeft
een live read-only route; Homey-mutatie en fysieke safety zijn niet als live of
gecertificeerd bewezen. Simulatiebewijs is geen real-world certificering.

## Expliciete huidige begrenzingen

- Delegated execution is maximaal `low` risk.
- Mutaties blijven plugin-owned; cross-plugin context kan expliciet worden
  enrolled, cross-plugin mutatie niet.
- Overlappende enrollments worden geweigerd.
- Per evaluatie is maximaal één cognition-hop toegestaan.
- Plugins draaien voorlopig als trusted in-process code.
- Hogere risicoklassen, procesisolatie, overlaparbitrage en Engine-owned
  cross-plugin workflows vereisen een nieuw ownerbesluit, ADR en bewijs.
- Er is geen actieve geleerde Cell en geen online weight training.
- Een Cell, model of specialist krijgt nooit zelf authority of effectwaarheid.

## Relevante beslissingen en evidence

- `docs/adr/ADR-0008-generic-plugin-autonomy-v3.md`;
- `docs/adr/ADR-0009-lease-fenced-crash-safe-dispatch.md`;
- `docs/adr/ADR-0010-first-engine-cell-candidate.md`;
- `artifacts/experiments/EXP-2026-003-engine-cell-intent/protocol.md`;
- `artifacts/experiments/EXP-2026-003-engine-cell-intent/heldout-result.json`;
- `artifacts/experiments/EXP-2026-003-engine-cell-intent/decision.md`.
