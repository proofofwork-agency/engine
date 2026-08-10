# Engine — conceptanalyse

> Bron: gelezen tegen `plan.md`, `AGENTS.md`, `RULES.md`, `ARCHITECTURE_GUARDRAILS.md`, `RESEARCH_PROTOCOL.md`, `BUILDER_CHECKLIST.md`, `GOVERNANCE.md`.
> Status van het concept: `SPECULATIVE` (geen code of metingen aanwezig in de repo).

## Wat het conceptueel is

Engine is een **local-first, capability-gebaseerde runtime** die menselijke intentie omzet in begrensde, getypeerde, auditeerbare acties op uiteenlopende software- en fysieke systemen. De centrale ontwerpkeuze is een *inversie* ten opzichte van gangbare AI-agentframeworks: niet de LLM is de control loop, maar een getypeerde pijplijn van capability → policy → autorisatie → uitvoering → observatie. De LLM is een **perifere, verwisselbare, onbetrouwbare voorstelgenerator** (`plan.md:26-28`, `RULES.md:89-91`).

De werkelijke intellectuele kern is geen feature-lijst, maar een stelsel van **categorische scheidingen** (`AGENTS.md` §2, `GOVERNANCE.md:35-44`): real state ≠ LLM-context, proposal ≠ autoriteit, deliberatie ≠ realtime-control, policy ≠ fysieke safety, predictie ≠ observatie, missing ≠ false, state ≠ weights, generieke lifecycle ≠ generieke device-semantiek.

## Sterktes

1. **Epistemologische discipline.** Bewijs wordt als first-class getypeerd (`OBSERVED/DERIVED/INFERRED/UNKNOWN/CONFLICTING/STALE`, `AGENTS.md` §9). De meeste agentsystemen verstoppen dit onderscheid; Engine maakt het operationeel. De regel "missing is not false" (`AGENTS.md:2.6`) en de weigering om een LLM-verklaring als observatie op te waarderen (`ARCHITECTURE_GUARDRAILS.md` §26, §9) zijn zeldzaam rigoreus.

2. **Falsificeerbaarheid als ontwerpprincipe.** `plan.md:43` stelt expliciet de weerleggingsvoorwaarde: de hypothese valt wanneer apparaatverschillen zoveel speciale logica vragen dat alleen een "dunne logginglaag" overblijft, of wanneer bestaande domeinruntimes + kleine integraties structureel eenvoudiger zijn. Weinig projecten formuleren dit.

3. **LLM-vervangbaarheid als correctheidseigenschap.** "Als de LLM wegvalt, verandert geen autorisatie- of waarheidssemantiek" (`ARCHITECTURE_GUARDRAILS.md` §18, `BUILDER_CHECKLIST.md:105-106`) is een sterke, testbare koppelingstest. Claim #2 van de eerste slice (`plan.md:187`) maakt dit direct toetsbaar.

4. **Schone Umwelt-grens.** Integratie via een versioned `WorldModelPort`, geen gedeelde mutable database (`plan.md:162-177`, `AGENTS.md` §12). Engine werkt zonder Umwelt. Dit voorkomt cirkelafhankelijkheid en koppelte risico's.

5. **Eerlijke statusdiscipline.** `SPECULATIVE/IMPLEMENTED/MEASURED/SUPPORTED/NOT-SUPPORTED/INCONCLUSIVE/CERTIFIED` (`GOVERNANCE.md:23-31`) en "negative result ≠ governance failure" (`GOVERNANCE.md:44`) maken dat het project kan falen zonder gezichtsverlies — een zeldzame, volwassen houding.

6. **Realistische fasering.** Software-filesystem → sim-arm → fysieke arm, met expliciete abandon-gates na elke fase (`plan.md:351-359`), geen automatische "doorgaan"-aanname.

## De werkelijke noveliteit

Engine leunt dichter aan tegen **aerospace/industriële safety-architectuur** (DO-178C-achtige traceerbaarheid, onafhankelijke safety-plane, bevroren oracles) dan tegen AI-agentframeworks. Het is in feite *capability-based security* (seL4/KeyKOS-traditie) toegepast op actuatie, met de LLM als onpriviligeerd proposal-proces. Dat is een oprecht ander ontwerppunt dan LangChain/AutoGen-achtige systemen waar het model de loop bezit.

## Spanningen en zwaktes

1. **De "dunne-laag"-ruk is het grootste productrisico** — en het plan weet dit zelf (`plan.md:43`). Twee adapters (filesystem + sim-arm, `plan.md:192-195`) is **mager bewijs** voor "één runtime voor veel werelden." Het toont slechts dat de lifecycle/contractlaag deling toelaat; of die deling productief is i.p.v. cosmetisch (gewoon logging + serialisatie) blijft de open vraag. De slice is correct gebouwd om juist dit te toetsen.

2. **Goedkeuringslast vs. nut — de onopgeloste productspanning.** Elke muterende actie vereist scoped, verlopende autorisatie (`RULES.md` MUST 8). Als de mens te vaak in de loop zit, is Engine een trage afstandsbediening. `RESEARCH_PROTOCOL.md:261` noemt dit als abandon-gate, maar `plan.md:333` laat de autorisatie-UX bewust open. Dit is product-kritiek en onbeslist.

3. **Grote contractsurface vóór implementatie.** 14 canonieke types in v0.1 bevriezen (`plan.md:107-119`) is zwaar voor één implementer. Risico op premature abstractie. Bij tegenwerking van types moet een ADR open — governance-overhead is hoog.

4. **Reconstructie-eis verdubbelt het werk.** Zowel event-replay als full-materialization met bewezen equivalentie (`RESEARCH_PROTOCOL.md:130-134`) is wetenschappelijk degelijk maar bouwt in feite het systeem twee keer. Goed voor correctheid, zwaar voor snelheid.

5. **De LLM-waardeprop-tension.** Als de LLM volledig vervangbaar is door vooraf vastgelegde voorstellen (claim #2), wat levert hij dan op? De slice test dit slim, maar het is een reële spanning in de waardepropositie: of de LLM mattert (dan is providerkoppeling een echt concern), of niet (dan is de "intentieparser" een dun laagje suiker).

6. **True safety-onafhankelijkheid op goedkope hardware.** Het principe (onafhankelijk van commando/netwerk/model) is juist. Op Pi-klasse hardware is een onafhankelijke hardware-noodstop haalbaar; een softwarematige onafhankelijke watchdog op hetzelfde bordje is moeilijker. Fysieke pilot is terecht pas P3 (`plan.md:288`).

7. **9–16 weken voor één implementer** door de volledige testlast (4 lagen, property-based stateful tests, crash-injectie, reconstructie-equivalentie) is **optimistisch**. Governance is zwaar; de feitelijke snelheid ligt lager.

## Onderspecificeerd

- **Concurrency/scheduling-model** voor meerdere doelen/targets/sessies (isolatie wordt genoemd, het lockmodel niet).
- **Klok- en tijdsynchronisatie** tussen edge en core (alleen vermeld als "excluded nondet. fields").
- **OTA/update-model** voor skills, adapters, policy-versies zelf — niet behandeld.
- **Faalt de runtime correct als de lokale policy-service down is?** `RESEARCH_PROTOCOL.md:153` noemt het als fault, maar fail-closed-gedrag van een local-first systeem bij eigen policy-uitval behoeft verheldering.
- **Economie/licentiemodel** voor skills — enkel als open beslissing (`plan.md:336`).

## Conclusie

Engine is **intellectueel volwassen en ongewoon gedisciplineerd** voor een AI/robotica-concept. De grootste kracht (governance en epistemische strengheid) is tegelijk het grootste commerciële risico (hoge overhead, lage snelheid, smalle initiële scope). Het project wordt eerlijk als een te falsifiëren hypothese gepresenteerd i.p.v. als een productbelofte — zeldzaam en lovenswaardig.

De beslissende vraag is exact de eigen falsificatievoorwaarde uit `plan.md:43`: *overleeft een betekenisvolle gedeelde runtime de apparaatheterogeniteit, of stort hij in tot gedeelde logging?* De 0.1-slice is correct gebouwd om precies dat te beantwoorden.
