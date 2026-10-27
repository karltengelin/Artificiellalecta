# Handläggar-UI:t

> **Status:** 🟡 Under uppbyggnad i Fas 4 (delprojekt 1). **Byggt:** sök, översikt, löneunderlag och premiehistorik (S1); formulär för löneunderlag, fribrev och premierättelse (S2); godkännandekö och händelselogg (S3); anslutning av ny försäkrad, aktuell lön, kontaktuppgifter och arbetsgivare (S5). **Verifierat skarpt i Lakebase 2026-10-12** (S6, se ATT_GORA): verifieringsposten AL-000499.
> **Bygger på:** B-017 (människa som fullständig operatör), B-020 (handläggar-UI före kundportal), B-028 (tjänstelagret), B-032 (anslutning, stamdata och arbetsgivare), B-036 (försäkringsteamets område på plattformen)
> **Kod:** `src/web/` · **Start:** `python scripts/web/start_ui.py` · **Tester:** `tests/test_web_*.py`
> **Relaterat:** [tjänstelager.md](tjänstelager.md), [tjänstelager_operationer.md](tjänstelager_operationer.md), `projekt/01_ärendehantering/PROJEKTPLAN.md`

---

## 1. Syfte

Ett lokalt webbgränssnitt där handläggaren söker fram en försäkrad och gör ändringar som syns i
Lakebase-tabellerna och i händelseloggen. UI:t är tjänstelagrets första klient. Agenterna
(Fas 3b/5) använder senare samma operationer, med samma spår i loggen (B-017).

**Försäkringsteamets område (B-036).** På bolagets gemensamma plattform är handläggar-UI:t försäkringsteamets
område, och operatörscentralen är startsidan ([projekt 10](../projekt/10_operatörscentral/PROJEKTPLAN.md),
OC-8). Här nås bara försäkringsteamets agent, handläggaragenten. Flöden över flera team och andra teams
agenter hör hemma i centralen respektive i teamens egna områden.

## 2. Teknik och gränser

- **FastAPI + Jinja2 + HTMX.** Sidorna renderas på servern. HTMX laddas från unpkg med fast version och
  SRI-hash. Det finns inget Node och inget byggsteg. Sidorna fungerar också utan JavaScript, och då ger
  HTMX bara mjukare navigering.
- **Digital klarhet (B-034).** UI:t är designspråkets pilotyta (`06_design/designsprak.md`). Färger,
  typsnitt, avstånd och hörnradier finns bara i tokenfilen `src/design/digital_clarity.tokens.json`.
  `src/web/static/tokens.css` genereras ur den med `python scripts/web/build_design_tokens.py`, och
  `app.css` använder enbart dessa variabler. Härledda nyanser blandas med `color-mix()`.
  `tests/test_design_web_css.py` fallerar om `tokens.css` inte är aktuell eller om `app.css` får egna
  färgvärden. Stilarken länkas med `?v=` och en innehållshash (`web.handler.static_version`), så att
  webbläsaren inte fortsätter använda en cachad gammal version efter en ändring. DM Sans laddas från Google Fonts utan referer, eftersom adresserna innehåller
  personnummer. Saknas nätet används reserven `system-ui`.
- **Bara tjänstelagret.** Webbkoden anropar `ServiceLayer.execute/approve/reject` och läsoperationerna,
  och rör aldrig modeller eller sessioner. Det gäller även läsningar, eftersom läsningar av
  personuppgifter loggas. Testet `test_webbkoden_ror_varken_modeller_eller_sessioner` vaktar gränsen.
  Behövs en lista eller en sökning byggs den som läsoperation med en rad i `access_register.yaml`.
  Flödena (`/floden`) hör till harness och inte till tjänstelagret. De nås genom adaptern
  `agents.flows.console.FlowConsole`, som följer samma gräns.
- **Bara lokalt; v1-handläggningen kräver ingen inloggning.**
  - Servern binds till `127.0.0.1`, och Host-huvudet måste vara `127.0.0.1` eller `localhost`
    (skydd mot DNS-rebinding).
  - Skrivformulär bär en token per process (skydd mot att en annan webbplats postar hit).
  - Aktören är `Actor.human(HANDLAGGARE_ID)`, med standardvärdet `karl`.
  - Bolagsfrågornas separata [operatörsinloggning](operator_inloggning.md)
    finns som lokal grund från OC-3a val H–I. Den ändrar inte v1-handläggningens
    mandat eller B-036:s befintliga vägar via `/floden` och `/parametrar`.
- **Motivering i varje skrivformulär**, eftersom tjänstelagret kräver den för `write`.
- **Personuppgifter i webbläsaren.**
  - Adresserna innehåller personnummer, så serverns accesslogg är avstängd.
  - HTMX sparar ingen sidhistorik i webbläsarens lagring (`historyCacheSize: 0`).
  - När handläggningen autentiseras eller kundportalen byggs bör adresserna byta personnummer mot interna id:n.

## 3. Starta

```powershell
python scripts/web/start_ui.py --db lakebase      # gemensamt bestånd, http://127.0.0.1:8765
python scripts/web/start_ui.py                    # demodatabas, http://127.0.0.1:8767
python scripts/web/start_ui.py --reset-demo       # skapa demodatabasen på nytt
python scripts/web/start_ui.py --db svc_test --port 8766
```

I Claude-appen finns `handlaggare-ui` (Lakebase), `handlaggare-ui-demo` och
`handlaggare-ui-svc-test` i `.claude/launch.json`.

**Skrivbordsgenväg (Windows).** Kör `python scripts/web/install_desktop_shortcut.py` en gång från
huvudcheckouten. Det uppdaterar den vanliga genvägen *Artificiellalecta – handläggare* till
**Lakebase** och skapar *Artificiellalecta – handläggare (DEMO)* för lokal övningsdata.
Märket används som ikon (`src/design/icon.py`). `--db` installerar bara den valda genvägen;
`--dry-run` visar resultatet utan att skriva. En äldre separat genväg med suffixet *(Lakebase)*
kan finnas kvar; den vanliga genvägen är nu ingången till beståndet.

Genvägarna kör `scripts/web/open_ui.ps1`, som startar servern dolt om den inte redan kör.
Standard är Lakebase på **8765**, separat testbestånd på **8766** och demo på **8767**.
En egen port kan anges med `-Port` (eller `--port` i Pythonkommandona).
Startskriptet kontrollerar `/_instance` innan webbläsaren öppnas. En körande app med fel databas,
en okänd app eller en äldre version utan miljökontroll blockeras med ett tydligt fel.
Den gamla servern måste då stoppas, eller en annan port väljas; skriptet stoppar inga processer.
För att kunna stoppa en server i terminalen kan den i stället startas med `start_ui.py` ovan.

| Variabel / flagga | Standard | Innehåll |
|---|---|---|
| `HANDLAGGARE_ID` | `karl` | Handläggarens id i händelseloggen |
| `HANDLAGGARE_DB` / `--db` | `demo` | `demo`, `svc_test` eller `lakebase` |

| Databas | Var | Tabeller |
|---|---|---|
| `demo` | `data/handlaggare_demo.db` (SQLite, gitignorerad) | Skapas med demobeståndet (`src/utils/demo_data.py`) om filen saknas |
| `svc_test` | Schemat `handlaggare_ui` i `SERVICES_TEST_POSTGRES_URL` | Skapas med demobeståndet om schemat är tomt. Vägrar om adressen är `DATABASE_URL` |
| `lakebase` | Beståndet via `DATABASE_URL` | Skapas aldrig. Schemaändringar görs bara med migrationsskript (T3-mönstret) |

Pythonkommandot utan databasval behåller demoläget; den vanliga genvägen väljer Lakebase
uttryckligen med `--db lakebase`. `DATABASE_URL` i `.env` räcker alltså inte för att ändra
utvecklingskommandots databasval. Sidhuvudet visar **Lakebase – gemensamt bestånd**,
**DEMO – lokal övningsdata** eller **TEST – separat testbestånd**. Mot Lakebase finns även en röd varning.
Ett läsfel i menyn visas som ett anslutningsfel på sidan; appen byter aldrig automatiskt till demo.
`/_instance` visar bara appens identitet och valda databasläge, inga anslutningsuppgifter,
och är ingen kontroll av databasanslutningen.

**Ingen synkning finns mellan miljöerna.** Sökningar och ändringar går via tjänstelagret direkt
mot den valda databasen. Demo är ett eget övningsbestånd, inte en cache av Lakebase.
Att välja Lakebase flyttar inga uppgifter från demo; eventuella manuella demoändringar måste
jämföras och föras över kontrollerat om de ska bevaras.

### Byta datakälla i gränssnittet

Välj **Lakebase – gemensamt bestånd (Postgres)** eller **Demo – lokal övningsdata (SQLite)**
i sidhuvudets **Datakälla** och klicka **Byt miljö**. Bytet går till målmiljöns startsida
och gäller bara den aktuella fliken. Andra flikar, öppna ärenden och deras servrar behåller
sina databasanslutningar. Inga formulär-, person- eller ärendeuppgifter följer med bytet.

Målmiljön kontrolleras via `/_instance` (app, databasläge och stöd för miljöväljaren).
Om porten är ledig startas en separat lokal server från samma checkout och Pythonmiljö;
på Windows körs den dolt. Om porten används av fel eller en äldre app visas ett fel.
En påbörjad start återanvänds vid nytt försök; inga befintliga processer stoppas automatiskt.
Lakebase och demo använder standardportarna **8765** respektive **8767** som mål även om
den nuvarande servern har startats med en egen port. Testmiljön `svc_test` startas inte från väljaren.

Med JavaScript varnas du före byte om ett skrivformulär har osparade ändringar. Avbryter du,
eller misslyckas miljökontrollen, är formuläret kvar med sina värden. Byte blockeras medan
en HTMX-skrivning eller agentkörning pågår. JavaScriptet lagrar inga formulärdata i cookies
eller webbläsarlagring. Utan JavaScript fungerar miljöval som ett vanligt formulär, men
varningen och bevarandet av osparade fält vid ett misslyckat byte saknas.

`POST /miljo` kräver samma formulärtoken som övriga skrivformulär och accepterar bara
Lakebase eller demo. Det utför ingen försäkringsoperation och ändrar inte serverns databasläge.
Webbläsarens referrerpolicy hindrar att den gamla sidans personnummeradress skickas till målmiljön.

Första skarpa skrivningen föregås av backup och operatörens OK
(AGENTS.md §4.5).

**Demobeståndet** innehåller fyra fiktiva personer och två agentförslag i godkännandekön:

| Person | Läge |
|---|---|
| 19850515-1236 | aktiv |
| 19720303-4561 | aktiv, lön över 7,5 IBB |
| 19900101-7897 | fribrev |
| 19590420-2461 | pension pågår |

Därtill en äldre kohort för flaggskeppsdemon (B-035 val K): 31 aktiva, premiebetalande försäkrade födda
1959–1962 (AL-000005–AL-000035) hos de två demoarbetsgivarna. En demofil som skapades före 3c-B saknar kohorten;
ta bort `data/handlaggare_demo.db` så skapas den på nytt med kohorten.

Agentförslagen prövas mot regelpaketet som om det redan gällde, men bara i demodatabasen. Före
2026-11-01 kan en agent annars inte föreslå skrivningar, eftersom regelgolvet ger `HUMAN_ONLY`.

## 4. Sidor

| Adress | Innehåll | Operationer |
|---|---|---|
| `/` och `/sok?q=` | Personnummer (ÅÅÅÅMMDD-NNNN) och försäkringsnummer (AL-…) öppnar översikten; namnsökning öppnar beståndsurvalet | – |
| `/forsakrade` | Bestånd: namnsökning, person-/försäkringsnummer, arbetsgivare, nuvarande försäkringsläge, antal och sidindelning | `list_insured_persons`, `list_employers` |
| `/forsakrade/{pnr}` | Översikt: person, anställning, aktuell lön, försäkringar med läge och kapital | `get_insured_overview` |
| `/forsakringar/{nr}` | Samma översikt, med försäkringen markerad | `get_insured_overview` |
| `/forsakrade/{pnr}/loneunderlag` | Löneunderlag per månad med alla versioner | `get_insured_overview`, `get_salary_reports` |
| `/forsakringar/{nr}/premier` | Premiehistorik med urval på månader och summa betalt | `get_insured_overview`, `get_premium_history` |

Varje sidvisning loggas som läsning av personuppgifter (vem tittade på vem). Läsresultatet loggas inte.

**Bestånd.** Menyvalet **Bestånd** och länken **Visa beståndet** öppnar listan i den datakälla
som sidhuvudet visar. Den läser direkt från vald databas via tjänstelagret; ingen lokal kopia
eller synkning tillkommer. Antalet träffar avser personer, även när någon har flera försäkringar.
Personer utan försäkring finns med och kan väljas med **Utan försäkring**.

Sökord matchar delar av namn, personnummer eller försäkringsnummer. Alla namndelar ska matcha,
oavsett ordning och stora/små bokstäver (även ÅÄÖ). Arbetsgivarfiltret avser personens nuvarande
arbetsgivare. Lägesfiltret matchar minst en försäkring med en öppen lägesperiod (`valid_to IS NULL`),
inte historiska perioder. Alla personens försäkringar visas i raden. Personens anställningsstatus
visas separat. Sidorna har 25, 50 eller 100 personer; urvalet följer med sidlänkarna och ett nytt
urval börjar på första sidan. Länkarna öppnar befintliga person- och försäkringsöversikter.

`list_insured_persons` är `HUMAN_ONLY` och PII-klassad. Varje sökning eller sidbyte loggas med
handläggare och urval, utan resultatlistan. Databasfel visas som fel och ger inget tomt reservbestånd.

**Skrivformulär (S2).** Formulären visar operationens beskrivning, produktregler med status och vad
agenter får göra med operationen enligt registret och regelgolvet. Varje formulär kräver en motivering.
Efter en lyckad ändring visas operationens resultat.

| Formulär (GET) → skickas till (POST) | Operation | Nås från |
|---|---|---|
| `/forsakrade/{pnr}/loneunderlag/ny` → `/forsakrade/{pnr}/loneunderlag` | `register_salary_report`: ny rapport eller rättelse (`?typ=rattelse&manad=&version=`) | Fliken Löneunderlag |
| `/forsakringar/{nr}/fribrev` → samma adress | `set_policy_paid_up`: avanmälan och fribrev | Översikten, vid premiebetalande försäkring |
| `/forsakringar/{nr}/premier/{id}/rattelse` → samma adress | `correct_premium_transaction`: länkad rättelserad | Premiehistoriken, per premierad |
| `/berakna/premie` (POST, HTMX) | `calculate_premium_preview`: förhandsberäkning i formulären, sparar ingenting | Löneunderlag och premierättelse |

Rättas lönen för en månad som har premie, länkar resultatsidan direkt till premierättelsen med den nya lönen.

**Godkännandekön och händelseloggen (S3).**

| Adress | Innehåll | Operationer |
|---|---|---|
| `/godkannanden?status=vantar\|godkanda\|avslagna\|alla` | Agentförslag med operation, indata, motivering, förslagsställare och körning | `list_approval_requests`, `count_approval_requests` |
| `/godkannanden/{id}/godkann` (POST) | Godkänn med valfri kommentar. Operationen körs på nytt mot aktuellt läge, och agenten blir förslagsställare i loggen | `ServiceLayer.approve` |
| `/godkannanden/{id}/avsla` (POST) | Avslå med obligatoriskt skäl, som sparas i loggen | `ServiceLayer.reject` |
| `/handelselogg` | Hela loggen, senaste först, med urval på operation och utfall. Läsningar visas på begäran | `get_operation_events` |
| `/forsakrade/{pnr}/handelser` | Händelser som rör den försäkrade | `get_operation_events` |

**Produktparametrar (Fas 3c, 3c-P2, B-035).**

| Adress | Innehåll | Operationer |
|---|---|---|
| `/parametrar` | Gällande värden i dag som nyckeltal, alla versioner med giltighet, tillstånd, regel, källa och beslut, och formuläret för en ny version | `get_product_parameters` |
| `/parametrar/ny` (POST) | Schemalägg en ny version från en framtida månad, med regelns nya version, källa, beslut och motivering | `schedule_product_parameter_change` |
| `/parametrar/aterkalla` (POST) | Dra tillbaka en kommande version med motivering; föregående version gäller då vidare | `withdraw_product_parameter_change` |

Handläggaren utför ändringarna direkt. En agent kan bara föreslå en ny version, och förslaget avgörs i
`/godkannanden`. Procentsatser skrivs som andel (0,045 = 4,5 %) och visas i procent.

**Flöden (Fas 3c, 3c-3, B-035; avgränsat enligt B-037).** Flödet `rule_change_parameter` från regeländring till verifierad
produktparameter ([flaggskeppsflöde.md](flaggskeppsflöde.md) §6–7). Sidorna och adaptern finns som
återanvändbar kod. De ansluts inte automatiskt i någon datakälla, och menyvalet
visas bara med en uttryckligen ansluten `FlowConsole`. Direktåtkomst utan
anslutning visar att förmågan ännu inte är tillgänglig. Tabellen nedan beskriver
sidorna när en konsol är ansluten, vilket regressionstesterna gör uttryckligen.

> **Tillfälligt hem.** Flöden och produktparametrar är beslut på bolagsnivå, inte handläggning av enskilda
> försäkrade, och flödet kör compliance och aktuarie, som inte hör till det här området. De ligger här för att
> handläggar-UI:t var det enda gränssnittet när 3c-3 byggdes. De flyttar till operatörscentralen i OC-7
> ([projekt 10](../projekt/10_operatörscentral/PROJEKTPLAN.md),
> [operatörscentral.md](operatörscentral.md) §2). Bygg därför inte ut `/floden` och `/parametrar` här, utöver
> rättningar. Det som ska kunna återanvändas läggs i `src/agents/flows/` och i adaptern `FlowConsole`.

| Adress | Innehåll | Motorn |
|---|---|---|
| `/floden` | Flödena med status och aktuellt steg, och *Starta flöde* med en källa ur regelverksgatewayen | `list`, `start` |
| `/floden/{id}` | Stegen med status, resultat, kostnad, körning och tider, grindbesluten med bunden hash, och åtgärden flödet väntar på | `get` |
| `/floden/{id}/kor` (POST) | *Kör nästa steg*: agent- eller systemsteget, synkront och ett åt gången (val F). När flödet väntar på kön prövas om förslaget är avgjort | `run_next` |
| `/floden/{id}/grind` (POST) | *Godkänn* (anteckning valfri) eller *Avslå* (skäl krävs). Grind 2 bär regelns version, giltighet och valfritt B-nummer | `decide_gate` |
| `/floden/{id}/klart` (POST) | *Markera klart* med commit-referensen för regeltexten | `complete_manual` |
| `/floden/{id}/avstam` och `/avbryt` (POST) | Avstämning av ett avbrutet steg (kör om eller avsluta) och avbrott av flödet, med anteckning | `resolve_reconciliation`, `cancel` |
| `/floden/{id}/steg/{steg}/utkast/{namn}` | Ett utkast som steget skrivit, som Markdown-text | – |
| `/floden/{id}/steg/{steg}/journal` | Agentstegets körjournal ur `logs/agent_runs/` | – |

- **Adapter i stället för modeller.** Webben anropar `agents.flows.console.FlowConsole`, som håller motorn,
  definitionerna och agenternas körmiljö. Webbkoden importerar varken `models` eller `services.operations`.
  Förslaget i kön läses med `list_approval_requests`.
- **Låsning.** Varje formulär bär flödets version, och grindformulären bär också hashen av underlaget som visades
  (`seen_hash`). Har flödet eller underlaget ändrats sedan sidan visades blir det en konflikt (409), och ingenting
  ändras.
- **Omstart.** När UI:t startar blir steg som stod som pågående `reconciliation_required` (`mark_interrupted`).
  Handläggaren avgör dem på sidan efter att ha kontrollerat körjournalen och kön.
- **Grinden ersätter inte kön.** Aktiveringen lägger ett förslag från `compliance_agent` i `/godkannanden`, och
  flödet går vidare först när förslaget är avgjort där.
- **Ingen skriptad agentväg.** Den tidigare demomodellen och den automatiska kopplingen
  till `/floden` är borttagna på operatörens uppdrag (B-037). Databasvalet ändrar inte
  regelkatalogens giltighetsdatum för flödets skull. `FlowConsole.build` kräver en
  uttrycklig AI-klient och använder de tjänstelager den får. Teamroller och flödestabeller
  finns i Lakebase sedan 2026-10-26 och flödet är röktestat med riktiga modeller (3c-V);
  någon verksamhetskoppling i UI:t görs inte här (OC-7). FakeProvider används bara som
  uttryckligt testunderlag i regressionstesterna för flödet.
- **Verifiering.** Definition v2 jämför lagrade parameterversioner före och efter
  giltighetsdagen med det godkända beslutet. Den skapar ingen syntetisk person eller
  demonstrationspremie och säger inget om övriga verksamhetsmotorers färdigställande.
  Äldre flödesdefinitioner får inte köras vidare som v2; historiken behålls för avstämning.

Antalet väntande förslag visas i menyn. Det hämtas med `count_approval_requests`, som inte läser
personuppgifter och därför inte loggas. Ett godkännande som krockar med dagens läge, till exempel för
att handläggaren redan har registrerat underlaget, rullas tillbaka i sin helhet. Förslaget ligger då kvar
som väntande och kan avslås. Tider visas i datorns lokala tid, medan tjänstelagret sparar UTC.

**Kön, loggen och agenterna.** De tre läsoperationerna är `HUMAN_ONLY` i registret
(se [tjänstelager.md](tjänstelager.md) §9).

**Anslutning, stamdata och arbetsgivare (S5, B-032).** Operationerna stämdes av med operatören i
`projekt/01_ärendehantering/OPERATIONER_BESLUTSFORSLAG.md`. Stödda och blockerade fall står i
[tjänstelager.md](tjänstelager.md) §9.2.

| Adress | Innehåll | Operation |
|---|---|---|
| `/forsakrade/ny` (`?arbetsgivare=`) | Anslut ny anställd: person, försäkring, förmån och premiebetalande | `enroll_insured_person`, `list_employers` |
| `/forsakrade/{pnr}/lon` | Aktuell månadslön och tjänstgöringsgrad (stamdata). Formuläret skiljer den tydligt från löneunderlaget | `update_current_salary` |
| `/forsakrade/{pnr}/kontakt` | E-post och telefon, där ett tomt fält tar bort uppgiften. Ange varifrån ändringen kommer och hur personen verifierades | `update_contact_details` |
| `/arbetsgivare` | Arbetsgivare med antal aktiva försäkrade och länk till anslutning | `list_employers` |
| `/arbetsgivare/ny` | Ny arbetsgivare (ITP) | `register_employer` |

Översikten har knappar för löneunderlag, aktuell lön och kontaktuppgifter. Startsidan har en knapp för att ansluta en ny försäkrad.

**Ärenden och handläggaragenten (Fas 5 F5-4, B-033).** Ärendet är agentens arbetsenhet och mandat. Operationerna står i [tjänstelager.md](tjänstelager.md) §9.3 och agentkörningen i `src/agents/case_runs.py`.

| Adress | Innehåll | Operation |
|---|---|---|
| `/arenden?status=aktiva\|stangda\|alla` | Handläggarens lista med typ, försäkrad, månad, mottagning, status och handläggare | `list_cases` |
| `/arenden/ny` (`?pnr=`) → `/arenden` | Registrera ett ärende om inrapporterat löneunderlag; med `?pnr=` förifylls personen och arbetsgivaren | `create_case` |
| `/arenden/{nummer}` (`?lasningar=1`) | Ärendet: inrapporterade uppgifter, agentens senaste körning, förslag i ärendet, statusbyte, stängning och historik (ändringar och förslag, läsningar på begäran) | `get_case`, `list_approval_requests`, `get_operation_events` |
| `/arenden/{nummer}/agent` (POST) | *Starta agent*: handläggaragenten körs i ärendet. Resultatet visar status, sammanfattning, förbrukning, underlag, förslag och journalens sökväg | `run_case` |
| `/arenden/{nummer}/status` (POST) | Byt status bland de öppna, och vid behov handläggare | `update_case_status` |
| `/arenden/{nummer}/stang` (POST) | Stäng med utfall och motivering | `close_case` |

- **Agenten körs synkront**, en körning åt gången i processen (B-033 val D). Knappen frågar först, eftersom körningen gör modellanrop som kostar. Modellklienten skapas vid första körningen – UI:t startar utan API-nycklar.
- **Planerat: självständiga körningar (F5-7).** Handläggaragenten ska kunna ta ärenden själv, till exempel när ett ärende om löneunderlag registreras, och arbeta utan att handläggaren klickar. Det kräver en utlösare, en bakgrundsarbetare och regler för vilka ärendetyper som går automatiskt, med budget och möjlighet att stänga av. Mandat, budget och godkännande i kön gäller som vid *Starta agent*. Agenten föreslår, handläggaren beslutar. Knappen finns kvar för att starta agenten i ett enskilt ärende.
- **Databasrollen per läge** (B-033 val H): i `demo` och `svc_test` simuleras agentens roll och sidan visar *simulerad*; mot `lakebase` används den riktiga rollen `agent_forsakring`, vars läsrätt på `cases` verkställdes i Lakebase 2026-10-24 (F5-5).
- **Efter körningen** skriver harness ärendets status: *Väntar på godkännande* om ett förslag lagts, annars *Pågår*. Förslaget avgörs i `/godkannanden`, där det länkar till ärendet.
- **Egen registrering i ärendet.** *Registrera löneunderlaget själv* öppnar löneunderlagsformuläret med ärendets uppgifter och ärendenumret medskickat (`?arende=`). Registreringen hamnar då i ärendets historik, och ärendet kan stängas som *Godkänt*.
- **Demo- och testdatabasen** får nya tabeller, som `cases`, när UI:t startar mot en befintlig fil eller ett befintligt schema. Befintliga tabeller och rader rörs inte, och Lakebase ändras aldrig härifrån.
- Godkännandekön kallar sina poster *förslag*, så att de inte blandas ihop med ärenden.

## 5. Felvisning

Tjänstelagrets fel visas i en ruta med rubrik, skäl och de produktregler som nämns, med regelns
rubrik och status ur `01_domän/produktregler/`:

| Fel | HTTP | Rubrik |
|---|---|---|
| `BlockedError` | 422 | Stoppat – kräver manuell prövning |
| `ConflictError` | 409 | Krock med aktuellt läge |
| `InvalidInputError` / `MissingReasonError` | 422 | Ogiltiga uppgifter, per fält |
| `NotFoundError` | 404 | Hittades inte |

Efter ett fel i en ändring står det uttryckligen *Ingenting har ändrats.* Tjänstelagret rullar
tillbaka hela anropet (tjänstelager.md §6.1).
