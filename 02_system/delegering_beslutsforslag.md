# 3c-1 – beslutsförslag för delegering mellan team

> **Datum:** 2026-10-27. **Version:** 0.1. **Status:** rekommendationerna A0 och A–K
> godkända av operatören i chatten 2026-10-27, utan avvikelser, loggat som **B-039**.
> **Omfattning:** endast Markdown. Ingen kod, databasändring, ny behörighet eller
> ändrad körpolicy införs genom dokumentet; bygget följer §11.
> **Bygger på:** B-016 och B-026 (`agentekosystem.md` §6.1), de valda startgränserna i
> [`harness.md`](harness.md) §6.3, §10.1–10.2 och §10.4, B-037 (verksamhetsbehov styr) och
> B-038 val M (ett team åt gången i OC-3 tills 3c-1 finns).
> **Ägare:** harness (tvärgående agentekosystem). Berör projekt 10 (OC-3) och projekt 1.

## 1. Sammanfattning

Delegering betyder att en ledande agent mitt i sin körning ger ett annat team ett
avgränsat uppdrag och får tillbaka ett strukturerat svar som verktygsresultat.
Grundreglerna är redan valda i `harness.md` §10.2: barnet kör som mottagarteamets
ledande agent med egen identitet, profil och databasroll; kontexten är en sammanfattning
och referenser; djup högst 2, högst 3 barn per rot, inga cykler, sekventiell körning
och en gemensam rotbudget på 5 USD, 60 modellsteg, 90 verktygsanrop och 900 sekunder.

Det som återstår att avgöra är **vilka team som får delegera till vilka, hur mandat och
personuppgifter hanteras över teamgränsen, när verktyget alls visas och hur väntan och
återstart fungerar**. Förslaget nedan begränsar första leveransen till paret
**compliance → aktuarie** utan personuppgifter och utan godkännandeväntan, och bygger
mekaniken så att fler par kan öppnas genom granskad konfiguration.

**Ärlig bedömning av verksamhetsnyttan:** kända flerteamprocesser, som
parameterändringen, går redan genom flödesmotorn med grindar. Delegeringens nytta
ligger i frågor som inte följer ett fast flöde – främst OC-3 *Fråga bolaget* och
handläggarens behov av regeltolkning i ett ärende. Första paret ger ett avgränsat
verksamhetsvärde (aktuariell granskning av en tolkning); den större nyttan kommer med
OC-3 och par 2. Val A0 låter operatören skjuta upp bygget om annat bedöms viktigare.

**Byggordning enligt B-035:** 3c-1 ska byggas efter 3c-V. Det som återstår av 3c-V är
den skarpa körningen mot Lakebase, som väntar på att PR-ITP1 v1.0 börjar gälla
2026-11-01. 3c-1 ändrar loopen och dispatchern som flödet använder. Delegeringen är
därför avstängd som standard, och flödets befintliga regressionstester ska gå gröna före
merge. Om operatören vill hålla B-035:s ordning strikt kan bygget i stället börja efter
körningen den 1 november; designbeslutet kan ändå fattas nu.

## 2. Beslutsval

| Val | Rekommendation | Alternativ och avvägning | Avsnitt |
|---|---|---|---|
| A0 | Bygg 3c-1 nu, avgränsat enligt valen nedan | Vänta tills OC-3 eller ärendeflödet (F5-6) visar konkret behov: inget oanvänt bygge, men OC-3 måste då börja med två separata beställningar och mekaniken byggs under tidspress senare | §1 |
| A | Första aktiva paret: **compliance → aktuarie**. Par 2, **forsakring → compliance** (B-011:s eskalering), öppnas i en senare leverans efter F5-6 och val D | Öppna båda paren direkt: större nytta, men par 2 kräver PII-skyddet i val D och verifierat ärendeflöde. Endast par 2: störst verksamhetsnytta men högst risk som första leverans | §3 |
| B | Barnet får **bara mandat som betrodd kod redan utfärdat** och som mottagarens profil får ta emot. Modellen kan aldrig skapa ett mandat. Utan mandat är mandatkrävande verktyg dolda för barnet, som i dag | Låt föräldern föreslå ett nytt mandat som operatören godkänner innan barnet startar: kraftfullare, men en ny godkännandeväg utanför flödesmotorn. Kända processer med mandatgrind fortsätter i flödesmotorn | §4 |
| C | Verktyget `delegate_to_team` visas **bara när det betrodda uppdraget uttryckligen tillåter delegering** till namngivna team (standard stängt). OC-3-beställningar och flödessteg kan slå på det; ärendekörningar inte i första leveransen | Visa verktyget i alla körningar för agenter med `delegates_to`: enklare, men varje körning får en dold möjlighet att förbruka rotbudget och utöka arbetet | §5 |
| D | Dataklassen kan skärpas men inte sänkas: en körning med synliga PII-verktyg får inte delegera till ett team utan PII-mandat. Par 2 öppnas först med en **strukturerad PII-fri fråga** (frågetyp, regelreferenser, kort fritext som prövas mot ärendets kända identifierare) | Tillåt fritext från PII-körningar med enbart mönsterkontroll: smidigare men regex är inget säkerhetsskydd (`harness.md` §5.3). Förbjud par 2 helt: säkrast, men B-011:s eskalering blir kvar som ren operatörskö | §6 |
| E | **Synkron** körning: barnet körs inom förälderns verktygsanrop och svaret returneras direkt. Ingen bakgrundsarbetare krävs | Asynkront via bakgrundsarbetaren (B-036): rätt på sikt, men arbetaren finns inte och skulle blockera 3c-1 | §7 |
| F | Betrodd kod bestämmer budgeten: barnets tak = mottagarprofilens tak, avsmalnat av vad som återstår i rotbudgeten. Barnets förbrukning bokförs i rotbudgeten, inte i förälderns segmenttak. Modellen anger ingen reservation | Låt modellen föreslå ett belopp inom taket: mer flexibelt men öppnar för att en modell styr kostnad, vilket `harness.md` §6.3 utesluter | §7 |
| G | Föräldern får barnets **strukturerade resultat** (status, sammanfattning, schemaresultat, osäkerheter, källreferenser, kostnad). Barnets utkast visas som referenser för operatören; föräldern läser dem inte | Ge föräldern läsrätt till barnets arbetsyta: rikare svar, men bryter principen att föräldern inte får mer än barnets resultat | §8 |
| H | Idempotens per `task_id`, som harness härleder ur förälderns run-id och call-id. Samma beställning igen ger samma barnresultat; ett barn med okänt utfall ger `reconciliation_required` och ingen ny körning | Ingen idempotens i första leveransen: enklare, men dubbla barn och dubbel kostnad vid återförsök | §9 |
| I | Väntan sprids uppåt: om ett barn slutar `waiting_approval`, `needs_human` eller `reconciliation_required` slutar föräldern med samma status och barnets referenser. Fortsättning över kedjan byggs när ett aktivt par kan vänta | Bygg länkad fortsättning genom hela kedjan direkt: komplett, men inget av paren i val A kan i dag skapa ett förslag som väntar | §9 |
| J | Nya journalhändelser `delegation_requested`, `delegation_denied`, `delegation_started` och `delegation_returned`; barnets `run_started` bär `parent_run_id`, `root_run_id`, `depth` och `task_id`. Operatörscentralens kostnadsunderlag ändras inte (B-038 §4.3 räknar unika AI-försök) | Egen delegeringslogg vid sidan av körjournalen: tydligare separat, men två källor att stämma av | §10 |
| K | Aktuarieteamets mandattext utvidgas till **aktuariell granskning och beräkningsunderlag på beställning av compliance**, utan nya poddar eller verktyg. Beståndsinsikten kräver fortfarande ett godkänt parametermandat | Behåll mandatet oförändrat: paret blir då bara möjligt för uppgifter som redan ryms i dagens text | §3 |

## 3. Första paret: compliance → aktuarie

**Varför detta par först.** Inget av teamen har personuppgifter, aktuarien har ingen
skrivande operation i tjänstelagret och kan därför inte skapa förslag som väntar, och
båda teamen har egna begränsade databasroller i Lakebase sedan 2026-10-26
(`agent_compliance`, `agent_aktuarie`). Paret prövar hela mekaniken – identitet,
budgetbok, resultat, journal, idempotens och nekanden – med minsta möjliga risk.

**Vad aktuarien kan göra som barn.** Utan parametermandat ser aktuarien
`read_regulatory_document` och `list_regulatory_documents` (inklusive aktuariell grund
och parameterregister), `get_product_parameters`, `calculate_premium_preview` och
`write_draft`. Det räcker för till exempel:

- granska om en tolkning stämmer med den aktuariella grunden och parameterregistret,
- ange vilka beräkningsregler och parametrar som berörs,
- räkna exempelpremier enligt gällande parametrar som underlag,
- skriva ett kort aktuariellt utlåtande som utkast.

Beståndsinsikten (`estimate_parameter_change_impact`) förblir dold utan godkänt
parametermandat och nås fortsatt genom flödet `rule_change_parameter` med grind 1.

**Konfiguration vid aktivering** (granskad ändring i `ecosystem.yaml`):
`delegation.enabled: true`, `delegates_to: [aktuarie]` för teamet `compliance` och för
`compliance_agent`, och en ny podd `delegering` med verktyget `delegate_to_team`
monterad på compliance (`agentekosystem.md` §5-tabellen). Delegeringsmålet
`kommunikation` hos försäkringsteamet ligger kvar som namn; ett mål utan aktiv
ledande profil ger nekande utan modellanrop.

**Par 2, forsakring → compliance**, är B-011:s eskalering från handläggaren när ett
ärende väcker en regelfråga. Det öppnas som egen leverans när ärendeflödet är verifierat
(F5-6, tidigast 2026-11-01) och PII-skyddet i §6 är byggt och provat. Tills dess
registreras `needs_compliance` för operatören som i dag.

## 4. Mandat och referenser

Uppdraget följer kontraktet i `harness.md` §10.1. Modellen fyller bara `target_team`,
`goal`, `background`, `constraints`, `expected_output` och `references`. Harness fyller
`task_id`, `root_run_id`, `parent_run_id`, `depth`, `flow_id`, `flow_step_id`,
gränser och eventuella mandatreferenser.

- **Referenser är pekare, inte rättigheter.** Varje referens prövas mot ett format
  (regelhandtag, parameternyckel, utkastreferens) och avvisas om den liknar en
  personuppgift. Barnet läser den bara om dess egen gateway eller tjänst tillåter det.
- **Mandat förs bara vidare, aldrig nyskapas.** Ett `execution_scope_ref` eller
  `parameter_change_ref` får följa med endast om föräldern själv bär det från sitt
  betrodda uppdrag och mottagarens profil får använda den typen av mandat. I första
  paret bär compliance inget sådant mandat, så barnet startar utan.
- **Begränsningar kan bara skärpas.** Barnets `deny_skills` och `allowed_effects` kan
  smalnas av men aldrig vidgas; barnets profil byggs med `compile_profile` som alla
  körningar.
- **`expected_output`** väljs ur de resultatscheman som finns i `agents.results`, eller
  utelämnas. Ett okänt schema nekas.

## 5. När verktyget visas

`RunRequest` får ett nytt betrott fält, förslagsvis `delegation_targets`, som anger
vilka team körningen får delegera till. Standard är tomt. Verktyget visas bara om
fältet, teamets och agentens `delegates_to` och `delegation.enabled` alla tillåter
målet. Beställare som kan sätta fältet:

- **OC-3** (operatörens fråga till ett team) – när operatören väljer att tillåta samordning.
- **Flödessteg** – när flödesdefinitionen uttryckligen anger det.
- **Uppdragsmallar** i `agents.assignments` – inte de befintliga mallarna, som förblir utan.

Ärendekörningar (`run_case`) får inte delegering i första leveransen.

## 6. Personuppgifter över teamgränsen

Grundregel: en körning vars profil har synliga PII-verktyg är PII-klassad. Dess
beställningar får bara gå till ett team vars profil är byggd för samma mandat.
Compliance har inget PII-mandat, så par 2 kräver en granskad transformation:

- **Frågetyp** ur en fast lista: tillämplighet, tolkning, giltighet, motstridiga regler.
- **Regelreferenser**: produktregler, tolkningar och källhandtag som finns i regelverksgatewayen.
- **Kort fritext** (förslagsvis högst 500 tecken), som harness prövar mot ärendets kända
  identifierare – den försäkrades personnummer, namn, födelsedatum, försäkringsnummer
  och arbetsgivare ur mandatet – och mot allmänna personnummer- och datummönster.
  Träff ger nekande, inte maskering.
- **Inga** ärendenummer, belopp per person eller referenser till personer följer med.

Svaret från compliance är PII-fritt och kan föras tillbaka till ärendet. Detta byggs och
provas i par 2-leveransen; första leveransen nekar alla delegeringar från PII-körningar.

## 7. Körning och budget

- **Synkront och sekventiellt.** Barnet körs inom förälderns verktygsanrop med samma
  loop, dispatcher och journal som andra körningar, med mottagarens tjänstelager
  (teamets databasroll, `AgentRuntime.team_services`) och mottagarens modellroll.
- **Gemensam budgetbok.** En budgetbok per rot håller förbrukat och reserverat.
  Före start reserveras barnets tak; efteråt bokförs verklig förbrukning och resten
  frigörs. Okänd kostnad hålls kvar som reserverad, aldrig noll.
- **Barnets tak** = minimum av mottagarprofilens tak och det som återstår av roten.
  Räcker roten inte till mottagarens minsta rimliga körning nekas beställningen utan
  modellanrop.
- **Förälderns egna tak** räknar förälderns modellsteg och verktygsanrop; delegeringen
  räknas som ett verktygsanrop. Barnets förbrukning räknas i roten.
- **Taken** djup ≤ 2, högst 3 barn per rot och inget team två gånger i samma kedja
  prövas före start. I första paret är djupet i praktiken 1, eftersom aktuarien inte
  har några delegeringsmål.

## 8. Resultat till föräldern

Föräldern får ett verktygsresultat med `task_id`, barnets `run_id`, `status`,
`summary`, `output` (när ett schema begärts), `assumptions`, `uncertainties`,
`evidence_refs`, `pending_approvals` och `cost_usd`. Statusen är aldrig en beslutstoken.
Barnets utkast listas som referenser för operatören. Ett barn som slutar `blocked`,
`failed` eller `limit_reached` ger föräldern ett strukturerat fel som modellen kan ta
hänsyn till men inte kringgå genom att beställa om samma sak (val H).

## 9. Idempotens, väntan och återstart

- `task_id` härleds av harness ur förälderns run-id och call-id. Samma beställning i samma
  körning hittar samma barn i stället för att skapa ett nytt.
- Ett barn som slutar `waiting_approval`, `needs_human` eller `reconciliation_required`
  får föräldern att sluta med samma status, med barnets run-id och eventuella approval-id.
  Ingen modell står och väntar.
- Krasch under barnets körning ger `reconciliation_required` för både barn och förälder
  (`harness.md` §6.4, §10.4). Ingen automatisk omkörning.
- Länkad fortsättning genom kedjan (barnets fortsättning följd av förälderns) byggs när
  ett aktivt par kan vänta på godkännande – tidigast med par 2.

Första leveransen håller barnregistret i körjournalen under `logs/agent_runs/`, i linje med
val J i B-035. Lagring av körjournalen i Lakebase är en separat backlogpunkt.

## 10. Spårbarhet och kostnadsredovisning

| Händelse | Var | Innehåll |
|---|---|---|
| `delegation_requested` | förälderns journal | task-id, mål, uppdragets hash, referenser, mottagare |
| `delegation_denied` | förälderns journal | skäl (mål, djup, antal, cykel, budget, PII, referens) |
| `delegation_started` | förälderns journal | barnets run-id, reservation, djup |
| `delegation_returned` | förälderns journal | status, förbrukning, rotens förbrukning |

Barnets egen journal börjar med `run_started` som bär `parent_run_id`, `root_run_id`,
`depth` och `task_id`. Fritext lagras som hash och längd som i dag (`harness.md` §8.1).
Operatörscentralens kostnadsunderlag (OC-2) räknar unika AI-försök per körning och
hänför kostnaden till teamet som gjorde försöket; barnens försök kommer därför med
utan ändring, och `RunResult.cost_usd` eller rotsummor adderas inte (B-038 §4.3).

## 11. Föreslaget genomförande efter beslut

1. **Kontrakt:** `DelegationRequest`/`DelegationResult`, podden `delegering`, fältet
   `delegation_targets` i `RunRequest` och valideringen i `ecosystem.py`.
2. **Budgetbok** per rot med reservation, bokföring och frigörelse; fortsättningar
   och barn använder samma bok.
3. **Verktyget i dispatchern och loopen:** prövning före start, barnets profil och
   tjänstelager, synkron körning och resultatprojektion.
4. **Idempotens och statusspridning** enligt §9.
5. **Tester mot FakeProvider:** lyckad delegering, alla nekandeskäl, budget som tar
   slut i barnet, barn som försöker använda förälderns verktyg, påhittade mandat och
   referenser, dubbel beställning, krasch i barnet och journalens innehåll
   (`harness.md` §11.1, raden om barn, högre rättigheter och cykler).
6. **Röktest med riktig modell** i demodatabasen och `svc_test` med båda teamens roller,
   med kostnadstak. Inga Lakebase-ändringar behövs: rollerna finns och inga tabeller tillkommer.
7. **Dokumentation:** `harness.md`, `agentekosystem.md`, aktuarieagentens instruktion
   (val K), skillkatalogen (genererad) och `ATT_GORA.md`.

Par 2 (forsakring → compliance) och fortsättning genom kedjan är egna, senare leveranser.

## 12. Förslag till beslutspost

Om valen godkänns föreslås en post i `BESLUTSLOGG.md` (numret sätts vid loggning):

> **3c-1: delegering mellan team.** Delegering byggs synkront med gemensam rotbudget,
> idempotens per task-id och spridd väntan. Första aktiva paret är compliance → aktuarie
> utan personuppgifter; barnet får bara mandat som betrodd kod redan utfärdat. Verktyget
> visas bara när det betrodda uppdraget tillåter det. Forsakring → compliance öppnas
> senare med en strukturerad PII-fri fråga. Aktuariens mandat omfattar granskning och
> beräkningsunderlag på beställning av compliance.
