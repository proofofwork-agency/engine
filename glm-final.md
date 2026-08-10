# Engine — laatste review

> Sluitstuk na `glm.md` en `glmdeep.md`. Deze notitie neemt de Engine-identiteit zoals door de eigenaar vastgesteld als *gegeven* en beoordeelt alleen het pad naar realisatie. Geen herdefinitie, geen herschrijven van het concept, geen één kant indrukken. Eerdere notities leunden te zwaar op de "stort de abstractie in tot logging / is-het-een-ding"-lees; die lees verandert hier van hoofdkader naar één risico onder meerdere.

## 0. Disclaimer van positie

Ik behandel Engine niet als een te rechtvaardigen hypothese maar als een te realiseren systeem. Risico's blijven risico's. De vraag is niet "verdient Engine te bestaan?" maar "wat moet er echt gebouwd worden, waar zit de technische zwaarte, en wat mag de eerste realisatie niet verdringen?"

## 1. Engine zoals vastgesteld

Vastgelegd, niet ter discussie:

- Engine is het **volledige levende systeem** — hart én brein, niet een harness, workflow-engine of safetylaag.
- **Intelligentie is kern**, niet optionele versiering.
- Eén **algemeen brein** kiest (begrijpt situatie, vormt plan, kiest tools, roept specialistische breinen aan). Het **hart** voert de aanroep uit, bouwt context, bewaart resultaat en houdt continuïteit.
- **Specialistische breinen** (vision, code, planning, beweging, voorspelling, critic) zijn cognitieve capabilities.
- Engine **bezit de gedeelde wereldtools** (filesystem, browser/API, simulator, sensoren, apparaten). Specialistische breinen mogen eigen interne cognitieve tools hebben zolang in/uit duidelijk is.
- **State, ervaring, doelen en wereldtoestand** horen bij Engine en overleven modelaanroepen en procesherstarts.
- Een **mens hoeft niet iedere cyclus** te initiëren of goed te keuren.
- **Safety en autorisatie** kunnen nodig zijn, maar definiëren niet wat Engine fundamenteel is. Ze zijn een schil die groeit naarmate het systeem het lab verlaat — en ze mogen de eerste realisatie van de cognitieve kern niet verdringen.
- Mini-breinen zijn mogelijk en interessant, geen voorwaarde voor de eerste kern.

## 2. Realisatie-goal (anker)

> Realiseer en valideer Engine 0.1 als een duurzaam hart én brein dat met één stateful cognitieve lus, gedeelde tools en specialistische breinen zelfstandig meerstapsdoelen voltooit in minstens twee heterogene sandbox-/simulatiewerelden.

Anti-driftregels die deze review binden:

- zelfde cognitieve kern bedient beide werelden;
- alleen adapters, tools en specialistische breinen zijn domeinspecifiek;
- state en ervaring overleven modelcalls en procesherstarts;
- werkelijke resultaten beïnvloeden volgende beslissingen;
- de mens initieert niet elke stap;
- safety verdringt de eerste realisatie van de cognitieve kern niet;
- afwijkingen zijn expliciet als hypothese of trade-off, nooit stille herdefinitie.

## 3. Wat echt gebouwd moet worden (de technische zwaarte)

De identity-woorden moeten naar architectuur worden vertaald zonder het concept te verschuiven. Concreet betekent "levend systeem" vier dingen die niet triviaal zijn en die het werk vormen:

### 3.1 Het hart als duurzame drager
Het hart is geen message-bus. Het is de drager die levend blijft tussen modelaanroepen door:
- **doelen die blijven bestaan** buiten een modelsessie;
- **wereldgebeurtenissen die Engine kunnen wekken** (niet alleen het model trekt);
- **aandacht/prioriteit** als eigen toestand, niet afgeleid uit de prompt;
- **duurzame wereldtoestand** die reconstructeerbaar is;
- **ervaring/geheugen** dat groeit met iedere cyclus;
- **continuïteit van onafgemaakte processen** over herstarts heen.

Dit is het echte verschil met een harness (die alleen een modelsessie en tools organiseert). Een harness wordt wakker als er een beurt is; een hart houdt de lus levend.

### 3.2 Eén cognitieve kern, identiek over werelden
Dezelfde lus — `snapshot → algemeen brein.propose → (specialist of tool) → uitvoeren → observation/receipt → reduce → nieuwe snapshot` — draait ongewijzigd op beide werelden. Domeinspecifiek zijn uitsluitend: adapters, wereldtools, specialistische breinen. Dit is de harde eis die "twee werelden, één hart" tot een echte claim maakt in plaats van twee afzonderlijke integraties.

### 3.3 Brein-orchestratie
Het algemene brein redeneert ("ik heb visuele interpretatie nodig"), produceert een gericht verzoek; Engine bouwt de context, roept het specialistische brein aan, bewaart het resultaat; het algemene brein verwerkt en kiest een wereldtool; Engine voert uit en verwerkt het gevolg. De orchestration-lus, contextbouw en resultaatpersistentie zijn Engine-verantwoordelijkheid — de intelligentie kiest, het hart organiseert de feitelijke cyclus.

### 3.4 Waarheid uit observatie, niet uit modeltekst
"Wat gebeurde er?" komt uit `Observation` + `ExecutionReceipt`, reduceerbare tot canonieke staat. Dit is geen safety-eis maar een *cognitieve* eis: de lus kan alleen beslissingen verbeteren als de feedbackkant echte, reconstructeerbare signalen draagt, geen zelfgerapporteerde succesverhalen van het model.

## 4. Wat al bestaat — en wat niet

De onderdelen zijn onderzocht en bestaan als afzonderlijke ideeën:
- tool-calling agents ≈ propose + execute zonder strakke wereldtoestand;
- HuggingGPT — één LLM plant, selecteert specialistische modellen, voert uit, voegt samen;
- MRKL — taalmodel + neurale experts + deterministische redeneermodules;
- Toolformer — een model leert wélke API, wanneer, met welke argumenten;
- CoALA — komt het dichtst bij het harness/architectuur-onderscheid (geheugen, interne/externe acties, besliscyclus rond een LLM);
- ROS-actions/skill-frameworks — capabilities + feedback op robots;
- workflow-engines — duurzame stappen + retries;
- MCP/plugin-hosts — tools achter schemas.

**Wat daarmee nog niet bestaat is het volledige Engine:** blijvende identiteit en continuïteit, één levende wereldtoestand over meerdere werelden, een hart dat zelfstandig aandacht/doelen/gebeurtenissen beheert, algemene én specialistische breinen die samen ervaring opbouwen, tools en apparaten als delen van dezelfde handelingsruimte, en het leren welke brain/tool-combinatie wanneer werkt. Dát is de eigenlijke realisatieruimte, positief geformuleerd — niet "is het een ding?" maar "dit is het ding dat nog niet bestaat en dat we bouwen."

## 5. De twee werelden en de gedeelde kern

De eerste realisatie moet de gedeelde cognitieve kern *demonstrabel last dragen* op twee ongelijksoortige werelden. Dat betekent: de kern bevat de lus, de orchestratie, de aandachts-/doel-/ervaringstoestand, de snapshot/reduce-logica en de brain/tool-aanroep-protocol; de adapters en wereldtools zijn genuinely plug-in, geen fork per wereld. De sterke claim is niet "twee adapters werken" (zwak, baseline) maar "dezelfde cognitieve lus boekt niet-triviale meerstapsdoelen op beide werelden, met wisselbare breinen en reconstructeerbare staat." Dat is de realisatie die de goal bindt.

## 6. Risico's op het pad naar realisatie (geen existentietwijfel)

Deze blijven risico's om te managen, niet een lens die het concept ter discussie stelt.

- **Gedeelde kern te licht.** Risico dat de "kern" in de praktijk voornamelijk logging + per-adapter if/else blijkt, en het cognitieve werk in de adapters/world-tools zit. Te managen door als succesmaat te eisen dat de gedeelde laag substantiële cognitieve verantwoordelijkheid draagt (orchestratie, staat, ervaring, lus), niet alleen serialisatie.
- **Orchestratie die in het model lekt.** Risico dat de lus feitelijk in het algemene brein woont (recursieve modelloop) en Engine weer een harness wordt. Te managen door te toetsen dat de lus ook draait met een *fixture-brein* (vaste plannen), niet alleen met een LLM.
- **Staat die in context leeft.** Risico dat operationele staat stiekem in de promptgeschiedenis kruipt en bij model/procesverlies verdwijnt. Te managen door de reconstructietest: replay → zelfde canonieke staat.
- **Approval-burden die autonoom handelen smoort.** Risico dat de mens per stap moet goedkeuren, waardoor Engine een trage afstandsbediening wordt. Te managen door in de eerste realisatie (sandbox) de autorisatieschil dun te houden en autonome meerstapsuitvoering de norm te maken.
- **Ambient authority in adapters.** Risico dat een adapter meer kan dan de Engine-cyclus bedoelt (OS-rechten los van de lus). Voor de sandbox is dit beperkt; wordt relevant zodra de wereld buiten de temp-workspace reikt.
- **Roadmap-realisme.** Eén implementer + volledige testlast is zwaar. Voor de *eerste realisatie* (cognitieve kern op twee sandbox-werelden) is de scope kleiner dan de volledige 9–16-weken-constitution; dat is juist het punt van "kern eerst."

## 7. Verhouding tot veiligheid (de niet-drift-positie)

Beide uitersten zijn drift. Dit is de gebalanceerde positie:

- Safety is een schil, geen definitie van Engine. Akkoord.
- De eerste realisatie is sandbox; daar is de schil natuurlijk dun (temp-dir-isolatie, getypeerde tools, reconstructeerbare staat). Dat is geen roekeloos uitstel, maar de juiste schildikte voor het lab.
- Safety groeit waar het systeem groeit: richting netwerk, fysiek, mens-nabij. Dat is een tweede, later spoor dat de eerste realisatie niet mag blokkeren.
- Wel blijft gelden: de cognitieve lus mag niet zo worden ingericht dat autonoom handelen structureel onveilig wordt *vanaf dag één* — dus de schil is dun maar niet afwezig, en de architectuur laat ruimte om hem later aan te zetten zonder de kern te herschrijven.

Dit eert zowel "safety verdringt de kern niet" als "safety wordt niet roekeloos weggestemd."

## 8. Wat de eerste realisatie moet tonen (succescriteria, gebonden aan de goal)

Wél meten:
- de lus voltooit **meerstapsdoelen** op beide werelden (niet één demo-stap);
- **zelfde cognitieve kern** op twee heterogene werelden;
- **breinen wisselbaar**: fixture-brein en LLM-brein achter dezelfde interface;
- **state/ervaring overleven** modelcalls en procesherstarts;
- **werkelijke resultaten** beïnvloeden volgende beslissingen (lus is niet blind);
- **partial failure expliciet** — geen "succes" uit modeltekst bij een half uitgevoerde actie;
- de **gedeelde kern is plug-in** voor de tweede wereld, geen fork.

Expliciet niet nodig voor de eerste realisatie (komt later, op hun eigen spoor): autorisatie-UX, deny-by-default-policy-theater, hardware-e-stop, multi-tenant-isolatie, skill-signing, Umwelt-integratie. Deze zijn niet afgewezen — ze staan op het juiste moment in de wachtrij.

## 9. Eindoordeel

Engine is een levend-systeem-claim, geen safety-runtime-claim en geen harness-claim. De identiteit is helder en hoeft niet opnieuw onderhandeld. De realisatieruimte is reëel en deels onbezet: een duurzaam hart dat één algemeen brein, meerdere specialistische breinen, gedeelde wereldtools, blijvende staat en ervaring tot één continu handelend systeem maakt — over minstens twee heterogene werelden — bestaat als geheel nog niet, ook al bestaan de bouwstenen afzonderlijk.

De eerste realisatie moet de cognitieve kern zwaar maken op beide werelden, met wisselbare breinen en reconstructeerbare staat, autonoom meerstapsdoelen boeken, en de autorisatie-/safety-schil dun houden (passend bij sandbox) zonder het latere aanschakelen ervan onmogelijk te maken. Dat is haalbaar in dagen/weken voor een eerste voelbare kern, in plaats van een 9–16-weken-constitution die de kern achter guardrails begraaft. De risico's zijn executief (kern te licht, lus lekt in model, staat in context, approval-smoor) en goed te managen zolang de succescriteria uit §8 bindend blijven.

Oordeel: bouwbaar, en waard om te bouwen — als de cognitieve kern de eerste burger van de realisatie is en safety zijn schil-dikte naar het domein krijgt, niet vóór de kern en niet in plaats van de kern.
