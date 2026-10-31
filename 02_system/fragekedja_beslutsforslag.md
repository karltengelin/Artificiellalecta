# OC-3a – beslutsförslag för första fråge- och rapportkedjan

> **Datum:** 2026-10-27. **Version:** 0.2. **Status:** valen A–L godkända av operatören i chatten
> 2026-10-27 (”godkänner alla A-L”), utan avvikelser, loggat som **B-041**.
> **Omfattning:** endast Markdown. Ingen kod, databasändring, behörighet eller körpolicy
> ändras genom dokumentet; bygget följer §11.
> **Bygger på:** [projekt 10:s avgränsning](../projekt/10_operatörscentral/PROJEKTPLAN.md)
> ("Pågående bygguppdrag", tidigare "Nästa bygguppdrag att förbereda"), [riktningsgranskningen](riktningsgranskning_2026-10-27.md),
> B-038 med [OC-0-underlaget](operatörscentral_beslutsforslag.md) §4.4, §6 och §7, B-035/B-036
> (flödesmotorn), B-039 (delegering) och B-040 (Postgres-prov).
> **Operatörens besked 2026-10-27:** `get_company_metrics` är inte känslig och behöver inte
> vara `HUMAN_ONLY`; den ska bli agentläsning (val C).
> **Ägare:** projekt 10 med projekt 2. Harness och tjänstelager: Claude. Webb, mallar och
> måttunderlag: Codex (§11).

## 1. Sammanfattning

Leveransen är det första hela arbetsförloppet genom centralen: **operatören ställer en
beståndsfråga, aktuarieteamet besvarar den med behöriga verktyg, svaret blir en A4-rapport,
operatören granskar den och rapporten går att hitta igen** – från centralen och från
aktuariens teamyta. Frågan gäller registrerade försäkrade vid läsdatum och betalmarkerade
premier för en vald avslutad månad, med begränsningar.

Förslaget bygger nästan helt av befintliga delar:

| Behov | Återanvänds | Nytt |
|---|---|---|
| Uppdragets livscykel, väntan, fel, granskning | Flödesmotorn (3c-2): versionerade steg, hashbundna grindar, avstämning efter avbrott, tabellerna finns redan i Lakebase | Flödestypen `company_question` |
| Data | `get_company_metrics` och ledningsmåtten (OC-1), samma definitioner som centralen | Nivån `AGENT`, montering för aktuarien, kolumnbegränsad läsrätt |
| Tal i svaret | Resultatlagrets mönster: betrodd kod bär verktygets resultat oförändrat (`agents/results.py`) | Resultatschemat `company_answer` |
| Rapport | A4-mallen (B-034) | Rendering från strukturerat svar, versionerad leverans |
| Identitet | B-038 val P–Q | Lokal operatörsinloggning med serversession |
| Arbetsvy | Centralen (OC-1), `FlowConsole`-mönstret | Uppdragslista, granskningsvy, minsta teamyta för aktuarien |

Ingen ny databastabell, ingen bakgrundsarbetare, ingen delegering och ingen ny agentprofil.

## 2. Beslutsval

| Val | Rekommendation | Alternativ och avvägning | Avsnitt |
|---|---|---|---|
| A | **Frågeomfång:** en frågetyp, *beståndsöversikt*, med en vald avslutad månad (någon av de elva föregående) och valfri precisering i fritext. Svaret har status `answered`, `partial`, `unavailable`, `needs_clarification` eller `failed` (OC-0 §6.3) | Helt fri fråga: bredare men utan granskat stöd för de flesta frågor. Enbart fast mall utan fritext: enklast men prövar inte avgränsning av frågor utanför stödet | §3 |
| B | **Mottagare: aktuarieteamet**, som projekt 10 anger. Teamet är utan personuppgifter och har analysansvaret. **Aktuarieagenten svarar** som teamets ledande agent; den planerade Data scientist-agenten byggs inte i första kedjan (§3) | OC-0 §6.1 föreslog `forsakring` för bestånd/premier; handläggaragentens mandat är ärendebundet med personuppgifter och passar inte ett bolagsövergripande aggregat. Låta Data scientist-agenten svara: närmare dess mandat, men kräver en ny profil och delegering inom teamet utan ett verktyg som skiljer den från aktuarien | §3 |
| C | **`get_company_metrics` blir `AGENT`** (läsning, `pii=False`, småcellsskydd kvar) och monteras i podden `bestand`, alltså bara för aktuarien. Operationen ändras inte | Behåll `HUMAN_ONLY` och låt betrodd kod läsa åt agenten: agenten blir då bara textförfattare. Operatören har avgjort att operationen inte är känslig | §4 |
| D | **Kolumnbegränsad läsrätt** för `agent_aktuarie`: `policy_benefits` (id, försäkring) och `premium_transactions` (förmån, typ, status, betaldatum, belopp) – inte lön eller beräkningsunderlag. `RoleGrants` utökas med kolumnlistor | Full läsrätt på båda tabellerna: enklast, men rollen får läsa pensionsgrundande lön per rad, vilket B-035 val I undvek. Betrodd anslutning för aggregatoperationer: kringgår rollen som försvarslinje | §4 |
| E | **Uppdragets livscykel är flödesmotorn** med en ny flödestyp `company_question`: svar → rapport → granskning → leverans. Flödes-id är uppdragsreferensen | Ny uppdragstabell: egen livscykel men dubblerar versionering, grindar och avstämning och kräver migrering. Bara körjournalen: ingen varaktig status eller granskning | §5 |
| F | **Tal kommer bara från verktyget:** harness bär `get_company_metrics`-resultatet oförändrat i svaret. Modellens text får inte innehålla tal som saknar motsvarande observation; annars blir steget `needs_human` | Låt modellen skriva talen och granska i grinden: människan blir enda kontrollen av siffror | §6 |
| G | **Leveransen är versionerad:** Markdown och PDF sparas under `logs/deliveries/<flow_id>/v1/` (gitignorerat) med manifest och kontrollsummor; flödet binder hasharna. Grinden binder rapportens hash. Avslag stoppar uppdraget; ny beställning blir nytt uppdrag som pekar på det avslagna | Lagra PDF i databasen: följer miljön men gör tabellerna tunga. Omarbetning inom samma uppdrag: följer OC-0 §4.4 fullt ut men kräver ny återgång i flödesmotorn | §7 |
| H | **Inloggning enligt B-038 val P:** lokalt namngiven operatör, lösenfras som Argon2id-hash i `.env` (operatören sätter den med ett skript), serverlagrad session, sessionsbunden CSRF, försöksbegränsning. Första leveransen körs över `http://127.0.0.1`; HTTPS krävs före OC-5:s styrning eller annan bindning än loopback | HTTPS redan nu med lokalt certifikat: följer OC-0 §7.1:s ordalydelse men kräver att operatören skapar och litar på ett certifikat innan kedjan kan provas | §8 |
| I | **Session krävs för alla skrivande handlingar på bolagsfrågor:** starta, köra nästa steg, granska och avbryta. Läsning och de befintliga flödena i `/floden` och `/parametrar` (B-036) är oförändrade | Kräv inloggning för hela webben: enhetligt men bryter B-036:s väg och handläggar-UI:t | §8 |
| J | **Synkron körning:** när frågan startas körs svar och rapport direkt, och flödet stannar vid granskningsgrinden. En körning åt gången per process | Bakgrundsarbetare: rätt på sikt men F5-7 är inte byggd och ska kopplas till ett eget självständigt arbetsfall | §5 |
| K | **En läsprojektion för uppdrag** (`AssignmentView`) som centralen och teamytan visar likadant. Teamytan för aktuarien är minsta möjliga: teamets uppdrag, status och leveranser, inte hela OC-8 | Bygg hela OC-8 nu: större omfång än kedjan kräver | §9 |
| L | **Arbetsfördelning och ordning enligt §11:** Claude bygger tjänstelager, roll, harness och flöde; Codex bygger inloggning, rendering och webbvyer. Gränssnitten i §10 låses först | En byggare för allt: färre överlämningar men långsammare och mot AGENTS.md §4.2 | §10–11 |

## 3. Frågan och svaret (A, B)

**Beställningen** (`CompanyQuestion`, OC-0 §6.2) är flödets indata och byggs av betrodd kod:

| Fält | Källa |
|---|---|
| Frågetyp | Vald i formuläret; första versionen har bara `portfolio_overview` |
| Månad | Vald bland de elva senaste avslutade månaderna (inom operationens gräns; pågående månad ingår inte) |
| Precisering | Valfri fritext, högst 500 tecken. Den är data: den kan inte ändra team, verktyg, period eller miljö |
| Beställare | Den inloggade operatören (val H), aldrig ett formulärfält |
| Team | `aktuarie`. Övriga team visas som ej tillgängliga med beroendet, utan modellanrop (OC-0 §6.1) |
| Miljö | Webbens aktiva miljö (demo, `svc_test` eller Lakebase) från miljöväljaren |
| Mått | `insured_registered_count` och `premium_paid_recorded_sek` med definitionsversion (projekt 2:s datakontrakt) |
| Körbild | Hash av effektiv körpolicy och modellkonfiguration, utan hemligheter (OC-0 §6.2 före OC-5) |

**Vem i teamet som svarar.** Aktuarieagenten tar emot och besvarar frågan. Det följer
B-026: operatören och andra team når ett team genom dess ledande agent, aldrig direkt
genom en specialist. Teamets planerade specialist, [Data scientist-agenten](agenter/data-scientist-agent.md),
har ett mandat för dataanalys som ligger nära frågan, men den är inte byggd och har varken
profil, skills eller dataåtkomst. Enligt B-008 införs en specialist när mandatet skiljer sig
väsentligt, och en aggregatläsning med två mått och en kort tolkning kräver det inte.

Data scientist-agenten blir aktuell när en fråga kräver verktyg som aktuarien inte ska ha,
till exempel statistik över tid, egna datamodeller, kontroll av datakvalitet eller läsning
via Databricks BI och Genie. Då har den ett konkret uppdrag och egna verktyg. Den byggs då
som specialist i teamet, med delegering inom teamet från aktuarieagenten; dagens delegering
(B-039) går bara mellan team. Det är ett eget designbeslut efter första kedjan.

**Uppdraget till aktuarien** är en betrodd mall i `agents/assignments.py`: mål, begränsningar
och resultatschema kommer från mallen, preciseringen följer med som bakgrund. Körningen
smalnas av till läsning och beräkning (`allowed_effects`), utan utkast och utan delegering.
Budget och tak är aktuarieteamets (1,00 USD, `harness.md` §6.3).

**Svaret** (`company_answer`) följer OC-0 §6.3: status, kort slutsats, observationer (val F),
definitioner med version, läsdatum och period, miljö, antaganden, begränsningar och nästa steg.
En fråga utanför stödet ska ge `unavailable` eller `needs_clarification` – det är ett godkänt
utfall, inte ett fel.

## 4. Data och behörighet (C, D)

**Operationen ändras inte.** `get_company_metrics` returnerar redan bara två aggregat med
läsdatum, period och tillstånd (`available`, `suppressed`, `failed`). Celler med 1–9 personer
döljs, och ett ogiltigt betaldatum ger `failed`. Ändringen är en rad i
`access_register.yaml` (`AGENT`) och en skill i podden `bestand` utan parametermandat.
Centralens egen läsning är oförändrad och fortsätter med handläggarens identitet.

**Databasrollen behöver mer.** `agent_aktuarie` får i dag läsa `insured_persons`, `policies`,
`policy_states`, `base_amounts` och `product_parameters`, men inte `policy_benefits` eller
`premium_transactions`. Operationen skulle alltså fallera i `svc_test` och Lakebase under
aktuariens roll, trots att den fungerar i SQLite. Val D ger kolumnrätt till exakt det som
aggregatet läser:

| Tabell | Kolumner |
|---|---|
| `policy_benefits` | `id`, `policy_id` |
| `premium_transactions` | `benefit_id`, `transaction_type`, `status`, `paid_date`, `amount_sek` |

`pensionable_salary_sek` och `calculation_basis` förblir stängda. `RoleGrants` får en
kolumnlista per tabell, `inspect_role` kontrollerar kolumnrätterna, och rollproven för
aktuarien utökas. Det är en ändring i `src/utils/agent_roles.py`, så B-040:s Postgres-regel
pekar ut rollproven; de körs med `--postgres` mot `svc_test`. Rättigheterna sätts i Lakebase
först efter backup och operatörens OK (AGENTS.md §4.5).

## 5. Livscykel genom flödesmotorn (E, J)

Flödestypen `company_question` har fyra steg:

| Steg | Slag | Vad händer | Resultat som binds |
|---|---|---|---|
| `answer` | agent (`aktuarie`) | Aktuarien läser måtten och skriver svaret enligt `company_answer` | Svaret med observationer |
| `render` | system | Betrodd kod bygger rapportens Markdown ur svaret och renderar A4-PDF (§7) | Leveransversion med kontrollsummor |
| `review` | grind | Operatören granskar rapporten och godkänner eller avslår | Hash av `answer` och `render` |
| `deliver` | system | Leveransen markeras godkänd med granskare och tid (`Delivery`, `QualityCheck` i OC-0 §4.4) | Godkänd version |

Motorn ger redan det acceptansvillkor 2 och 6 kräver: varaktig status
(`running`, `waiting_gate`, `failed`, `reconciliation_required`, `completed`, `rejected`),
villkorlig uppdatering mot version, ingen automatisk återupptagning efter krasch och
grindar som blir inaktuella om underlaget ändras. Ett avslutat agentsteg är aldrig en godkänd
leverans; det blir det först i `deliver`.

**Körning (J).** Start och de två första stegen körs i samma anrop och stannar vid grinden.
Det tar omkring en till tre minuter; sidan visar att arbetet pågår. Ett andra klick under
körningen stoppas, som i `FlowConsole`. Flödestabellerna finns i Lakebase sedan 3c-V och
skapas med övriga tabeller i demo och `svc_test`; ingen migrering behövs.

**Förhållande till B-036.** Flödet startas från centralen och är en ny bolagsfråga, så val I
gäller. De befintliga flödena i `/floden` behåller sin väg och får inget beroende till
inloggningen eller OC-5.

## 6. Tal och spårbarhet (F)

Resultatschemat `company_answer` följer samma mönster som beståndsinsikten i
`agents/results.py`: modellen skriver slutsats och begränsningar i ord, och harness lägger
till det faktiska verktygsresultatet från körningen. Harness kontrollerar innan svaret godtas:

- **Observationen kommer från verktyget.** Den kommer från ett lyckat `get_company_metrics`-anrop i körningen med den beställda månaden, och läsdatum och tillstånd följer med oförändrade.
- **Inga obelagda tal i texten.** Siffror i slutsatsen ska motsvara en observation, perioden eller ett datum. Ett obelagt tal ger `needs_human` med skälet.
- **Inga ersättningsvärden.** Ett dolt eller misslyckat mått får inte ersättas med en uppskattning. Svaret blir då `partial` eller `unavailable`.

Rapportens tabell med värden byggs av betrodd kod ur observationen, inte ur modellens text.
Körjournalen, kostnadsunderlaget (OC-2) och flödets steg bär samma `task_id` och flödes-id.

## 7. Rapport och leverans (G)

**Innehåll** enligt projekt 10: slutsats, definitioner med version, läsdatum och period,
datakälla och miljö, värden, kontroller, källreferenser och begränsningar. Rapporten anger
också uppdrags-id, granskningsstatus och mallversion.

**Rendering.** Betrodd kod bygger en Markdown-rapport med fast struktur och renderar den med
A4-mallen (B-034). Det är rapportmallens ägare (Codex) som tillhandahåller funktionen. Den tar
Markdown och metadata och returnerar PDF; den läser inga data själv. Presentationsmallen
ingår inte i första kedjan.

**Lagring.** `logs/deliveries/<flow_id>/v1/` innehåller `rapport.md`, `rapport.pdf` och
`manifest.json` (kontrollsummor, mall- och designversion, flödes-id, run-id, skapad, status).
Mappen är gitignorerad och skrivs bara av systemsteget. Flödets steg binder kontrollsummorna,
så en ändrad fil upptäcks. Ingen fil skickas eller publiceras, och rapporten blir inte
gällande dokument av att den finns i mappen.

**Avslag.** Ett avslag stoppar uppdraget som `rejected`, enligt flödesmotorns regel. En ny
beställning kan peka på det avslagna uppdraget (`supersedes`). Omarbetning inom samma
uppdrag, med flera leveransversioner, väntar tills flödesmotorn har en återgång.

## 8. Inloggning och rättigheter (H, I)

Följer OC-0 §7.1 med en avgränsning:

- En lokalt provisionerad operatör (`karl`). Lösenfrasen hashas med Argon2id och hashen ligger i `.env`. Operatören sätter den själv med ett nytt skript; inget lösenord skapas av agenter.
- Ogenomskinligt sessions-id i serverns minne. Det roteras vid inloggning och upphör efter 15 minuters inaktivitet eller 8 timmar. Utloggning återkallar det.
- Cookie med `HttpOnly`, `SameSite=Strict` och `Secure`. Chrome och Firefox godtar `Secure` på `http://localhost` och `127.0.0.1`; vilken webbläsare som stöds anges i driftbeskrivningen.
- Formulärtoken bunden till sessionen, och ursprungs- och Host-kontroll som i dag.
- Högst fem misslyckade försök på fem minuter, sedan fem minuters väntan. Feltexten är generell, och loggen innehåller aldrig lösenord, sessions-id eller token.

**Avgränsning (H).** OC-0 §7.1 kräver HTTPS före lösenordsinmatning för styrning. Första kedjan
är ingen styrning, och servern lyssnar bara på loopback. Förslaget är att HTTPS införs med
OC-5 eller före annan bindning än `127.0.0.1`. Väljer operatören alternativet krävs ett lokalt
certifikat som operatören skapar.

**Vad sessionen ger (I).** Rätt att starta, köra, granska och avbryta bolagsfrågor. Den ger
inte `policy_admin`, nya poddar, personuppgifter eller databasroller. Beställare och granskare
är sessionens identitet; `HANDLAGGARE_ID` är inget inloggningsbevis.

## 9. Arbetsvyn (K)

`AssignmentView` är en läsprojektion över flöden av typen `company_question`: uppdrags-id,
fråga i kort form, team, beställare, skapad, status i klartext, steg, kostnad enligt körjournalen, senaste
leveransversion och granskningsstatus. Den byggs i harness och visas av webben.

| Yta | Innehåll |
|---|---|
| Centralen | *Fråga bolaget*: formulär (val A), tillgängliga och ej tillgängliga team, lista över uppdrag och detaljsida med steg, svar, rapport och granskning |
| Aktuariens teamyta | Teamets uppdrag med samma detaljsida. Första delen av OC-8; resten av teamytan (körningar, utkast, övriga uppdrag) kommer senare |

Pågående, väntande, felaktiga och avslutade uppdrag skiljs åt. Granskningen visar PDF:en
och svaret sida vid sida. Råa konversationer visas inte (riktningsgranskningen R-05).

## 10. Gränssnitt mellan byggdelarna

Låses före byggstart, eftersom Claude och Codex bygger på var sin sida av dem.

1. **Rendering.** `render_report(markdown: str, metadata: ReportMetadata) -> bytes` i
   `src/reporting/`, deterministisk för samma indata. Rapportens Markdown-struktur
   (rubriker och tabeller) dokumenteras i `06_design/rapportmall.md`.
2. **Uppdragsadapter.** En tunn adapter i harness, som `FlowConsole`:
   `start(question, actor)`, `get(flow_id)`, `list(team=None)`, `decide(flow_id, version, actor, decision, seen_hash)`,
   `cancel(...)` och läsning av leveransfiler via flödes-id och version. Webben rör inga
   modeller, sessioner eller filvägar direkt.
3. **Aktör.** Webben skickar en `Actor` som bara skapas ur en verifierad session.
4. **Mått.** Projekt 2:s datakontrakt (Codex) är källan till definitioner, versioner och
   förväntade avvikelsefall; testerna i båda delarna använder samma fall.

## 11. Byggordning och ansvar

| Steg | Claude (`src/agents`, `src/services`, `src/utils/agent_roles.py`) | Codex (`src/web`, `src/reporting`, `src/management`) |
|---|---|---|
| 0 | Detta designstopp | Projekt 2:s datakontrakt (pågår) |
| 1 | Val C och D: åtkomstnivå, podd, kolumnrätter, rollprov mot `svc_test` | Val H: inloggning, session, formulärtoken, lösenordsskript |
| 2 | Val E och F: `company_answer`, uppdragsmall, flödestypen, adaptern och leveranslagringen | Rendering enligt §10.1 och rapportens struktur |
| 3 | Integrationstester för hela flödet med testleverantör | Val K: vyer i centralen och aktuariens teamyta |
| 4 | Gemensamt: röktest mot riktig modell i demo och `svc_test`, visuell kontroll av rapporten, sedan Lakebase efter backup och OK | |

**Status 2026-10-27:** Claudes steg 1–3 är byggda. Åtkomstnivå, podd och kolumnrätter
(`src/services/access_register.yaml`, `src/agents/ecosystem.yaml`, `src/utils/agent_roles.py`);
resultatschemat `CompanyAnswer` med talkontroll (`src/agents/results.py`), uppdragsmallen
(`src/agents/assignments.py`), flödet (`src/agents/flows/definitions/company_question.py`),
leveranslagringen (`src/agents/deliveries.py`) och adaptern med `AssignmentView`
(`src/agents/flows/questions.py`). Integrationstester i `tests/test_agents_questions.py`.
Översättningen från aggregat till observationer är gemensam (`management.metrics.company_observations`);
centralens route kan gå över till den. Adaptern tar renderaren som argument. Codex operatörsinloggning (val H) är klar;
Codex rendering och webbvyer är lokalt byggda 2026-10-28; se
[rapportens struktur](../06_design/rapportmall.md#oc-3a-deterministisk-markdown-till-pdf) och
[webbvyer och anslutning](fragekedja_webb.md). Samordnat röktest med den ordinarie renderaren och
DM Sans återstår. Kolumnrätterna sattes i Lakebase 2026-10-31 efter backup `backups/20261031T124616Z` och operatörens OK, i samma körning som antagandebibliotekets läsrätt (A4, B-042); `get_company_metrics` fungerar med rollens egen anslutning.

*2026-10-28:* röktestskriptet för steg 4 (`scripts/diagnostics/smoke_test_question.py`) är klart och kört i demo med riktig modell: 19 av 19 kontroller efter två rättelser – talkontrollen godtar nu periodens sista dag (perioden enligt §6), och resultatschemat säger att en precisering utanför underlaget ger `unavailable`. Rapporten renderades provisoriskt. Kolumnrätternas torrkörning mot Lakebase passerar förkontrollen; `--apply` väntar på backup och operatörens OK.

*2026-10-31:* röktestet med OpenAI (`gpt-6-astra`) i demo, `--avvikelser` och `reporting.render_report` med Helvetica gav 19 av 19 kontroller, 0,23 USD. Rapporten granskades översiktligt; Codex visuella kontroll med DM Sans och webbvyerna återstår. Samma dag i `svc_test` med `claude-opus-5` och aktuariens begränsade testroll, inklusive kolumnrätterna: 19 av 19 kontroller, 0,31 USD, sedan operatören slagit på den avstängda Lakebase-endpointen.

*2026-10-31, läsbarhet:* på operatörens begäran skrivs rapporten för en VD. Svar, värden och begränsningar kommer först; definitioner, datakälla och det nya avsnittet *Så togs rapporten fram* (agent, modell, verktygsanrop med nivå och utfall ur körjournalen, `agents.trace`) sist. Aktuarien instrueras att skriva slutsatsen utan tekniska namn och inte upprepa datakontraktets fasta begränsningar. Samma spår finns för webbens avancerade vy genom `QuestionConsole.trace`. Röktest i demo med `claude-opus-5` och `--avvikelser`: 22 av 22 kontroller, inklusive den nya läsbarhetskontrollen, 0,29 USD.

Steg 1 och 2 kan gå parallellt eftersom filerna är åtskilda. Steg 3 för webben förutsätter
adaptern. Lakebase-ändringarna (kolumnrätter) samordnas enligt AGENTS.md §4.5 och krockar inte
med 3c-V och F5-6 den 1 november om de görs vid olika tillfällen.

## 12. Acceptans

Projekt 10:s sex villkor gäller. Så prövas de:

| Villkor | Prov |
|---|---|
| 1. Verifierad operatör ställer frågan och ser team och uppdragsreferens | Webbtester: utan session nekas, med session skapas flödet; fel team från formuläret nekas |
| 2. Följs från central och teamyta; körning, väntan, fel, utkast och granskad leverans skiljs åt | Samma `AssignmentView` i båda; flödestester för `failed`, `reconciliation_required`, `rejected` och `completed` |
| 3. Värden från behöriga verktyg; inga ersättningsvärden | Resultattester: obelagt tal, dolt mått, misslyckad läsning, fel månad |
| 4. Rapporten kan granskas, öppnas igen och följas till underlag | Leveranstester: kontrollsummor, manifest, ändrad fil upptäcks; visuell kontroll av PDF |
| 5. Normalfall, noll kontra saknat, småcellsskydd, nekad åtkomst, datakällsfel, fråga utanför stödet, misslyckad export | Fallen ur projekt 2:s datakontrakt i båda delarnas tester |
| 6. Upprepning gör inte gammal rapport aktuell | Ny beställning ger nytt uppdrag; avslaget uppdrag kan inte levereras; dubbelklick ger en körning |

## 13. Utanför första kedjan

Databricks BI och Genie, flera team eller delegering i frågan, bakgrundskörning,
presentationsexport, omarbetning inom samma uppdrag, kvalitetsmått i centralen,
personuppgifter och resten av OC-8. Kapitalförvaltning, FTA och premie-/betalningskedjan
har egna kommande uppdrag (ATT_GORA).

## 14. Förslag till beslutspost

Om valen godkänns föreslås en post i BESLUTSLOGG med valen A–L, operatörens besked om
`get_company_metrics` och avgränsningen av HTTPS i val H. Posten formuleras för godkännande
efter operatörens ställningstagande; den skrivs inte in av agenten.
