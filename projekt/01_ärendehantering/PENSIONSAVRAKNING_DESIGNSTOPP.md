# Designstopp – paket B: pensions- och månadsavräkning

> **ID:** P1-PENSION-001 | **Version:** 0.1 | **Datum:** 2026-11-14
> **Status:** PB1–PB13 godkända enligt rekommendationerna av Karl i chatten
> 2026-11-14: ”Godkänn alla”. Byggstart enligt byggordningen i §12 är därmed godkänd,
> med separat OK före varje Lakebase-ingrepp. De öppna frågorna i §13 avgörs vid
> respektive byggsteg. Loggat som **B-047** samma dag efter Karls OK: ”Ja, logga den”.
> **Uppdrag:** [ATT_GORA, paket B](../../ATT_GORA.md#-månadssimulering--byggluckor-och-samordning);
> gap V-04–06 och V-11 i [processöversikten](../../01_domän/processer_översikt.md#3-gap-i-verksamhetsförmågorna).
> Beställt 2026-11-14 efter att paket A:s första operativa period (2026-10) körts i Lakebase.
> **Utgångspunkt:** `main` vid `fd3c336`, arbetsbranch `claude/nervous-antonelli-fcac7f`.
> **Mall:** [P1-PREMIE-001](PREMIEFLODE_DESIGNSTOPP.md) (paket A, B-046).

## 1. Godkända val

Bygg bolagets ordinarie månadsavräkning för ålderspension, ett led i taget:

mottagen nettopremie (paket A) → operativ kapital- och garantijournal per uttagsdel →
månadsstängning i PR-020:s ordning → månadsrätt och pensionsskuld → preliminär skatt →
bankuppdrag och bankkvitto → dödsfall, arvsvinst och slutavräkning.

Allt räknas i befintliga motorer: `close_month`, `roll_origins`, `allocate_cents`,
`annuity_factor`, `guarantee_part`, `reconstruct_origins`, premiemotorn och
bankdagskalendern. Paket B bygger en operativ journal och de verksamhetsoperationer
som saknas. Det bygger ingen andra FTA-motor, avkastningsmodell eller agentloop.

| Val | Godkänt 2026-11-14 |
|---|---|
| **PB1: omfattning i första versionen** | Start från 66 år: ordinarie livsvarig start enligt PR-025, kundvald senare start (uppskov), tidsbegränsad plan med minst 60 rättigheter, paus och återstart, förlängning, deluttag i högst tre delar, dödsfall, arvsvinst och slutavräkning. **Tidigt uttag före 66** (PR-002 och PR-024:s pensioneringsprövning) blockeras med ärende och blir ett senare steg |
| **PB2: uttagsdel och tre förlopp** | Ny uttagsdel under förmånen. Varje garantidel, kapitalpost och månadsrätt tillhör exakt en del. `policy_states` blir enbart premieförloppet; pensionsförloppet ligger per uttagsdel och betalningsförloppet per månadsrätt (§4) |
| **PB3: begäran, plan och beslut** | Kundens begäran registreras med mottagningsdag och kanal och prövas mot fristen. Handläggaren beslutar en versionerad plan hashbundet mot en förhandsberäkning. Saknas val vid 66 skapar månadsstängningen standardplanen, om livs- och avtalsstatus är verifierade; annars blir det ett ärende |
| **PB4: en operativ kapital- och garantijournal** | En journal per post för bolagets faktiska C och G, med S-04 per 2026-10-31 som märkt ingående läge och paket A:s allokeringar som enda källa för nya premier. P6-MANAD-001:s tabeller förblir scenarioverktyg och läser den operativa journalen i stället för att bygga en egen. A6 läser den som `source='ledger'` |
| **PB5: månadsstängning** | En körning per månad för hela kollektivet, i PR-020:s åtta steg, i betrodd kod. Handläggaren granskar en förhandsberäkning och stänger med dess kontrollsumma. Saknad avkastning, avgift eller skattesats blockerar stängningen. Rättelse av stängd månad blir en ny länkad version med motposter |
| **PB6: månadsrätt, belopp och skuld** | Ett bruttoanspråk per uttagsdel och rättighetsmånad, skuldfört och debiterat C en gång i steg 5. Beloppet beslutas vid start, återstart, planändring och varje januari som max(G, B) med PR-009:s golv. Nytt bankförsök ändrar inte anspråket |
| **PB7: preliminär skatt** | Skattestatus per person och år registreras av handläggaren: sidoinkomst 30 %, individuellt beslut eller huvudinkomst med tabell. Tabellavdrag kräver en versionsbunden tabellparameter för året och utbetalarens ort; saknas den blockeras betalningen med skulden kvar. Småbeloppsgränserna ingår. SINK bara genom registrerat beslut. Saknad skattestatus blir ett ärende, aldrig ett antagande |
| **PB8: utbetalning och bankkvitto** | Bankuppdrag skapas första bankdagen efter pensionsmånaden, efter stängd månad, per mottagare med detalj per del. Handläggaren godkänner bankfilen hashbundet. Bankens kvitton (utförd, avvisad, återkommen, okänt utfall) importeras idempotent. Motpartssimulatorn i `src/simulation/` byggs ut med utbetalningssidan |
| **PB9: dödsfall och arvsvinst** | Dödsfallsbesked registreras som misstänkt eller verifierat. Misstänkt stoppar nya bankuppdrag; verifierat avräknas i nästa stängning (PR-010). Återstående C går till en poolpost och fördelas samma månad efter SIM-R (PR-011). Dödsbo får äldre obetalda anspråk först efter behörighetsprövning hos handläggaren |
| **PB10: slutavräkning och `terminate_policy`** | Slutavräkning görs i stängningen för den tidsbegränsade delens sista rätt (PR-027). En del avslutas bara genom slutavräkning eller dödsfall. `terminate_policy` byggs inte som egen operation; försäkringens avslut härleds när alla delar är avslutade och skulderna reglerade |
| **PB11: bolagskapital och garantifinansiering** | Journalen får ett bolagskonto. Karl registrerar en dokumenterad startinsättning innan första stängning med utbetalning (PR-028). Bolagsstöd förs från bolagskontot med motpost. Räcker kontot inte blir anspråket ej finansierat, körningen ekonomiskt blockerad och ärendet eskaleras |
| **PB12: befogenheter och kanaler** | Alla nya skrivande operationer är `HUMAN_ONLY`. Agenter får läsa aggregat. Operationerna tar kanal och verifierad aktör, så att kundportalen senare använder samma operationer med en ny aktörstyp |
| **PB13: start, testbestånd, byggordning och Lakebase** | Byggordningen i §12. Verifiering i demo och `svc_test` med demobeståndets äldre kohort. Första operativa stängning i Lakebase blir november 2026 för sparandet, när steg 3 är byggt och en antagen AVK för månaden finns. Separat OK före varje Lakebase-ingrepp (§12) |

Valen ändrar inga produktregler. PR-ITP1-002–011 och 020–028 är godkända sedan
2026-11-01 (B-031). Där en regel lämnar ett tillämpningsval öppet anges det i §13.
Valen ger inga agenter nya befogenheter (§8).

## 2. Varför paket B nu och vad som redan finns

**Verksamhetsnytta:** Bolaget kan i dag ta emot premie och tilldela garanti i en
scenariojournal, men inte förvalta ett faktiskt kapital eller betala ut en pension.
Utan paket B:

- kan en försäkring bara ha ett läge, så fribrev under pågående pension och flera
  uttagsdelar går inte att uttrycka (B-030, `set_policy_paid_up` blockerar);
- räknas kapitalet om från premiehistoriken vid varje värdering (S-04, `reconstructed_s04`),
  och delbetalda premier från paket A saknas där eftersom de inte är `paid`;
- finns ingen motor för månadsrätt, skuld, skatt, bankutbetalning, dödsfall eller
  slutavräkning, så `terminate_policy` är uppskjuten (B-030 p. 4);
- markerar värderingskontraktet A1 pågående uttag, betalningsskuld, dödsfall och
  slutavräkning som *ej beräknat* tills paket B finns.

**Nuläge i Lakebase**, enligt dokumenterade skrivskyddade kontroller (inga nya
körningar i detta designstopp):

| Område | Läge |
|---|---|
| Bestånd | 501 försäkrade, 499 försäkringar; 471 premiebetalande och 28 fribrev. Inga påbörjade eller pausade uttag (0 ej beräknade i S-04 per 2026-10-31). Den äldre kohorten (B-035 val K) är inte införd |
| Kapital och garanti per 2026-10-31 | C 42 087 223,57 kr och G 119 195,6502916268 kr/mån, rekonstruerat S-04 med utdragshash `023946…3fefa` (P6-MANAD-001 §3.3) |
| Mottaget i november via paket A | 87 885,56 kr inbetalt: 51 623,90 kr fördelat på fakturarader (TeknikNorden 36 261,66 kr fullt, SvenskIndustries 15 362,24 kr delvis) och 36 261,66 kr på avstämningskontot (CASE-000011) |
| Månadsjournal | `premium_month_journals`, `premium_receipts`, `premium_month_closes` är tomma; den syntetiska novembermånaden finns bara lokalt |
| Grunder | SIM-HIST, SIM-G, SIM-B, SIM-R, SIM-V och FI-SIM finns i `valuation_bases`. AVK-SIM-2026-01 räcker till och med oktober 2026 |
| Parametrar | Kapitalavgift och skattebelastning för 2026 i `product_parameters`; 2027 års `customer_tax_rate` läggs in i januari 2027 |

Inga pensionsfall finns alltså i Lakebase de närmaste åren. Pensionsdelen verifieras
därför i demo och `svc_test` (PB13), medan journalen och stängningen för sparandet
ger nytta i Lakebase direkt.

**Återanvänds:**

| Del | Användning i paket B |
|---|---|
| `close_month` (`capital_rollforward.py`) | Avkastning, avgift och skattebelastning per försäkring och månad med kollektivets öresfördelning (PR-020 steg 2–4) |
| `roll_origins` (`premium_origin_ledger.py`) | Fördelar månadens belopp på kapitalspår per ursprung. Utökas med pensionsdebit, bolagsstöd, pool och delning, utan att ändra befintliga stegs avrundning |
| `reconstruct_origins` och S-04 (`valuation_extract.py`) | Ingående spår och garantidelar per 2026-10-31, bevarade exakt i ören |
| `annuity_factor`, `guarantee_part`, `reference_start` (`actuarial_annuity.py`) | A_g, A_b, garantidel, värdebevarande omräkning och referensplan |
| `allocate_cents` | Största bråkrest för delning, poolfördelning och debiteringar |
| `premium_month_inputs` och `export_premium_month` | `ReceiptInput`-kontraktet och paket A:s allokeringar som premiekälla |
| A4 `valuation_bases` | SIM-B, SIM-G, SIM-R och AVK som versionerade grunder; ingen ny grundkatalog |
| A6 `fta_valuation` / `valuation_extract` | Värdering ur journalen när `source='ledger'`; tar bort *ej beräknat* för uttag och skuld |
| `product_parameters` och `services.parameters` | Avgift, skattebelastning och nya skatteparametrar som versionerad data |
| Bankdagskalendern, OCR-/kontrollsummemönstret och motpartssimulatorn | Bankdag för utbetalning, idempotent filintag och simulerad bank |
| Tjänstelagret, `cases`, godkännandekön och `operation_events` | Alla nya operationer, ärenden och spår (B-028, B-033) |
| Flödesmotorn | Hashbunden granskning av månadsstängning och bankfil, med samma mönster som paket A:s filgodkännande |

## 3. Omfattning

**Ingår:**
- uttagsdelar, planer och de tre förloppen för start från 66 år;
- operativ kapital- och garantijournal med övergång från S-04;
- månadsstängning med avkastning, avgift, skattebelastning, premier, månadsrätt,
  dödsfall, arvsvinst och slutavräkning;
- pensionsbelopp, januariomräkning och garantiomräkning vid planändring;
- preliminär skatt, bankuppdrag, bankkvitton, retur och nytt försök;
- bolagskonto och bolagsstöd enligt PR-028;
- utbyggd motpartssimulator för kundbegäran, dödsfallsbesked och bankkvitton.

**Ingår inte**, och var det hör hemma:

| Utanför | Var |
|---|---|
| Tidigt uttag före 66 med pensioneringsintyg (PR-002, PR-024 före 66) | Senare steg i paket B |
| Återtag av mottagen premie och återbetalning (PR-019 p. 3–4), inklusive CASE-000011 | Senare steg; journalens kapitalspår gör det möjligt, men rättslig prövning och extern återbetalning behöver egen design |
| Ny försäkring för premie när alla delar startats (PR-025) | Senare steg; tills dess blockeras premien med ärende |
| Dröjsmålsränta vid bolagets dröjsmål (PR-026) | Senare steg; bolagskostnad, aldrig C-debit |
| Utbetalning till dödsbo | Handläggarärende; ingen automatisk betalning i första versionen |
| Kontrolluppgift (KU18/19), AGI och skatteinbetalning till staten | Projekt 6 (V-10/V-12); paket B lämnar underlaget |
| Bokföring, huvudbok, bolagets faktiska avkastningsskatt | Projekt 6 |
| Realiserad avkastning, likviditet och portfölj | Projekt 5, pausat; se kassaflödesgränsen i §10 |
| Prognos och besked till kund (PR-029), kundbrev (V-09) | Kommunikationsflödet; paket B ger beräkningsunderlaget |
| Kundportalen och kundautentisering | Projekt 3; använder paket B:s operationer (PB12) |
| Simuleringsklocka och full månadssimulator (S-01–06) | Paket C |
| `monthly_actuarial_check` med buffertberäkning E_min | Projekt 6 (A8); paket B lämnar underlaget |

## 4. Uttagsdel och tre förlopp (PB2)

UTTAG_GEMENSAMT kräver tre oberoende förlopp. I dag finns ett läge per försäkring.

| Förlopp | Bärare | Lägen |
|---|---|---|
| Premie och intjänande | `policy_states`, oförändrad tabell med enbart premielägen | `premium_paying`, `paid_up`; sena poster hanteras separat |
| Uttagsdelens pension | Ny tidslinje per uttagsdel | `not_started`, `in_payout`, `paused`, `ended` (med orsak `final_settlement` eller `death`). En framtida plan är en planversion, inte ett läge |
| Betalningsanspråk | Status på varje månadsrätt | `arisen`, `funded`/`unfunded`, `bank_prepared`, `sent`/`unknown`, `paid`, `rejected`/`returned` |

**Övergången:** varje befintlig förmån får en uttagsdel nummer 1 i läget `not_started`,
med förmånens alla garantidelar och kapitalspår. Ingen ekonomisk effekt uppstår.
Lägena `in_payout` och `payout_paused` i `policy_states` flyttas till uttagsdelen.
I Lakebase finns inga sådana rader. I demo har David Dahl `in_payout` sedan 2024-05
utan garantidelar eller anspråk; han får ett rekonstruktionsärende, inte en konstruerad
historik. Läget `terminated` används inte för nya avslut (PB10).

**Följder för befintliga operationer:**
- `set_policy_paid_up` får sätta fribrev även när en uttagsdel är pågående eller
  pausad, eftersom premieförloppet nu är skilt från pensionen.
- Läsare som tolkar `in_payout` på försäkringen (översikt, listning, produktrapport,
  S-04, webbens presentation) läser i stället uttagsdelens läge. Det görs i byggordningens steg 1 (§12).
- `create_premium_from_salary_report` väljer premiens mottagare bland ej startade
  delar. Finns flera, används vikterna i PR-015; finns ingen, blockeras premien med ärende.

**Byggt i steg 1 (2026-11-14, infört i Lakebase samma dag efter backup `backups/20261114T150341Z` och Karls OK):**
tabellerna `payout_parts` och `payout_part_states` ([databasschema §7b](../../02_system/databasschema.md#7b-tabeller-payout_parts-och-payout_part_states--uttagsdelar-och-pensionsförloppet)),
övergången, de anpassade läsarna och `set_policy_paid_up` ([tjänstelager §9.14](../../02_system/tjänstelager.md#914-uttagsdelar-och-tre-förlopp-paket-b-steg-1-b-047--vad-som-stöds-och-vad-som-blockeras));
fall 38 är verifierat lokalt och migrationen mot isolerad Postgres. Mergat till main 2026-11-14 (`86c3d6e`). Avvikelser, godkända av Karl i chatten samma dag (”Approve, merge it”):
- *Flera ej startade delar* blockerar premien i stället för att fördela med vikterna i PR-015,
  eftersom ingen fördelningsinstruktion finns ännu. Ingen del blockerar premien med skäl, men
  utan nytt ärende – ett ärende för det fallet hör till steg 4, när start finns.
- *Rekonstruktionsärendet* har den nya ärendetypen `payout_reconstruction`, skapad av
  systemaktören; villkoret `ck_cases_type` vidgas av migrationen.
- *Agentrollernas läsningar:* en roll utan rätt på de nya tabellerna redovisar pensionsförloppet
  som ej läst i översikten och produktrapportens bestånd. `agent_forsakring` och `agent_aktuarie`
  får SELECT enligt **B-048**, som också loggar ärendetypen `payout_reconstruction`.
- *Övergången stoppar* vid `terminated`, uttagslägen som inte ligger sist eller har glapp och
  fler än en ålderspensionsförmån per försäkring, i stället för att gissa.
- *David Dahls premieförlopp* blir fribrev från 2024-05-01, dagen efter registrerat
  anställningsslut – samma läge som `set_policy_paid_up` hade gett.

**Delning (PR-024):** högst tre delar per ursprunglig försäkring. Ny del och kvarvarande
del minst 10 % av kapitalet vid delningen, prövat som andel även när C = 0 men G finns.
C delas i ören med största bråkrest och varje G_j proportionellt i hög precision.
Delningen ger inget nytt kollektivmedlemsdatum och ingen extra arvsvinstvikt.

## 5. Begäran, plan och belopp (PB3, PB6)

### 5.1 Begäran och frist

`register_payout_request` sparar kundens begäran med mottagningsdag, kanal, aktör och
innehåll: uttagsdel, startmånad, form, antal rättigheter, delningsandel, paus och
återstart. Fristen är sista kalenderdagen i månaden före ändringsmånaden, i
Europe/Stockholm (UTTAG_GEMENSAMT). Utfallet sparas:

- **I tid och fullständig:** ärende `payout_request` till handläggaren med förhandsberäkning.
- **Sen:** förslag på nästa möjliga månad. Planen ändras först efter kundens bekräftelse.
- **Ofullständig:** komplettering med konkreta uppgifter. Ingen tyst plan.
- **Avliden, okänd identitet eller saknad behörighet:** stopp och ärende.

Bolagets dröjsmål flyttar aldrig en giltig begärans datum. Mottagningen registreras
även när handläggningen sker senare.

### 5.2 Plan och beslut

`preview_payout_plan` räknar G, B och M för föreslagen plan i betrodd kod och ger en
granskningssumma. `decide_payout_plan` binder summan och sparar en ny planversion med
originalstart, form, N, förbrukade och kvarvarande rättigheter, pausintervall,
återstart, härledd slutmånad, regel- och villkorsversion, grunder med hash, faktorer,
belopp, motivering och beslutsfattare. En ny version ersätter den förra uttryckligen.
En godkänd framtida plan ändrar inte dagens läge före giltighetsdagen.

**Standardstart (PR-025):** för en ej startad del vars ägare fyller 66 i månaden och
saknar val, skapar månadsstängningen standardplanen livsvarig från 66-årsmånaden, om
avtalet och levandestatus är verifierade. Annars blir det ett ärende och rättigheterna
räknas fram när underlaget styrkts. Startmånaden flyttas aldrig tyst till handläggningsdagen.

### 5.3 Belopp och garantiomräkning (PR-008, PR-009)

Vid start, återstart, planändring och varje januari, på värderingen vid föregående
månadsslut:

```text
B = C / A_b(t, D_kvar)                          SIM-B, 0 % nettoränta
M = max(round_half_up(max(G, B)), ceil_öre(ΣG_j), tidigare bindande golv)
```

Livsvarig del håller minst senaste beslutade brutto under de första 60 rättigheterna
för oförändrad plan. Paus återställer inte golvet; en verklig förlängning kan ge ny nivå.
Vid planändring räknas varje garantidel om värdebevarande på sin historiska grund:
`V_j = G_j × A_gj(gammal plan)` och `G_j_ny = V_j / A_gj(ny plan)`. Vid delning delas G_j
proportionellt utan ny värdering. Beloppet ligger fast mellan omräkningarna.

### 5.4 Byggt i steg 4

**Byggt 2026-11-21 på branchen `claude/paket-b-steg-4-pension-cd2841` och mergat till main 2026-11-22 efter Karls OK (B-052); inte infört i Lakebase.**

- **Var det finns:**
  - kalender, frist, belopp, golv och omräkning i `src/skills/calculation/payout_plan.py`;
  - begäran, förhandsberäkning, beslut, delning och ägarkontrollen i `src/services/payout_plans.py`;
  - operationerna `register_payout_request`, `preview_payout_plan`, `decide_payout_plan`, `split_payout_part` och `get_payout_part`, alla `HUMAN_ONLY` ([tjänstelager §9.17](../../02_system/tjänstelager.md));
  - genomförandet i stängningens steg 1 i `src/services/month_close.py`;
  - tabellerna `payout_requests`, `payout_plans` och `payout_splits`, `ledger_guarantee_parts.plan_id` och migrationen `migrate_payout_plans.py` ([databasschema §7d och §12](../../02_system/databasschema.md));
  - körskripten för Lakebase i `scripts/simulation/paket_b_steg4/`.
- **Verifierat:**
  - lokalt: fall 1–12 (`tests/test_payout_plan_calculation.py` och `tests/test_payout_plans.py`), steg 3:s stängning oförändrad utan steg 4:s tabeller;
  - mot isolerad Postgres (`svc_test`): migrationen från läget efter steg 3 med november stängd, och fall 2 och 7 i novemberstängningen med paket A:s testbestånd (`tests/test_migration_payout_plans.py`).

Karls val V1–V11, godkända i chatten 2026-11-21 (”Godkänn alla”). Loggade som **B-051** samma dag efter Karls OK (”Yes, log B-051”):

- **V1 Datamodell:**
  - tre tabeller: `payout_requests`, `payout_plans` med versionskedja och `payout_splits`;
  - `ledger_guarantee_parts` får `plan_kind = 'plan'` och `plan_id`;
  - `ck_cases_type` vidgas med `payout_request` och `payout_review`.
- **V2 Bokning:**
  - ett beslut skriver bara beslutet;
  - ändringsmånadens stängning genomför det i steg 1, inom sin kontrollsumma, på värderingen vid föregående månadsslut;
  - beslutet kräver att föregående månadsslut är täckt och att ändringsmånaden är öppen.
- **V3 Startade delar:** beslut om start, paus och förlängning tillåts. En månad där en del har rätt enligt plan blockerar tills månadsrätten finns i steg 5.
- **V4 Standardstart:**
  - för en verifierad ägare som fyller 66 i månaden visar granskningen standardplanen livsvarig från 66-månaden, med G, B, M, första rätt och betalningsdag, och månaden blockerar enligt V3;
  - overifierat underlag ger ett ärende `payout_review`, och sparandet stängs som i S4;
  - efter migrationen heter kontrollen *standardstart*; före den är kontrollposten densamma som i steg 3.
- **V5 Verifiering:** registerkontroll i betrodd kod. Personen är inte `deceased` och har en giltig födelsedag, försäkringen är ITP1 med arbetsgivarens avtal `ITP`, och inget rekonstruktionsärende är öppet.
- **V6 Passerat 66 utan plan:**
  - ett ärende `payout_review` per person, första gången;
  - planen beslutas efter kundens begäran;
  - inga automatiska retroaktiva rätter, och startmånaden flyttas inte.
- **V7 Omräkning och premier:**
  - en ändrad plan räknar om varje G_j värdebevarande som ny version (`recalculation`, länk till planen; fall 12);
  - en ny premie på en del med beslutad plan får G_j direkt på planen;
  - ledger-utdraget redovisar en försäkring med planbaserad garanti som ej beräknad.
- **V8 Begäran:**
  - varje begäran sparas med utfallet i tid, sen, ofullständig, stoppad eller blockerad;
  - kundens bekräftelse av ett förslag är en ny begäran som pekar på den sena;
  - ett ombud kräver verifierad behörighet;
  - systemets egna fynd får typen `payout_review`.
- **V9 Delning:**
  - bara ej startade delar delas;
  - delningen genomförs i ändringsmånadens stängning;
  - beslutet anger en primär premiemottagare med vikt 1 (PR-ITP1-015), som premieunderlaget använder;
  - viktad fördelning är ett senare steg.
- **V10 Belopp:**
  - M = max(round_half_up(max(G, B)), ceil_öre(ΣG_j), golv);
  - golvet för en livsvarig del under de första 60 rätterna är senast beslutade M;
  - förbrukade rätter härleds ur kalendern;
  - januariomräkningen finns som funktion och tillämpas i steg 5.
- **V11 Main och Lakebase:**
  - ingen merge förrän novembers stängning är bokad och kontrollerad, eftersom kontrollens nya namn ändrar sammanställningen. *Ersatt 2026-11-22 av **B-052**: merge tillåts eftersom stängningen före migrationen är identisk med steg 3;*
  - koden beter sig som steg 3 när tabellerna saknas;
  - *2026-11-22:* före migrationen är novembers stängning nu identisk med steg 3. Kontrollposten har steg 3:s namn och text, och premiernas innehåll saknar steg 4:s fält. En jämförelse på samma databas utan steg 4, med main:s kod och branchens, gav samma granskningssumma, verifikation, poster, garantidelar och ärenden, även med två ägare som fyllt 66;
  - migrationen och körskripten är skrivna men inte körda.

Avvikelser från §5 och §10:
- *Standardplanen sparas inte i steg 4.* Den visas i 66-månadens granskning och blockerar månaden. Den beslutas och bokas i steg 5 tillsammans med månadsrätten. `origin = 'standard_start'` finns i modellen men skrivs inte än.
- *Paus och förlängning* av en startad del kan bara förhandsberäknas som indikativa (fall 5, 6 och 10), eftersom en startad del blockerar varje stängning till steg 5.
- *Delning* av en del med planbaserad garanti blockeras, liksom plan och delning på samma del i samma månad.
- *M vid uppskov* räknas vid beslutet på dagens grunder och räknas om vid den verkliga starten (steg 5).
- *Premie utan mottagande del* täcks redan av ärendet `salary_file_deviation` ur paket A. Ingen ny `payout_review` skapas för det fallet.
- *En ny ärendetyp*, `payout_review`, för systemets egna fynd vid 66 (V8), utöver §10:s lista. `payout_hindrance` gäller utbetalningshinder (§8.2) och byggs i steg 6.
- *Körskripten* i `scripts/simulation/paket_b_steg4/` är inte provade på en lokal kopia av Lakebase.
- *2026-11-22:* standardplanen, paus och förlängning av startade delar och M vid verklig start är byggda i steg 5 (§5.5).

### 5.5 Byggt i steg 5: månadsrätt, skuld och bolagskonto

**Byggt 2026-11-22 på branchen `claude/paket-b-steg-5-manadsr-e22262` och mergat till main 2026-11-23 efter Karls OK (”okej, mergea”); inte infört i Lakebase.**

- **Var det finns:**
  - finansiering, debitering per spår och slutavräkning i `src/skills/calculation/pension_claim.py`, utan databas;
  - beloppsbeslut, bolagskonto, anspråk och läsningar i `src/services/pension_claims.py`;
  - operationerna `register_company_capital` och `list_pension_claims`, båda `HUMAN_ONLY` ([tjänstelager §9.18](../../02_system/tjänstelager.md));
  - stängningens steg 1 och 5 i `src/services/month_close.py`;
  - premier på startade delar i `src/services/ledger_premiums.py`;
  - tabellerna `payout_amounts`, `pension_claims` och `pension_claim_fundings` och migrationen `migrate_pension_claims.py` ([databasschema §7e och §12](../../02_system/databasschema.md));
  - körskripten för Lakebase i `scripts/simulation/paket_b_steg5/`.
- **Verifierat lokalt:**
  - fall 1 och 14 i stängningen;
  - fall 35 med senare finansiering;
  - PB11;
  - W9;
  - fall 5 och 6;
  - januariomräkningen;
  - W10.
  
  Fall 14, 32, 33 och 35 är också verifierade som ren beräkning. Utan steg 5:s tabeller beter sig stängningen som steg 4 (`tests/test_pension_claims.py`, `tests/test_pension_claim_calculation.py`).
- **Verifierat mot `svc_test`:** migrationen från läget efter steg 4, och fall 1 och 14 i novemberstängningen (`tests/test_migration_pension_claims.py`).
- **Jämfört med main (B-052):** novembers stängning med main:s och branchens kod på samma databas (`compare_main.py`). Kontrollerat:
  - utan steg 4:s och steg 5:s tabeller;
  - med steg 4:s men utan steg 5:s tabeller;
  - med och utan ägare som fyllt 66.

  Resultatet var detsamma i alla fall: samma granskningssumma, verifikation, poster, garantidelar och ärenden.

Karls val W1–W12, godkända i chatten 2026-11-22 (”Godkänn alla”). Loggade som **B-053** 2026-11-23 efter Karls OK (”Logga B-053”).

- **W1 Anspråket:**
  - `pension_claims` har en oföränderlig rad per uttagsdel och rättighetsmånad (unik). Raden har plan, beloppsbeslut, löpnummer, brutto, del ur C, bolagsstöd, ej finansierat, slutavräkning och betalningsdag (första bankdagen efter månaden). Stabilt id ur del och månad.
  - Steg 6 bygger betalningsförloppet som egna rader som pekar på anspråket.
- **W2 Beloppsbeslut:**
  - `payout_amounts` har ett beslutat M per del från en månad, med orsak `start`, `restart`, `plan_change` eller `january`, och med G, B, faktor, golv och grund med kontrollsumma.
  - Ordningen: ett befintligt beslut för månaden; planens M när planens ändringsmånad är månaden; nytt M vid första rätt (även efter uppskov) och vid återstart efter paus; januariomräkning; annars senaste beslutet.
  - Nya belopp räknas på föregående månadsslut, med golvet ur `amount_floor` och senast beslutade M.
- **W3 Standardstart:**
  - 66-månadens stängning sparar standardplanen med `origin = 'standard_start'`, med den som stänger som beslutsfattare;
  - G_j räknas om till planen (oförändrat med samma referensplan);
  - delen får läget `in_payout`, och M beslutas;
  - första rätten skuldförs i samma transaktion (fall 1: november, betalning 2026-12-01).
- **W4 Pensionsförloppet:**
  - stängningen skriver `in_payout` vid första rätt och återstart, `paused` vid paus och `ended` vid slutavräkning;
  - startade och pausade delar får avkastning, avgift och skatt i stället för att blockera;
  - paus och förlängning av startade delar bokas (fall 5 och 6);
  - registrerat dödsfall blockerar fortfarande (steg 7).
- **W5 Debitering och bolagsstöd:**
  - debiteringen ur C är min(M, C efter kostnader), fördelad på delens spår i ören med största bråkrest (`pension_debit`);
  - bolagsstödet K = M − debiteringen förs direkt från bolagskontot till betalningsskulden (`company_support`), utan att passera C.
- **W6 Slutavräkning (PR-027):**
  - den tidsbegränsade delens sista rätt är max(M, C), med bolagsstöd vid brist; därefter C = 0 och delen `ended`;
  - fall 32 och 33 hör till steg 5 (§12); fall 34 verifieras i steg 6.
- **W7 Bolagskonto:**
  - `register_company_capital` bokar insättningen som en egen verifikation `company_capital` i första öppna månaden;
  - insättningen har belopp, beslutsdag, dokumentreferens och en valfri hänvisning till aktuariens E_min, och är idempotent;
  - bolagskontot och skulden blir aldrig negativa (villkor i databasen);
  - granskningen visar likviditetsdelen 12 × ΣM och markerar stressgapet som ej beräknat (projekt 6, A8);
  - den första stängningen med en rätt kräver en registrerad insättning (PB11).
- **W8 Ej finansierat (fall 35):**
  - månaden stängs och rätten bevaras; skulden bokas bara för den finansierade delen;
  - verifikationen märks `economic_block`, och samma transaktion öppnar eller fyller på ett ärende `company_capital` utan person;
  - steg 6 får inte skapa bankuppdrag för det ej finansierade;
  - efter en ny insättning finansierar nästa stängning de äldsta ej finansierade anspråken först (`pension_claim_fundings`).
- **W9 Premie på startande eller startad del:**
  - premien hålls utanför journalen och redovisas som innehållen i granskningen;
  - delen får ett ärende `payout_review` (`premium_after_start`) en gång;
  - utan steg 5:s tabeller blockerar premien som förut.
- **W10 Rättelse:** en rättelse av en månad med anspråk tillåts bara när varje anspråks brutto och del ur C är oförändrade. Ändrad fördelning på spåren bokas som motposter; annars blockeras rättelsen.
- **W11 Kontrollposter:**
  - *standardstart* godkänns när planen sparas;
  - *rätt enligt plan* ersätts av *månadsrätt*;
  - nya kontroller är *förbrukade rätter* (anspråken före månaden mot kalenderns förbrukade rätter) och *skuld och bolagskonto*;
  - *kapital totalt* drar av pensionsdebiteringen;
  - ledger-utdraget och A6 redovisar startade delar och skuld som förut.
- **W12 Migration och befogenheter:**
  - `migrate_pension_claims.py` förutsätter steg 4:s migration;
  - båda operationerna är `HUMAN_ONLY`, och agenterna får inga rättigheter;
  - ordningen i Lakebase är novembers stängning, steg 4:s migration och sedan steg 5:s, var och en efter eget OK.

Avvikelser från designen och valen:
- *Inget `claim_id` på kapitalposterna (W1).* Posterna på skulden och bolagskontot bär uttagsdelen och månaden, och deras stabila id härleds ur anspråkets id. En tredje tabell, `pension_claim_fundings`, bär den senare finansieringen (W8) i stället för en ändring av anspråket.
- *Bolagsstödet passerar inte C (W5).* PR-020 talar om ett eget stödspår. Den ekonomiska effekten är densamma, eftersom stödet förbrukas samma månad.
- *Slutavräkningen i stängningen* är byggd men inte provad hela vägen: en tidsbegränsad del når sin sista rätt först efter minst 60 bokade rätter. Fall 32 och 33 är verifierade som ren beräkning.
- *Ärendetypen `company_capital`* gäller bolaget, och `ck_cases_subject` tillåter den utan person och arbetsgivare.
- *Premien efter start (W9)* bokas först när ny försäkring för sådana premier finns (PR-025, senare steg).
- *Körskripten* är provade på en lokal SQLite-kopia, inte på en kopia av Lakebase.

## 6. Operativ kapital- och garantijournal (PB4)

### 6.1 En journal för bolagets faktiska kapital

Journalen ägs av tjänstelagret (projekt 1/6). Den är **bolagets enda källa** för C och G
efter övergången. Posterna är oföränderliga; rättelser är nya länkade poster.

| Del | Innehåll |
|---|---|
| Garantidel | Uttagsdel, ursprung (premieallokering eller S-04-premierad), P_j, mottagningsmånad, värdedatum, premieperiod, referensplan, grundkod och hash, A_g, G_j i hög precision. Delning och omräkning ger nya versioner med länk; den historiska grunden byts aldrig |
| Kapitalpost | Uttagsdel, kapitalspår, månad, orsak (`premium`, `return`, `fee`, `tax`, `pension_debit`, `company_support`, `pool_in`, `pool_out`, `split`), konto, belopp i ören, in- och utgående spårsaldo, stängningens id |
| Konton | Kundkapital per del, betalningsskuld, skatteskuld, arvsvinstpool, bolagskonto och avstämningskonto. Kapital, skuld och pool blandas aldrig i samma saldo |
| Kontrollpost | Avstämningens led, skillnad, källor och utfall, utan ekonomisk effekt |

### 6.2 Övergången från S-04

1. Ingående läge är S-04 per **2026-10-31**, samma utdrag som P6-MANAD-001 frös
   (hash `023946…3fefa`). Ursprungsspåren återskapas med `reconstruct_origins`.
2. Varje försäkrings C och G och kollektivets summa ska bevaras exakt i ören:
   42 087 223,57 kr och 119 195,6502916268 kr/mån. Annars stopp.
3. Posterna märks `reconstructed_s04` och pekar på sina premierader. Historiska
   `premium_transactions` ändras inte.
4. Från november 2026 är paket A:s betalningsallokeringar den enda källan för nya
   premier. Status `paid` används inte som källa, så delbetalningen från
   SvenskIndustries kommer med. Avstämningskontot följer inte med.
5. S-04-rekonstruktion och journal får aldrig summeras för samma premie.

### 6.3 Förhållandet till P6-MANAD-001

P6-MANAD-001:s tabeller är ett scenarioverktyg: frysta källpaket, syntetiska händelser
och värderingar som aldrig låses. Paket B ändrar inte det. Två regler förhindrar dubbla journaler:

- En operativ månad har bara den operativa journalen som källa. Aktuariens analys
  `monthly_fta_change` ska kunna ta en operativ månadsstängning som källa, i stället
  för att återskapa samma premier i en scenariojournal.
- Ett scenario får utgå från en operativ stängning som IB men skriver aldrig tillbaka till den.

Paket A:s överlämning (`export_premium_month`, PA7) får därmed en operativ mottagare.
Kontraktet `ReceiptInput` och allokeringsprovet i ören återanvänds oförändrade.

**Byggt i steg 2 (2026-11-14, mergat till main efter Karls OK; infört i Lakebase 2026-11-15 efter backup `backups/20261114T231325Z` och Karls OK, [databasschema §12](../../02_system/databasschema.md)):**
- **Var det finns:** journalens fyra tabeller ([databasschema §7c](../../02_system/databasschema.md#7c-tabeller-ledger_batches-ledger_guarantee_parts-ledger_capital_entries-och-ledger_controls--kapital--och-garantijournalen)), övergången från S-04, A6-källan `ledger` och paket A som premiekälla ([tjänstelager §9.15](../../02_system/tjänstelager.md#915-kapital--och-garantijournalen-paket-b-steg-2-b-047--vad-som-stöds-och-vad-som-blockeras)).
- **Verifierat:** fall 36 och 37 lokalt, och migrationen och övergången mot isolerad Postgres.
- **På en återställd kopia av Lakebase-backupen `backups/20261114T150341Z`:**
  - S-04 har hashen `023946…3fefa`;
  - journalen bevarar 492 försäkringar och 15 097 garantidelar med C 42 087 223,57 kr och G 119 195,6502916268 kr/mån, exakt per försäkring;
  - A6 ger samma FTA, VÅ och U ur båda källorna;
  - november 2026 ger 51 623,90 kr, varav SvenskIndustries 15 362,24 kr, utan avstämningskontots 36 261,66 kr.

Avvikelser, godkända av Karl i chatten 2026-11-14 (”Godkänn avvikelserna”):
- *Ingående saldo:* en IB-post per kapitalspår med den nya orsaken `opening` (vald av Karl 2026-11-14). §6.1:s orsakslista hade inget ingående saldo.
- *Fall 37 i steg 2:* premiekällan och dess kontroll är byggda (`preview_ledger_premiums`), men bokningen vid månadsslut sker i månadsstängningen i steg 3 (vald av Karl 2026-11-14). Fall 37 är därmed verifierat som källa och belopp; tillförseln provas igen i steg 3.
- *Övergången är ett eget ingrepp,* operationen `open_capital_ledger` (`HUMAN_ONLY`), efter migrationen. Det följer §12 punkt 2–3.
- *Det ingående lägets S-04-utdrag sparas* i `valuation_extracts`, och verifikationen pekar på det. Ledger-utdraget stämmer sitt kapital mot det.
- *Ej överförda:* en försäkring med startad uttagsdel förs inte över och redovisas, som i S-04. I Lakebase finns inga.
- *Verifikationens slag* är bara `opening_s04`. Steg 3 vidgar villkoret med stängning och rättelse. Kontona och orsakerna i §6.1 finns redan i villkoren.
- *A6:s standardkälla* förblir S-04. `ledger` gäller bara datum journalen täcker, i steg 2 bara 2026-10-31.
- *P6-MANAD-001:* när det ingående läget finns blir IB:s kontrollsumma ledger-utdragets, och ursprungsspåren läses ur journalen. Ett paket som redan frysts mot S-04:s hash kräver då ny export. Scenariots egen stängning märker fortfarande sitt UB `ledger`; det är en namnlikhet, inte den operativa journalen.

## 7. Månadsstängningen (PB5)

### 7.1 Ordning

En körning per pensionsmånad för hela kollektivet, med samma värderingsversion
genom alla steg (PR-020):

| Steg | Innehåll | Motor |
|---|---|---|
| 1 | Öppningskapital, levandestatus, kollektivmedlemskap, planändringar och månadens rätt enligt föregående månads beslut. Standardstart vid 66 (§5.2) | Ny läsning av journal och planer |
| 2 | Avkastning på öppningskapital enligt antagen AVK för månaden (PR-021) | `close_month` + `roll_origins` |
| 3 | Kapitalavgift och skattebelastning på öppningsbas (PR-022, PR-023) | `close_month` + `roll_origins` |
| 4 | Månadens mottagna nettopremier vid månadsslut, med garantidel på ej startad del, utan avkastning denna månad | Paket A:s allokeringar, `guarantee_part` |
| 5 | Månadsrätt skuldförs en gång per del; sista rätten slutavräknas (PR-027); bolagsstöd vid brist (PR-028) | Ny anspråkslogik, `allocate_cents` |
| 6 | Dödsfallsavräkning: obetalda rättigheter till skuld om de inte redan debiterats, återstående C till pool (PR-010) | Ny |
| 7 | Poolen fördelas på behöriga delar efter SIM-R (PR-011) | `monthly_q`, `allocate_cents` |
| 8 | Stäng, stäm av tillgångar, skulder och pool, och fastställ underlag för nästa månads start, återstart och januariomräkning | Kontrollposter |

### 7.2 Granskning, idempotens och rättelse

`prepare_month_close` räknar hela stängningen utan att skriva och ger en sammanställning
med granskningssumma: IB-hash, AVK-version, parametrar, paket A:s stoppunkt, planer,
dödsfall, poster per steg och avstämningar. `close_policy_month` binder summan och
skriver allt i en transaktion. Ändrat underlag mellan granskning och stängning ger
konflikt. Samma innehåll igen ger samma stängning och inga nya poster.

En stängd månad ändras aldrig. Rättelse blir en ny version med motposter, granskad på
samma sätt. Mottagningar efter stoppunkten hör till nästa månad.

**Blockeras:** saknad eller ej antagen AVK för månaden, saknad parameterversion för
avgift eller skattebelastning, öppen föregående månad, ospårbar garantidel och en
kontroll som inte går ihop. En blockerad månad skapar inga anspråk.

**Byggt i steg 3 (2026-11-19, mergat till main efter Karls OK (`b6b9ebb`); migrationen införd i Lakebase samma dag efter backup `backups/20261119T201517Z`, [databasschema §12](../../02_system/databasschema.md); novembers AVK och stängning tidigast 2026-12-01):**
- **Var det finns:**
  - stängningen och rättelsen i `src/services/month_close.py`;
  - operationerna `prepare_month_close`, `close_policy_month` och `get_month_close`, alla `HUMAN_ONLY` ([tjänstelager §9.16](../../02_system/tjänstelager.md));
  - verifikationsslagen och versionskedjan i `ledger_batches` med migrationen `migrate_month_close.py` ([databasschema §7c och §12](../../02_system/databasschema.md));
  - körskripten för Lakebase i `scripts/simulation/paket_b_steg3/`.
- **Steg 1–4 och 8** för sparandet. Avkastning, avgift och skattebelastning räknas per kapitalspår med `close_month` och `roll_origins`, på samma sätt som S-04. Månadens premier ur paket A bokas vid månadsslut med garantidel och utan avkastning. Elva kontrollposter. Steg 5–7 byggs i steg 5–7 i byggordningen.
- **Verifierat:**
  - lokalt: fall 13, 15, 16, 17 och fall 37 i stängningen (`tests/test_month_close.py`);
  - mot isolerad Postgres (`svc_test`): migrationen från Lakebase-läget efter steg 2 och novemberstängningen med låset (`tests/test_migration_month_close.py`);
  - körskripten hela vägen, från granskning till kontroll, på en lokal kopia.
- **Ledger-utdraget och A6** täcker varje stängd månads slut. Månadssummorna kommer ur stängningarna, flödena ur kapitalposterna och AVK ur den sist stängda månaden.

Karls val S1–S7, godkända i chatten 2026-11-19 (”Godkänn alla”) och loggade som **B-050**:
- **S1 Verifikationer:** slagen `month_close` och `month_correction`, och kolumnen `supersedes_id` som pekar på versionen en rättelse ersätter. Villkoren ger en stängning per månad och en rak versionskedja.
- **S2 Rättelse:** motposterna är nettodifferensen per kapitalspår och orsak mot den gällande versionen. Ökningar bokas först, så att inget saldo blir negativt. Oförändrat underlag ger ingen rättelse.
- **S3 Stoppunkt:** det som är registrerat i paket A när månaden stängs.
  - En betalning som registreras sent, med mottagningsdag i en stängd månad, bokas i nästa öppna månad. Den redovisas som `late_allocations` och `late_sek`, och den ger ingen rättelse.
  - En rättelse gäller ändrad AVK eller parameter.
  - En ändrad redan bokad allokering i paket A blockerar och prövas manuellt.
  - Bara den senast stängda månaden kan rättas.
  - Premiekällan tar fram en månad först när föregående månad är stängd.
- **S4 Pensionsförloppet:**
  - En startad, pausad eller avslutad uttagsdel med kapital blockerar. Det gör också ett registrerat dödsfall. Månadsrätt, slutavräkning och dödsfall byggs i steg 5–7. *Efter steg 5:s migration stängs startade och pausade delar med månadsrätt; dödsfall blockerar till steg 7 (§5.5, W4).*
  - En ej startad del vars ägare fyllt 66 utan plan stängs för sparandet. Den redovisas i kontrollen *standardstart väntar på steg 4*; startmånaden flyttas inte. *Efter steg 4:s migration heter kontrollen* standardstart *och räknar planer och ärenden; före migrationen är den oförändrad (§5.4, V4).*
  - En startad del utan kapital i journalen ligger utanför stängningen.
- **S5 AVK för november:** AVK-SIM-2026-02 har AVK-SIM-2026-01:s historik och november +0,20 %, exakt som P6-MANAD-001 D5 (§13). Den föreslås och antas genom A4 från 2026-11-01 med Karl som aktör, av `adopt_avk.py` efter separat OK.
- **S6 Ordning i Lakebase:** migrationen kan införas när steg 3 är mergat. AVK, granskning och stängning görs tidigast 2026-12-01, efter novembers sista bankfil. Ordningen är backup → torrkörning → migration (OK) → AVK (OK) → granskning → stängning (OK) → skrivskyddad kontroll.
- **S7 Befogenheter:** alla tre operationerna är `HUMAN_ONLY`. Systemaktören nekas stängningen, agenterna får inga rättigheter, och granskningen är bunden till kontrollsumman. Avgift och skatt som inte kunde tas ut syns bara i sammanställningen.

Avvikelser från §7.2:
- *Sammanställningen* har inga planer eller dödsfall att visa. Planerna byggs i steg 4; dödsfall blockerar enligt S4. *Steg 4 lägger till avsnittet `payout` med planer, delningar, standardstarter och ärenden (§5.4).*
- *Testdatabasen:* saldovillkoret på kapitalposterna prövas på halva ören i SQLite, eftersom SQLite räknar `NUMERIC` som flyttal. Postgres-DDL:en är oförändrad.

## 8. Skatt, utbetalning och bankkvitto (PB7, PB8)

### 8.1 Preliminär skatt (PR-026)

Skatten räknas vid bankuppdraget och styrs av utbetalningsdagens år, inte
rättighetsmånadens. `register_tax_status` sparar per person och år en av:

| Status | Första versionen |
|---|---|
| Individuellt beslut från Skatteverket | Stöds med registrerad procent, belopp eller jämkning och giltighet |
| Sidoinkomst | 30 %; kunden kan begära högre frivilligt avdrag |
| Huvudinkomst | Pensionskolumn 2 för födda 1959 eller tidigare, annars 6 (2026). Kräver tabellparameter för året och utbetalarens ort, och förhöjt avdrag när SFL 11 kap. 21 § kräver det. Saknas parametern: blockerad betalning, skulden kvar, ärende |
| SINK | Endast med registrerat beslut; adress räcker inte |

Avdraget räknas i hela kronor och öretalet bortfaller. Netto = brutto − avdrag och
aldrig negativt. För A-skatt görs inget avdrag när utbetalningen understiger 100 kr eller
förväntad årssumma från bolaget understiger 1 000 kr, summerat över personens delar.
Skatten blir skuld till staten först när utbetalningen verkställs. En avvisad betalning
skapar ingen andra skatteredovisning.

### 8.2 Bankuppdrag och kvitton

1. **Konto:** `register_payout_account` sparar verifierat konto per mottagare. Saknat
   eller overifierat konto ger ärende `payout_hindrance`; skulden står kvar, och det är
   inte ett uppskov eller en paus.
2. **Bankuppdrag:** efter stängd månad skapar `create_payout_orders` ett uppdrag per
   mottagare för första svenska bankdagen efter pensionsmånaden. Raderna visar varje dels
   anspråk, brutto, skatt och netto. Misstänkt dödsfall eller blockerad skatt stoppar personens uppdrag.
3. **Godkännande:** `approve_payout_order` binder bankfilens kontrollsumma. Utbetalning
   är en extern handling (MASTER_CONTEXT §3.5), även mot simulerad bank.
4. **Kvitton:** `import_payout_receipts` läser bankens svarsfil idempotent, på samma sätt
   som `import_bank_file`: utförd, avvisad, återkommen eller okänt utfall. Samma kvitto
   igen ger ingen effekt; samma id med ändrat innehåll ger konflikt.
5. **Nytt försök:** med samma anspråks-id när kontot är verifierat. Vid okänt utfall
   inväntas avstämning före nytt försök. Återkommen betalning öppnar skulden igen med
   bankreferens och skatteavstämning.

Simulatorn får en utbetalningssida: banken svarar på bankfilen enligt scenario (utförd,
avvisad konto, återkommen, okänt), och nya händelsetyper för kundbegäran och
dödsfallsbesked. Den skriver aldrig i affärstabellerna, och facit hålls separat (PA8).

### 8.3 Val för steg 6: skatt, konto, bankuppdrag och kvitton

**Godkända av Karl i chatten 2026-11-24 (”Godkänn alla”) enligt rekommendationerna. Loggade som B-054 samma dag efter Karls OK (”Logga och bygg”).**

Steg 5:s kontrakt består: `pension_claims`, `pension_claim_fundings` och `payout_amounts` ändras inte, och
anspråkets `payment_day` ligger fast. Tre ändringar i steg 5:s kod och villkor följer av valen och
flaggas här: skuldens utgående saldo i `month_close._payouts` räknar in utbetalningar (X10), `tax_liability`
blir ett konto som aldrig får bli negativt (X9), och villkoren för verifikationens slag, postens orsak och
ärendetypen vidgas (X5, X6, X9).

- **X1 Datamodell:** sex tabeller där rader bara läggs till, alla med pekare till `pension_claims`:
  - `tax_statuses`: skattestatus per person och år i en versionskedja;
  - `payout_accounts`: konto per person i en versionskedja;
  - `payout_files`: bankfilen per betalningsdag, med kontrollsumma och godkännande;
  - `payout_orders`: ett uppdrag per mottagare, med kontoversion, skattestatusversion, skatteår, brutto, skatt, netto och beräkningsunderlag;
  - `payout_order_lines`: en rad per anspråk och försök, unik på (anspråk, försöksnummer);
  - `payout_receipts`: bankens kvitton, unika på (källsystem, kvitto-id), med innehållskontrollsumma.
  
  Betalningslägena i §4 härleds ur raderna. Anspråket ändras aldrig (W1).
- **X2 Betalbart anspråk (W8):** bara ett helt finansierat anspråk utan öppen eller verkställd rad. Hela bruttot betalas i en rad.
- **X3 Skatteberäkning (fall 18–20):**
  - per uppdrag (person och betalningsdag) på summan av personens delar, med utbetalningsdagens år;
  - hela kronor, öretalet bortfaller, och netto blir aldrig negativt;
  - gränserna 100 och 1 000 kr är strikt mindre än och gäller A-skatt, inte SINK;
  - förväntad årssumma är det som verkställts i året plus återstående rätter i året enligt planerna och M, över personens alla delar, sparad i uppdraget;
  - engångsbelopp (sena betalningar och nya försök) särredovisas, och skatten bokas på uppdraget, inte per del.
- **X4 Huvudinkomst (§13):** registreras med tabellnummer, kolumn och eventuellt förhöjt avdrag men betalas inte ut. Uppdraget blockeras med ärende `tax_status` (`table_missing`) och skulden står kvar (fall 21). Skattetabellen byggs som ett eget steg när Karl hämtat Skatteverkets tabeller för 2026 och 2027, med engångstabellen, i en egen versionsbunden tabell med källa och kontrollsumma.
- **X5 Skattestatus:** `register_tax_status` per person och år med kanal och verifierad aktör; en ny version ersätter den förra uttryckligen. SINK kräver beslutsreferens. Frivilligt högre sidoavdrag är ett heltal på minst 30 % och gäller från första betalningen två veckor efter begäran. Saknad status för utbetalningsdagens år blockerar personens uppdrag med ett ärende `tax_status` en gång per person och år.
- **X6 Konto och hinder (fall 22):** `register_payout_account` sparar en versionskedja per person med verifieringssätt och dokumentreferens; kontobyte är en ny version. Saknat, overifierat, avvisat eller återkommet konto ger ärende `payout_hindrance`; skulden står kvar och delens läge rörs inte. Läsningarna maskerar kontonumret.
- **X7 Bankfil och godkännande:**
  - `create_payout_orders(dag)` efter stängd månad, med alla betalbara anspråk, även nya försök och senare finansierade, och en kontrollsumma ur innehållet;
  - ändrat underlag före godkännandet ersätter den förberedda filen; en godkänd fil ändras aldrig;
  - utförandedagen är den senare av betalningsdagen och nästa bankdag från i dag, och en försening redovisas (dröjsmålsränta senare steg);
  - `approve_payout_order` binder filens kontrollsumma, en gång per fil, och är den externa handlingen;
  - en person med status `deceased` stoppas; misstänkt dödsfall kommer i steg 7.
- **X8 Kvitton och nytt försök (fall 23–25):** `import_payout_receipts` som `import_bank_file`: samma kvitto igen ger ingen effekt, samma id med ändrat innehåll ger konflikt för hela filen.
  - *Utförd:* bokas (X9).
  - *Avvisad:* inget bokas; hinderärende.
  - *Återkommen:* motposter; hinderärende.
  - *Okänt:* inget nytt försök förrän ett senare kvitto för samma uppdrag ger utförd eller avvisad.
  - Ett nytt försök är en ny rad med samma anspråk, när ett konto verifierats efter kvittot. Det ger aldrig nytt anspråk, belopp eller kapitaldebitering.
- **X9 Journalen och skatteskulden:** varje kvittofil bokas som en egen verifikation `payout_settlement` i första öppna månaden, som `company_capital`. Utförd: betalningsskulden −brutto per del (`payout`) och skatteskulden +skatt (`withholding`). Återkommen: exakta motposter (`payout_returned`), så att ett nytt försök ger en skatteredovisning (fall 23). Skatteskulden blir aldrig negativ, ingår inte i FTA och går till projekt 6.
- **X10 Stängningen och B-052:** steg 8 räknar in månadens utbetalningar i skuldens saldo och får kontrollen *utbetalningar* (verkställt netto + skatt = utbetalt brutto), bara när steg 6:s tabeller finns. `scripts/simulation/paket_b_steg6/compare_main.py` prövar main:s fyra lägen och `steg5` med en startad del, och ett regressionstest låser resultatet. `ledger_premiums.py` ändras inte.
- **X11 Simulatorn:** bara banksidan, `payout_receipt_file` med källan `bank-sim-payout`; scenarier per person är utförd, avvisad, återkommen och okänt med senare utfall. Facit hålls separat (PA8). Dödsfallsbesked i steg 7, kundbegäran senare.
- **X12 Befogenheter:** sex nya operationer, alla `HUMAN_ONLY`: `register_tax_status`, `register_payout_account`, `create_payout_orders`, `approve_payout_order`, `import_payout_receipts` och `list_payout_orders`. Systemaktören och agenterna nekas godkännandet, och agentrollerna får inga rättigheter. Ärendetyperna `payout_hindrance` och `tax_status` ligger utanför ärendepolicyn.
- **X13 Migration och Lakebase:** `migrate_payout_orders.py` förutsätter steg 5:s migration. Ordningen är novembers stängning, därefter steg 4:s, steg 5:s och steg 6:s migration, var och en med backup, torrkörning och eget OK.

**Verifiering:** fall 18–25 och 34 lokalt; migrationen och fall 18 och 23 hela vägen mot `svc_test`; jämförelsen
mot main enligt X10 före merge. **Utanför steg 6:** dröjsmålsränta, dödsbo, KU och AGI, skatteinbetalning,
prognos till projekt 5 och handläggarsidan (steg 8).

**Byggt i steg 6 (2026-11-24 på branchen `claude/paket-b-steg-6-design-03306f`; mergat till main samma dag, inte infört i Lakebase):**

- **Var det finns:**
  - skatten per uppdrag i `src/skills/calculation/payout_tax.py`, utan databas;
  - skattestatus, konto, bankfil, godkännande, kvitton och verifikationen `payout_settlement` i `src/services/payout_orders.py`;
  - de sex operationerna, alla `HUMAN_ONLY` ([tjänstelager §9.19](../../02_system/tjänstelager.md));
  - kontrollen *utbetalningar* i `src/services/month_close.py`;
  - banksidans kvittofil i `src/simulation/counterparties.py`;
  - tabellerna och migrationen `migrate_payout_orders.py` ([databasschema §7f och §12](../../02_system/databasschema.md));
  - jämförelsen med main i `scripts/simulation/paket_b_steg6/compare_main.py`.
- **Verifierat lokalt:** fall 18–25 och 34, decembers stängning med kontrollen *utbetalningar* och stängningen utan steg 6:s tabeller. Jämförelsen med main `2ed556d` är identisk i alla fem lägen (B-052). Migrationen och fall 22 är verifierade mot `svc_test` (`tests/test_migration_payout_orders.py`).
- **Preciseringar vid bygget** (inom valen):
  - en avliden person stoppas utan ärende; ärendet kommer med dödsfallet i steg 7;
  - efter avvisning eller retur krävs en ny verifierad kontoversion, inte bara ett verifierat konto (X8);
  - en ersatt fils rader räknas som försök, så försöksnumret ligger utanför filens logiska kontrollsumma; samma underlag ger därför samma fil (X7);
  - den förväntade årssumman räknar också med obetalda rätter med betalningsdag i året, utöver det verkställda och de återstående rätterna (X3);
  - pensionskolumnen för huvudinkomst prövas för 2026 (2 för födda 1959 eller tidigare, annars 6); uppdraget blockeras ändå (X4);
  - kontrollen *utbetalningar* prövar både skuldens och skatteskuldens poster mot kvittofilernas summor (X10).

## 9. Dödsfall, slutavräkning och bolagskapital (PB9–PB11)

**Dödsfall (PR-010).** `register_death_report` sparar dödsdatum, källa och rapportdatum
som `suspected` eller `verified`; `verify_death_report` verifierar eller drar tillbaka.
Misstänkt stoppar nya bankuppdrag men raderar ingen rätt. Verifierat avräknas i nästa
stängning: pågående ej pausad del får hela dödsmånadens rätt, även vid dödsfall den
första dagen eller på startdagen. Pausad del får ingen dödsmånadsrätt. Obetalda
rättigheter som redan är skuld dras inte igen. Återstående C förs till poolen.
`insured_persons.status` sätts till `deceased` vid verifiering, så att befintliga
spärrar fortsätter att gälla. Ett sent besked efter redan betalda månader ger ärende
för återkravsprövning, aldrig automatisk kvittning eller negativ arvsvinst.

**Arvsvinst (PR-011).** Poolen fördelas samma månad på delar som ingått hela månaden,
lever vid månadens slut och inte är slutavräknade, med vikten
`E_i = C_i_öppning × q_i/(1 − q_i)` på aktuell SIM-R. Arvsvinst ökar C, aldrig G.
Inga mottagare eller okänd risk ger kvarstående pool och ärende.

**Slutavräkning (PR-027).** Bara tidsbegränsad verifierad ITP-del. På sista rättens
stängning, efter avkastning och kostnader och före pensionsdebiten:
`M_sista = max(beslutat M, C_tillgängligt)`, med bolagsstöd vid brist. Därefter är
delens C = 0 och delen `ended`. Obetalda skulder, bankfel och skatteposter lever vidare.
Livsvarig del slutar aldrig på grund av ålder eller lågt C.

**`terminate_policy`.** Ingen egen operation (preciserar B-030 p. 4). En försäkring
visas som avslutad när alla dess delar är `ended`, premieförloppet är avslutat och inga
skulder eller fordringar är öppna. Det är en härledd läsning, inte en lägesändring.

**Bolagskapital (PR-028).** Bolagskontot i journalen får en startinsättning som Karl
registrerar med `register_company_capital`, dokumenterad som finansieringshändelse.
Stödet per del är `K_i = max(0, bruttorätt − tillgängligt C_i)` och förs från bolagskontot
med motpost. Stöd skapar ingen garanti. Räcker kontot inte: anspråket står kvar som
ej finansierat, körningen markeras ekonomiskt blockerad, ärendet eskaleras till Karl och
ingen betalning rapporteras som lyckad. Startbeloppet E_min beräknas av aktuarien
(projekt 6); paket B kräver bara att en dokumenterad insättning finns.

### 9.1 Val för steg 7: dödsfall och arvsvinst

**Godkända av Karl i chatten 2026-11-24 (”Godkänn alla”) enligt förslagen. Loggade som B-055 samma dag
efter Karls OK (”Logga och bygg”).** Valen preciserar PB9, PB10 och §9
ovan och ändrar inga produktregler. Varje val har ett förslag, ett alternativ, en motivering och en
regelreferens.

Kontrakten från steg 5 och 6 består. Ett anspråk ändras aldrig (W1), och ett bankförsök är en egen rad
(X1). Valen kräver ändå ändringar i steg 5:s och 6:s kod och villkor. De flaggas här:
- `month_close.py`:
  - rätten i månaden begränsas till och med dödsmånaden;
  - en avräknad del lämnar `plans_in_force`;
  - stängningen får steg 6 och 7 (Y4, Y6 och Y7).
- `pension_claims.outstanding_unfunded` och `payout_orders._payable`: ett återfört anspråk räknas varken som
  ej finansierat eller som betalbart (Y5).
- `payout_orders.build_file`: misstänkt dödsfall stoppar personen. Ett verifierat dödsfall stoppar tills
  dödsboet är prövat (Y3 och Y10).
- Villkoren vidgas för postens orsak, för konton som aldrig blir negativa, för garantidelens orsak och för
  ärendetypen (Y8 och Y11).

`ledger_premiums.py` ändras inte (Y6).

- **Y1 Datamodell**
  - *Förslag:* fyra tabeller där rader bara läggs till:
    - `death_reports`: dödsfallsbesked per person i en versionskedja. Läget är `suspected`, `verified`
      eller `withdrawn`. Raden har dödsdag, rapportdag, mottagningsdag, källa med referens, kanal, aktör
      samt verifieringssätt med dokumentreferens. Den är unik på (person, version) och, när beskedet kommer
      i en fil, på (källsystem, besked-id).
    - `death_settlements`: en rad per avräknad uttagsdel. Raden har beskedets version, dödsmånaden och
      stängningens verifikation, samt dödsmånadens anspråk, återförda anspråk, kapital till poolen och
      kvarstående skuld till dödsboet. Den är unik på uttagsdelen, så varje del avräknas en gång.
    - `pension_claim_reversals`: ett återfört anspråk efter dödsmånaden (Y5), unikt på anspråket. Raden
      har beloppen som går tillbaka till kundkapitalet och bolagskontot.
    - `estate_authorities`: dödsboets företrädare per avliden person i en versionskedja (Y10). Raden har
      roll, behörighetshandling, verifiering och beslutsfattare samt en kontoversion i `payout_accounts`.

    Delens slut skrivs som `ended` med orsaken `death` i `payout_part_states`. Steg 1 tillåter redan det.
  - *Alternativ:* dödsdag och besked som kolumner på `insured_persons`, och anspråk efter dödsmånaden
    markerade direkt på `pension_claims`.
  - *Motivering:* ett besked kan ändras, dras tillbaka eller komma sent. Varje version ska därför gå att
    spåra med sin rapportdag (T-005). Att skriva på anspråket bryter W1, som steg 6 bygger på.
  - *Regel:* PR-ITP1-010, PR-ITP1-019 p. 5–6 och PR-ITP1-031. UTTAG_GEMENSAMT kräver verifierat
    dödsdatum och rapportdatum.
- **Y2 Registrering och verifiering**
  - *Förslag:*
    - `register_death_report` sparar ett besked som `suspected`. Med verifieringssätt och
      dokumentreferens kan beskedet sparas direkt som `verified`. Ett verifierat besked kräver dödsdag,
      och dödsdagen får inte ligga efter rapportdagen.
    - `verify_death_report` kan verifiera ett misstänkt besked, ändra dödsdagen som en ny version eller
      dra tillbaka beskedet. Verifieringssätten är folkbokföringen, dödsbevis och annan handling med
      referens.
    - Vid verifieringen sätts `insured_persons.status` till `deceased`, och personens tidigare status
      sparas i versionen. Då gäller de befintliga spärrarna för löneunderlag, rättelse, plan, begäran och
      bankuppdrag direkt (§9). Om beskedet dras tillbaka före avräkningen återställs den sparade statusen.
    - När personens delar är avräknade (Y6) kan beskedet inte längre ändras eller dras tillbaka. En sen
      ändring blir ett ärende för manuell rättelse (PR-019 p. 6). Den rättelsen byggs i ett senare steg.
    - Varje registrering öppnar ett ärende `death_report` för personen eller fyller på det som finns.
  - *Alternativ:* varje besked registreras som misstänkt och verifieras alltid i ett andra steg. Ett annat
    alternativ är att ett besked ur folkbokföringen räknas som verifierat utan handläggare.
  - *Motivering:* PB9 tillåter båda lägena. Ett verifierat dödsfall avslutar pensionen, så verifieringen
    ska vara en människas beslut med en handling som grund. Statusen på personen återanvänds eftersom
    spärrarna i tjänstelagret redan läser den.
  - *Regel:* PR-ITP1-010 kräver verifierat dödsdatum, källreferens och rapportdatum. Enligt PR-ITP1-031
    avgörs misstänkt dödsfall av en människa. Se även T-ITP1-005.
- **Y3 Misstänkt dödsfall (fall 30)**
  - *Förslag:*
    - Ett öppet misstänkt besked stoppar personens bankuppdrag med skälet `death_suspected` i bankfilen.
      Inget ärende öppnas utöver `death_report`.
    - Stängningen påverkas inte. Rätter skuldförs, kapitalet förvaltas och delarna får arvsvinst.
    - En förberedd fil som innehåller personen ersätts, och ett godkännande av den gamla filen ger konflikt
      (X7).
    - När beskedet dras tillbaka kommer uppdragen med i nästa bankfil.
  - *Alternativ:* misstänkt dödsfall stoppar också nya rätter, eller undantar delarna från arvsvinsten.
  - *Motivering:* PR-010 säger att flaggan stoppar nya bankuppdrag men inte raderar intjänad rätt. Om
    beskedet senare verifieras med en tidigare dödsdag återförs rätterna efter dödsmånaden (Y5). Den
    arvsvinst som delarna har fått följer då kapitalet tillbaka till poolen (Y6), och ingen annan mottagare
    debiteras.
  - *Regel:* PR-ITP1-010, PR-ITP1-011 och PR-ITP1-019 p. 6.
- **Y4 Var månadsrätten upphör (fall 28)**
  - *Förslag:*
    - En del har rätt i månaden M bara om planen ger rätt i M och M är senast dödsmånaden D. Rätten gäller
      hela månaden, även vid dödsfall den första dagen.
    - En pausad del får ingen rätt i dödsmånaden. En del som inte har startat före D får ingen pension.
      En del vars första rätt eller återstart är D får en hel rätt, även vid dödsfall på startdagen.
    - En ägare som fyller 66 och dör i 66-månaden får standardplanen och dess första rätt, om resten av
      underlaget i V5 är verifierat. V5:s krav på en levande ägare prövas då mot dödsdagen, inte bara mot
      statusen.
    - Delen får läget `ended` med orsaken `death` från månaden efter D. Om beskedet kommer efter att D har
      stängts gäller läget i stället från avräkningsmånaden.
  - *Alternativ:* rätten upphör vid rapportdagen, eller räknas per dag i dödsmånaden.
  - *Motivering:* ITP 7.5 ger pension längst under dödsmånaden. T-005 väljer att dödsfall på startdagen
    ger hela månaden, eftersom datumet saknar klockslag. Ett läge som börjar i avräkningsmånaden skriver
    inte om historiken. Det som har rättats står i stället i avräkningen och i de återförda anspråken.
  - *Regel:* PR-ITP1-010, villkoren §12, T-ITP1-005 och PR-ITP1-025.
- **Y5 Anspråk och bankuppdrag efter dödsmånaden (fall 31)**
  - *Förslag:* avräkningen prövar varje anspråk med en rättighetsmånad efter D. Anspråket ändras aldrig
    (W1), och utfallet härleds ur bankförsöken (X1):
    - *Ej betalt* betyder finansierat eller ej finansierat, avvisat eller återkommet, eller med i en
      förberedd fil. Ett sådant anspråk får en rad i `pension_claim_reversals`:
      - skulden minskar med det skuldförda beloppet;
      - kundkapitalet får tillbaka sin debitering per spår;
      - bolagskontot får tillbaka bolagsstödet och den senare finansieringen;
      - en ej finansierad rest stryks.

      Kapitalet går sedan till poolen tillsammans med resten av delens C (Y6).
    - *Skickat eller okänt* betyder att anspråket ligger i en godkänd fil. Inget återförs förrän ett
      kvitto har kommit (X8). Ett avvisat eller återkommet anspråk återförs i nästa stängning.
    - *Utfört* ger ett ärende `death_recovery` för återkravsprövning. Ärendet har brutto, skatt, netto,
      utförandedag och kvitto. Inget av följande sker:
      - en post i journalen;
      - kvittning mot dödsboets äldre anspråk;
      - negativ arvsvinst.

      En verkställd återbetalning bokas först i ett senare steg och blir då poolmedel (PR-011).
  - *Alternativ:* anspråk efter dödsmånaden står kvar som skuld tills handläggaren avgör dem. Ett annat
    alternativ är att ett utfört belopp kvittas mot dödsboets obetalda anspråk.
  - *Motivering:* ett anspråk efter dödsmånaden är ingen giltig rätt, men det raderas inte. Återföringen
    är en egen rad med motposter, på samma sätt som X9 bokar en retur. Återkrav kräver en rättslig och
    skattemässig bedömning och ett beslut av en människa. Automatisk kvittning är uttryckligen utesluten.
  - *Regel:* PR-ITP1-010, PR-ITP1-019 p. 5–6, PR-ITP1-026, PR-ITP1-028 och PR-ITP1-031.
- **Y6 Avräkningen i stängningen (fall 26–27)**
  - *Förslag:* avräkningen görs i PR-020:s steg 6, i samma verifikation `month_close` som månadens övriga
    steg. Den gäller varje uttagsdel som ännu inte är avräknad och vars ägare har ett verifierat besked med
    D senast månadens slut:
    1. Dödsmånadens rätt skuldförs som vanligt i steg 5, med bolagsstöd vid brist. En rätt som redan
       skuldförts i en tidigare stängning dras inte igen.
    2. Anspråk efter D återförs enligt Y5.
    3. Delens återstående C, efter steg 2–5 och återföringen, förs till arvsvinstpoolen.
    4. Varje gällande garantidel får en ny version med G_j = 0 och orsaken `death`. Den frigjorda
       garantin tillför inga pengar.
    5. Delens läge blir `ended` (`death`) enligt Y4, och en rad skrivs i `death_settlements`.

    Särskilda fall:
    - En premie på en del som är avräknad, eller som avräknas i månaden, hålls utanför journalen med W9:s
      mekanism. Premien ligger kvar i paket A och anges i ärendet `death_report` för manuell avräkning.
    - En person med status `deceased` men utan verifierat besked blockerar stängningen som i dag, eftersom
      dödsdagen saknas.
    - Försäkringens avslut härleds (PB10) när alla delar är avslutade, C = 0 och skulden till dödsboet är
      reglerad.
  - *Alternativ:* en egen verifikation `death_settlement` direkt vid verifieringen, på samma sätt som
    `payout_settlement`. Ett annat alternativ är att G_j lämnas oförändrad och att avslutet läses ur delens
    läge.
  - *Motivering:*
    - PR-020 lägger dödsfallsavräkningen efter avkastning, kostnader och månadsrätt och före
      poolfördelningen, i samma månad. En egen verifikation skulle ge C för en månad som inte är stängd.
    - Journalen är bolagets enda källa för G (PB4). Utan nollversionen skulle den avlidnes garanti ligga
      kvar i ΣG och i A6.
    - W9:s mekanism gör att `ledger_premiums.py` inte behöver ändras.
  - *Regel:* PR-ITP1-010, PR-ITP1-020 steg 5–6 och PR-ITP1-028. Att frigjord garanti inte tillför pengar
    följer av PR-ITP1-010 och PR-ITP1-028.
- **Y7 Arvsvinsten (fall 29)**
  - *Förslag:* PR-020 steg 7, efter avräkningen:
    - Hela poolens saldo fördelas, alltså det ingående saldot och månadens inflöde.
    - Mottagare är delar som uppfyller tre villkor:
      - delen har öppningskapital efter steg 1, alltså efter månadens delning;
      - ägaren saknar verifierat dödsfall senast månadens slut;
      - delen är inte avslutad och slutavräknas inte i månaden.

      Sparande, fribrev, uppskov, paus och pågående pension deltar. En del utan öppningskapital får
      vikten 0, så en ny medlem får arvsvinst först nästa hela månad.
    - Vikten är E_i = C_i_öppning × q_i/(1 − q_i). q_i gäller månaden och tas ur den antagna SIM-R som gäller
      för månaden (A4), med samma modellfödelsedag som i övriga beräkningar. Grundens kod och kontrollsumma
      står i sammanställningen.
    - H_i fördelas i ören med största bråkrest, och vid lika rest i delarnas id-ordning (`allocate_cents`).
      Inom delen fördelas H_i på spåren efter öppningssaldot, på samma sätt.
    - Arvsvinsten ökar C men aldrig G.
    - I tre fall står poolen kvar: när det saknas mottagare, när ΣE = 0 och när ingen SIM-R är antagen
      för månaden. Månaden stängs ändå, och ett ärende `inheritance_pool` öppnas eller fylls på, som i W8.
  - *Alternativ:* H_i läggs på delens största spår, eller poolen fördelas först i nästa månads stängning.
  - *Motivering:*
    - PR-011 kräver fördelning samma månad, öppningskapital som vikt, aktuell riskgrund och öresfördelning
      med stabil ordning.
    - Fördelningen efter öppningssaldot ger exakt delens summa, och varje spår behåller sitt ursprung.
    - En månad med ett dödsfall ger ungefär en post per kapitalspår i kollektivet. I Lakebase blir det
      omkring 15 000 poster. Det är priset för att varje öre ska gå att spåra.
  - *Regel:* PR-ITP1-011, PR-ITP1-020 steg 7 och villkoren §12.
- **Y8 Journalen**
  - *Förslag:*
    - Inget nytt slag av verifikation. Avräkningen och fördelningen är poster i `month_close`.
    - Orsakerna `pool_in` och `pool_out` finns sedan steg 2:
      - `pool_in`: minus på dödsfallsdelens spår och plus på poolen;
      - `pool_out`: minus på poolen och plus på mottagarnas spår.
    - Den nya orsaken `death_reversal` används för återföringen på skulden, kundkapitalet och bolagskontot
      (Y5). Posterna summeras per spår och orsak, så varje kombination förekommer en gång per verifikation.
    - Poolen blir ett konto som aldrig blir negativt (`ck_ledger_capital_entries_accounts`), och garantidelens
      orsak får värdet `death`.
    - Sammanställningen får avsnittet `death` med besked, avräkningar, återföringar, pool och fördelning,
      men bara när steg 7:s tabeller finns.
    - En rättelse av en månad med dödsfallsavräkning eller poolfördelning blockeras i första versionen och
      prövas manuellt. Ändrad AVK ändrar poolen och därmed varje mottagares andel.
  - *Alternativ:* rättelsen bokar nettodifferensen även på pool- och återföringsposterna. Ett annat
    alternativ är en egen orsak för dödsfallsdelens kapital till poolen.
  - *Motivering:*
    - Kapital, skuld, pool och bolagskonto blandas aldrig i samma saldo (§6.1).
    - Varje orsak syns med motsatt tecken på två konton, som `company_support` i steg 5.
    - S2:s rättelse per spår och orsak räcker inte för en fördelning som beror på hela kollektivets kapital.
  - *Regel:* PR-ITP1-011, PR-ITP1-020 och PR-ITP1-028, samt designstoppets §6.1.
- **Y9 Kontrollerna**
  - *Förslag:*
    - Den nya kontrollen *dödsfall* prövar tre saker:
      - varje verifierat besked med D senast månadens slut är avräknat en gång;
      - inget anspråk efter D har skapats i månaden;
      - kapitalet till poolen och återföringarna stämmer med posterna.
    - Den nya kontrollen *arvsvinstpool* prövar fyra saker:
      - ingående pool + inflöde − fördelat = utgående pool, och utgående pool är minst 0;
      - ΣH är lika med det fördelade;
      - antalet mottagare och ΣE redovisas;
      - G är oförändrad av fördelningen.
    - *levandestatus* räknar misstänkta besked, som godkänns, och personer med status `deceased` utan
      verifierat besked, som underkänns.
    - *kapital totalt*, *garanti totalt* och *skuld och bolagskonto* tar med poolposterna, nollversionerna
      och återföringarna.
    - Utan steg 7:s tabeller är kontrollerna och deras texter exakt som i steg 6 (B-052).
  - *Alternativ:* dödsfall och pool i en gemensam kontroll.
  - *Motivering:* acceptansen i §11 kräver två saker:
    - kundkapital, skulder, pool och bolagskonto stäms av varje månad;
    - ingen månadsrätt finns två gånger.
  - *Regel:* PR-ITP1-020 steg 8 och PR-ITP1-011.
- **Y10 Dödsboet och utbetalning till dödsboet**
  - *Förslag:*
    - `register_estate_authority` sparar dödsboets företrädare. Det kan vara en dödsbodelägare med
      fullmakt, en boutredningsman eller ett ombud. Raden har behörighetshandling, verifiering och
      beslutsfattare. Handlingen är dödsfallsintyg med släktutredning, bouppteckning eller fullmakt.
    - Företrädaren pekar på en kontoversion i `payout_accounts`. Kontot registreras med
      `register_payout_account` på den avlidnes person efter dödsdagen och verifieras mot handlingen.
    - Dödsboet får bara anspråk med rättighetsmånad senast D, aldrig återstående kapital. Anspråken betalas
      i den vanliga bankfilen, men först när delarna är avräknade och behörigheten är prövad. Annars
      blockeras personen med skälet `estate_missing`, och skulden står kvar.
    - Handläggaren registrerar skattestatus för utbetalningsåret på den avlidnes person (X5):
      - förslaget är 30 % som engångsbelopp (PR-026 p. 6);
      - ett individuellt beslut med referens går också;
      - gränserna för småbelopp (X3) tillämpas inte på dödsboet i första versionen.
    - Underlaget för kontrolluppgiften märks som dödsbo och går till projekt 6.
    - Handläggaren stänger ärendet `death_report` när dödsboets anspråk är betalda eller avgjorda.
  - *Alternativ:* ingen betalning till dödsboet i första versionen. Ärendet visar beloppen, och skulden står
    kvar (§3).
  - *Motivering:*
    - PR-010 och PR-033 ger dödsboet de redan uppkomna anspråken efter behörighets- och skatteprövning.
    - Steg 6:s konto, skatt och hashbundna bankfil återanvänds, så godkännandet förblir den externa
      handlingen.
    - Betalningen sker aldrig automatiskt. Behörighet, konto, skatt och bankfil är fyra beslut av en
      människa.
    - Om gränserna för småbelopp gäller ett dödsbo är en tolkningsfråga för projekt 4 (§13).
  - *Regel:* PR-ITP1-010 och PR-ITP1-026, där dödsbo kräver verifierad behörighet och
    skatteklassificering. Se även PR-ITP1-033 och villkoren §12.
- **Y11 Ärendetyper, operationer och befogenheter**
  - *Förslag:*
    - Fem nya operationer, alla `HUMAN_ONLY`:
      - `register_death_report`;
      - `verify_death_report`;
      - `import_death_notices`;
      - `register_estate_authority`;
      - läsningen `get_death_settlement`, som per person visar besked, avräkning, anspråk, återkrav och
        dödsbo med maskerat konto.
    - Skrivningarna tar kanal och verifierad aktör (PB12). Systemaktören och agenterna nekas verifiering,
      tillbakadragning och dödsboets behörighet, och agentrollerna får inga rättigheter på tabellerna.
    - Tre nya ärendetyper, alla utanför ärendepolicyn:
      - `death_report`: besked, avräkning, premie efter dödsfallet och dödsbo;
      - `death_recovery`: återkravsprövning (Y5);
      - `inheritance_pool`: kvarstående pool, utan person och arbetsgivare.
  - *Alternativ:* `import_death_notices` blir ett systemsteg utan människa, eller ett och samma ärende per
    person täcker både besked och återkrav.
  - *Motivering:* §10 och PR-031 kräver en människa för dödsfallsbeslut, och agenter föreslår inga sådana
    beslut. Återkrav är ett eget beslut med eget utfall och egen motpart. Poolen gäller kollektivet, på
    samma sätt som `company_capital` gäller bolaget.
  - *Regel:* PR-ITP1-031, PR-ITP1-019 p. 5, B-028, B-033 val C och PB12.
- **Y12 Tabeller och migration**
  - *Förslag:*
    - `migrate_death_reports.py` förutsätter steg 6:s migration. Den skapar de fyra tabellerna tomma och
      vidgar fem villkor:
      - `ck_cases_type`;
      - `ck_cases_subject`;
      - `ck_ledger_capital_entries_reason`;
      - `ck_ledger_capital_entries_accounts`;
      - `ck_ledger_guarantee_parts_reason`.
    - `survey.py` räknar först personer med status `deceased`. Varje sådan person behöver ett besked innan
      nästa stängning kan bokas.
    - Ordningen i Lakebase är novembers stängning och sedan migrationerna för steg 4, 5, 6 och 7. Varje
      migration görs med backup, torrkörning och eget OK. Körskripten läggs i
      `scripts/simulation/paket_b_steg7/`.
  - *Alternativ:* steg 4–7 förs in i ett enda ingrepp.
  - *Motivering:* samma mönster som X13. I Lakebase finns inget att avräkna förrän det första dödsfallet
    registreras. Det fallet blir troligen en sparare, och då behövs ingen pension, bara poolen.
  - *Regel:* B-047 punkt 10, PB13 och AGENTS.md §4.5.
- **Y13 Jämförelsen med main (B-052)**
  - *Förslag:* `scripts/simulation/paket_b_steg7/compare_main.py` kör novembers stängning med main:s kod
    och med branchens kod på samma databas. Den prövar steg 6:s fem lägen och två nya:
    - `steg6`: alla main:s tabeller och den första månadsrätten;
    - `steg6-avliden`: en person med status `deceased`.

    Utan steg 7:s tabeller ska granskningssumma, verifikation, rader, ärenden och blockering vara identiska.
    Ett regressionstest låser resultatet, och jämförelsen görs mot den main som gäller före merge.
  - *Alternativ:* bara regressionstestet.
  - *Motivering:* steg 7 ändrar `month_close.py` och journalens villkor. Novembers stängning körs med main:s
    kod, så stängningen ska vara oförändrad där dödsfallstabellerna saknas.
  - *Regel:* B-052, B-053 och X10.
- **Y14 Simulatorns dödsfallsbesked**
  - *Förslag:*
    - `death_notice_file` i `src/simulation/counterparties.py` har källan `population-register-sim`. Filen är
      folkbokföringens avisering med personnummer, dödsdag, aviseringsdag och besked-id.
    - Scenarierna gäller per person:
      - dödsfall i månaden;
      - sent besked efter betalda månader (fall 31);
      - dödsfall under paus eller på startdagen (fall 28).
    - Filen läses med `import_death_notices`. Varje besked registreras som `suspected` med källan, och
      handläggaren verifierar.
    - Samma fil igen ger ingen ny effekt, och facit hålls separat (PA8).
    - Anhörigas besked registreras manuellt och simuleras inte. Kundbegäran kommer i ett senare steg.
  - *Alternativ:* aviseringen registreras direkt som verifierad.
  - *Motivering:* X11 sköt dödsfallsbeskedet till steg 7. En fil som går genom samma operation och samma
    verifiering som ett manuellt besked prövar flödet utan en genväg.
  - *Regel:* PR-ITP1-010, B-046 PA8 och X11.

**Verifiering:** fall 26–31 verifieras lokalt. Migrationen och fall 26 och 29 verifieras hela vägen mot
`svc_test`. Jämförelsen med main enligt Y13 görs före merge.

**Utanför steg 7:**
- sen dödsfallsrättelse efter avräkningen, alltså ändrad dödsdag eller tillbakadraget verifierat besked;
- verkställt återkrav och återbetalt belopp till poolen;
- dröjsmålsränta;
- KU och AGI;
- handläggarsidan (steg 8).

**Byggt i steg 7 (2026-11-24 på branchen `claude/paket-b-steg-7-design-c61002`; mergat till main 2026-11-25, inte infört i Lakebase):**

- **Var det finns:**
  - besked, avisering, dödsbo och läsningar i `src/services/death_reports.py`;
  - avräkningen, återföringen, poolen och arvsvinsten i stängningens steg 6–7 i `src/services/month_close.py`, med kontrollerna *dödsfall* och *arvsvinstpool*;
  - dödsboets uppdrag och stoppet vid misstänkt dödsfall i `src/services/payout_orders.py`, med skatten utan småbeloppsgränser i `src/skills/calculation/payout_tax.py`;
  - de fem operationerna, alla `HUMAN_ONLY` ([tjänstelager §9.20](../../02_system/tjänstelager.md));
  - folkbokföringens avisering i `src/simulation/counterparties.py`;
  - tabellerna och migrationen `migrate_death_reports.py` ([databasschema §7g och §12](../../02_system/databasschema.md));
  - jämförelsen med main och översikten före migrationen i `scripts/simulation/paket_b_steg7/`.
- **Verifierat lokalt:** fall 26–31, dödsboets betalning, premien efter dödsfallet, Y8 och stängningen utan steg 7:s tabeller. Jämförelsen med main `df93ea2` är identisk i alla sju lägen (B-052), och regressionstestet låser main:s form per läge. Migrationen och fall 26 är verifierade mot `svc_test` (`tests/test_migration_death_reports.py`); fall 29 lokalt.
- **Preciseringar vid bygget** (inom valen):
  - ett verifierat besked med dödsdag efter månadsslutet räknas som levande i månaden; avräkningen väntar till dödsmånadens stängning;
  - en del med verifierad dödsdag i 66-månaden eller senare får standardstarten och dödsmånadens rätt; en del vars ägare dog före 66-månaden startas inte, och standardstartens hinder för avliden ägare gäller inte den (Y4);
  - kontrollen *levandestatus* räknar bara delar med avliden ägare utan verifierat besked;
  - en avräknad dels nollspår tas inte med i senare stängningar. Ett anspråk som återförs efter avräkningen (sent kvitto på ett väntande anspråk) går tillbaka till spåret och därifrån till poolen i samma stängning;
  - vid en ny granskning av en månad räknas delar som avräknats i månadens egen stängning som delar som avräknas nu, så att granskningen ser samma läge som bokningen. Rättelse med avräkning blockeras ändå (Y8);
  - poolens vikter avrundas till 10 decimaler, mottagarna tas i delarnas id-ordning och arvsvinsten fördelas inom delen efter spårens öppningskapital;
  - dödsboets skatt är den skattestatus som är registrerad på den avlidnes person; saknas den blockeras uppdraget med ärendet `tax_status` som i steg 6;
  - ett misstänkt besked ger skälet `death_suspected` utan hinderärende, och en avliden utan besked stoppas som i steg 6 (`deceased`).

## 10. Operationer, befogenheter och samordning (PB12)

| Operation | Typ | Agentnivå | Kommentar |
|---|---|---|---|
| `register_payout_request` | skrivning, PII | HUMAN_ONLY | Begäran med frist och kanal; skapar ärende |
| `preview_payout_plan` | beräkning, PII | HUMAN_ONLY | G, B, M och omräkning med granskningssumma |
| `decide_payout_plan` | skrivning, PII | HUMAN_ONLY | Hashbunden planversion; negativ rättighetsändring avgörs av människa (PR-031) |
| `split_payout_part` | skrivning, PII | HUMAN_ONLY | PR-024 |
| `register_payout_account`, `register_tax_status` | skrivning, PII | HUMAN_ONLY | Verifierade uppgifter per mottagare och år |
| `register_death_report`, `verify_death_report` | skrivning, PII | HUMAN_ONLY | Besked kan också komma som systemsteg ur simulatorns fil |
| `prepare_month_close` | beräkning | HUMAN_ONLY | Skriver inget |
| `close_policy_month` | skrivning | HUMAN_ONLY | Hashbunden; även systemsteg efter granskning |
| `create_payout_orders`, `approve_payout_order` | skrivning | HUMAN_ONLY | Godkännandet är extern handling |
| `import_payout_receipts` | skrivning | HUMAN_ONLY | Idempotent |
| `register_company_capital` | skrivning | HUMAN_ONLY | Operatören |
| `get_payout_part`, `list_pension_claims`, `get_month_close` | läsning | AGENT för aggregat utan PII, annars HUMAN_ONLY | Poddmontering prövas när ett agentuppdrag behöver dem |

Nya ärendetyper: `payout_request`, `payout_hindrance`, `death_report` och `tax_status`. *Steg 4 byggde `payout_request` och dessutom `payout_review` för systemets egna fynd vid 66 (§5.4); `payout_hindrance` och `tax_status` byggdes i steg 6 (§8.3, X5–X6), som också lade till läsningen `list_payout_orders` (X12).*
De ligger inte i ärendepolicyn och kan inte lämnas till agenten i första versionen.
Agenter föreslår inga planer, betalningar eller dödsfallsbeslut.

**Kundportalen (projekt 3)** ska använda samma operationer. Därför tar de skrivande
operationerna kanal och verifierad aktör, och läsningarna har en vy avgränsad till en
person. En aktörstyp `customer` och kundautentisering byggs i projekt 3; paket B
förbereder bara kontraktet. Prognos (PR-029) är samma beräkning som `preview_payout_plan`,
märkt som osäkert scenario.

**Samordning:**

| Projekt | Ansvar och gräns |
|---|---|
| 1 | Operationerna, ärendena och handläggarsidan *Pensioner och utbetalningar* (Digital klarhet) |
| 4 | Reglerna är godkända. Tillämpningsfrågorna i §13 (skattestatus, övergång efter 66) bekräftas där tolkningen kräver det |
| 6 | A6 läser journalen (`ledger`); aktuarien antar AVK och beräknar E_min; ekonomin tar emot skatteskuld, bolagsstöd och KU-underlag. Första kvartalsbasen 2026-12-31 kan få journalen som källa, efter eget beslut |
| 3 | Använder operationerna med kundaktör; bygger autentisering och vyer |
| 2 | Mått för utbetald pension, skuld och mottagen premie definieras där |
| 5 (pausat) | Beroende, se nedan |

**Kassaflödesgränsen mot projekt 5 – bara ett beroende.** Paket B bygger ingen
förvaltningslogik. Två gränssnitt markeras för framtiden: (1) projekt 5 ska leverera
realiserad månadsavkastning efter direkta placeringskostnader enligt PR-021; tills dess
antar aktuarien en syntetisk AVK per månad via A4 (B-042), märkt syntetisk. (2) Paket B
publicerar verkställda utbetalningar och skatt med stabil referens samt en prognos över
kommande anspråk, som projekt 5 senare kan använda för likviditet. Ingen försäljning,
order eller portföljrörelse skapas, och utflödet räknas inte två gånger när en
tillgångssida kopplas in.

### 10.1 Val för steg 8: handläggarsidan *Pensioner och utbetalningar*

**Godkända av Karl i chatten 2026-11-25 (”Godkänn alla”) enligt förslagen. Loggade som B-056 samma dag
efter Karls OK (”Logga och bygg”).** Valen preciserar B-047:s konsekvens om en ny handläggarsida och PB12. De ändrar inga
produktregler, inga operationer från steg 4–7 och inga befogenheter. Varje val har ett förslag, ett
alternativ, en motivering och en grund.

**Utgångsläge.** Steg 1–3 är införda i Lakebase. Steg 4–7 är mergade till main, men deras tabeller saknas i
Lakebase till efter novembers stängning, tidigast 2026-12-01. I demo och `svc_test` finns alla tabeller.
Sidan ska därför fungera i båda lägena. Förebilden är *Premier och betalningar* (paket A steg 7,
`src/web/routes/premium_payments.py`). Den sidan visar en notis när tabellerna saknas och svarar 409 på varje
POST. Steg 4–7 har i dag 18 operationer. Ingen av dem listar uttagsdelar eller visar en persons skattestatus och
konton. Anspråk och bankuppdrag pekar på uttagsdelens och personens interna id, inte på försäkringsnummer
eller namn.

- **Z1 Sidans plats och adresser**
  - *Förslag:*
    - En ny sida i försäkringsteamets område, `/pensioner`, i den lokala menyn bredvid *Premier och
      betalningar*. Koden ligger i `src/web/routes/pensions.py`, mallarna i `pensions_*.html` och testerna i
      `tests/test_web_pensions.py`.
    - Sidan har en översikt och fem undersidor:
      - `/pensioner`: översikten;
      - `/pensioner/forsakringar/{nr}`: pensionsakten per försäkring;
      - `/pensioner/manadsratter`: månadsrätter och skuld;
      - `/pensioner/bankfiler`: bankuppdrag och kvitton;
      - `/pensioner/dodsfall`: dödsfall och dödsbo;
      - `/pensioner/manadsstangning`: månadsstängningen.
    - Sidan följer Digital klarhet (B-034) med befintliga komponenter i `app.css` och inga egna färgvärden.
  - *Alternativ:* vyerna läggs som flikar i den befintliga översikten för en försäkrad (`/forsakrade/{pnr}`),
    och månadsstängningen läggs i operatörscentralen.
  - *Motivering:*
    - B-047 och §10 nämner en egen sida.
    - Månadsstängningen och bankfilen gäller hela kollektivet och passar därför inte i en persons översikt.
    - Enligt projekt 10 stannar enskilda godkännanden i specialistytorna. Operatörscentralen visar trender.
    - Samma mönster som *Premier och betalningar* gör sidan lätt att känna igen.
  - *Grund:* B-047, B-046 steg 7, B-034, B-036 och B-038.
- **Z2 Vyer och flöden**
  - *Förslag:* översikten och sex flöden. Varje vy visar bara det som dess steg har infört (Z9).
    1. **Översikt:** vilka steg som är införda (Z9), senast stängda och nästa öppna månad, betalningsskuld,
       skatteskuld, bolagskonto och arvsvinstpool. Dessutom öppna ärenden per typ med länk till `/arenden`
       (`payout_request`, `payout_review`, `payout_reconstruction`, `company_capital`, `payout_hindrance`,
       `tax_status`, `death_report`, `death_recovery` och `inheritance_pool`). Sidan har ett urval av
       uttagsdelar på läge och på ägare som fyller 66 inom tolv månader.
    2. **Begäran och plan** i pensionsakten:
       - delarna med läge, kapital, garanti, gällande plan och delningar;
       - formulär för en ny begäran;
       - förhandsberäkningen med G, B, M, kalender och granskningssumma;
       - beslut om planen eller delningen med summan som visades.
       
       Efter en registrerad begäran visas förhandsberäkningen direkt, så att beslutet kan fattas i samma flöde.
    3. **Månadsrätt och skuld:** anspråken per månad med brutto, del ur kapitalet, bolagsstöd, ej finansierat,
       senare finansiering och betalningsdag, samt bolagskontots saldo och insättningar. Här finns också
       formuläret för en insättning på bolagskontot.
    4. **Skatt och konto** i pensionsakten: skattestatus per år i alla versioner, konton i alla versioner med
       maskerat nummer, och formulär för en ny version av båda.
    5. **Bankuppdrag och kvitton:**
       - bankfilerna med uppdrag, skatt, netto, utförandedag, försening och bankens utfall;
       - spärrade personer med skäl;
       - formulär för att skapa filen för en betalningsdag;
       - godkännande av filen med dess kontrollsumma;
       - inläsning av bankens kvittofil.
       
       Varje anspråks försök och betalningsläge visas.
    6. **Dödsfall och dödsbo:**
       - öppna `death_report`- och `death_recovery`-ärenden;
       - inläsning av folkbokföringens avisering;
       - i pensionsakten beskeden i alla versioner, registrering, verifiering, ny dödsdag och tillbakadragning,
         avräkningen per del, återförda anspråk, återkravsärenden och dödsboets företrädare med maskerat konto.
    7. **Månadsstängningen:**
       - granskningen av en månad med alla avsnitt: sparande, plan, månadsrätt, utbetalningar, dödsfall och
         pool;
       - kontrollposterna med utfall, hindren och granskningssumman;
       - den stängda månadens versionskedja;
       - bokningen med den granskade summan (Z10).
  - *Alternativ:* en enda lång sida, eller bara läsvyer i första versionen med skrivningarna kvar i skripten.
  - *Motivering:*
    - Vyerna följer PR-020:s ordning och de sju byggstegen, så varje vy kan visas eller döljas för sig.
    - Människan ska kunna utföra varje operation från ett gränssnitt (MASTER_CONTEXT §3.7).
    - Skripten i `scripts/simulation/paket_b_steg*/` är till för Lakebase-ingreppen, inte för den löpande
      handläggningen.
  - *Grund:* B-017, PR-ITP1-020 och §7–9 ovan.
- **Z3 Skrivoperationer**
  - *Förslag:* sidan anropar fjorton befintliga skrivoperationer, alla `HUMAN_ONLY`, och inga nya:
    - `register_payout_request`, `decide_payout_plan` och `split_payout_part` (steg 4);
    - `register_company_capital` (steg 5);
    - `register_tax_status`, `register_payout_account`, `create_payout_orders`, `approve_payout_order` och
      `import_payout_receipts` (steg 6);
    - `register_death_report`, `verify_death_report`, `import_death_notices` och `register_estate_authority`
      (steg 7);
    - `close_policy_month` (steg 3).

    Granskningarna `preview_payout_plan` och `prepare_month_close` skriver inget och anropas före besluten.
    `open_capital_ledger` och AVK:s antagande ingår inte. Övergången är redan gjord, och AVK antas i
    aktuariens yta (A4). Varje skrivformulär kräver en motivering, och efter ett fel står det *Ingenting har
    ändrats* (handläggar-UI §5).
  - *Alternativ:* sidan får egna sammansatta operationer, till exempel *registrera begäran och besluta*.
  - *Motivering:* människor, skript och den senare kundportalen ska använda samma operationer (B-028,
    PB12). En sammansatt operation skulle kringgå granskningssumman mellan förhandsberäkning och beslut.
  - *Grund:* B-028, PB12, X12 och Y11.
- **Z4 Tre nya läsoperationer**
  - *Förslag:* tre läsningar, alla `HUMAN_ONLY`. De ligger i en ny modul, `src/services/operations/pension_desk.py`,
    och ändrar varken stängningen eller steg 4–7:s moduler:
    - `get_pension_status`, utan PII:
      - vilka stegs tabeller som finns, med samma prov som tjänstelagret redan använder
        (`plans_present`, `claims_present`, `orders_present`, `deaths_present` och `month_close_present`);
      - senast stängda månad;
      - antal delar per läge;
      - öppna ärenden per typ;
      - saldona för skuld, skatteskuld, bolagskonto och pool när tabellerna finns.

      Läsningen fallerar aldrig för att en tabell saknas.
    - `list_payout_parts`, med PII: uttagsdelarna med försäkringsnummer, delnummer, ägarens namn, 66-månad,
      läge och gällande plan. Den har urval och sidindelning. Sidan använder den också för att visa
      försäkringsnummer och namn i stället för interna id i anspråk och bankuppdrag.
    - `get_payout_person`, med PII: en persons skattestatus och konton i alla versioner med maskerat
      kontonummer. Läsningen är avgränsad till en person (Z12).
  - *Alternativ:* steg 4–7:s läsningar får fler fält, till exempel försäkringsnummer och namn i
    `list_pension_claims`. Ett annat alternativ är att sidan läser `get_insured_overview` en gång per person.
  - *Motivering:*
    - Att ändra steg 4–7:s utdata ändrar deras kontrakt och tester, och det ligger nära koden som B-052 skyddar.
    - En läsning per person ger lika många loggade personuppgiftsläsningar som rader på sidan.
    - Webben får bara läsa genom tjänstelagret. En ny lista byggs därför som en läsoperation med en rad i
      `access_register.yaml` (handläggar-UI §2), på samma sätt som `list_salary_files` i paket A.
  - *Grund:* B-028, handläggar-UI §2 och B-046 steg 7.
- **Z5 Aktör och kanal**
  - *Förslag:*
    - **Handläggaren** som i v1 (`Actor.human(HANDLAGGARE_ID)` med processens formulärtoken) registrerar
      underlag: begäran, planbeslut och delning, skattestatus, konto, besked, verifiering, dödsbo, avisering och
      kvittofil.
    - **Verifierad operatör** (`operator_action`, samma inloggning som aktuariens värderingar) krävs för tre
      beslut på bolagsnivå:
      - `close_policy_month`;
      - `approve_payout_order`, som är den externa handlingen;
      - `register_company_capital`, som är ägarens insättning.

      Utan inloggning visas formuläret inte, och ett POST svarar 401 utan att något ändras.
    - **Kanalen** sätts i servern, inte i webbläsaren. Handläggarens formulär sänder `manual`. Kanalen `system`
      sätts bara av operationerna för filerna (`import_death_notices`). `customer_portal` och `chatbot` nekas
      från handläggarsidan, eftersom de hör till projekt 3 och 7.
    - **Mottagningsdagen** anges i varje registrering och är förvald till dagens datum. Fristen räknas från den
      (§5.1), och sen handläggning flyttar den aldrig.
    - Ombud anges med `requester = representative` och kräver en bock för verifierad behörighet. Utan den
      stoppar operationen begäran (V8).
  - *Alternativ:* alla skrivningar med handläggaren som aktör, som på *Premier och betalningar*. Ett annat
    alternativ är att alla skrivningar kräver verifierad operatör.
  - *Motivering:*
    - En bankfil flyttar pengar (MASTER_CONTEXT §3.5).
    - Stängningen och insättningen gäller hela kollektivet och bolagets kapital (PB11).
    - Med en egen inloggning för dessa tre syns en verifierad person i loggen, inte bara konfigurationens id.
    - Övrig handläggning behåller v1:s väg, så sidan kräver ingen ny inloggning för vardagliga registreringar.
    - Kanalen i servern gör att en handläggare inte kan registrera något som om det kom från kundportalen.
  - *Grund:* MASTER_CONTEXT §3.5, PB12, S7, X7, W7 och OC-3a val H–I (operatörsinloggningen).
- **Z6 Personuppgifter**
  - *Förslag:*
    - Nya adresser bär försäkringsnummer (AL-…), aldrig personnummer. Personnumret skickas i formulärets
      POST-kropp. Det gäller också `HX-Push-Url`.
    - Översikten, månadsrätterna, bankfilerna och månadsstängningen visar försäkringsnummer, del och namn,
      inga personnummer. Personnumret visas bara i pensionsaktens sidhuvud, som på översikten för en försäkrad.
    - Kontonummer visas alltid maskerat med de fyra sista siffrorna (X6). Formuläret för konto visar aldrig
      det inskrivna numret igen efter sparandet.
    - Personuppgiftsläsningar (`get_payout_part`, `get_death_settlement`, `list_payout_parts`,
      `get_payout_person`, `list_payout_orders` och `list_pension_claims`) loggas av tjänstelagret som läsningar,
      utan resultatet.
    - Okända personnummer i en avisering visas bara på resultatsidan efter inläsningen. De sparas inte i någon
      adress.
    - Uppladdade filer sparas inte av webben. Bara operationens rader finns kvar.
    - Sidan har ingen agentpanel och skickar inga personuppgifter till en modell.
  - *Alternativ:* personnummer i adresserna som i resten av handläggar-UI:t.
  - *Motivering:*
    - Sidan samlar känsliga uppgifter: skatt, konto, dödsfall och dödsbo.
    - Handläggar-UI §2 säger redan att adresserna bör byta personnummer mot andra id. En ny sida kan börja så.
    - Minsta möjliga visning per vy följer B-006 och dataminimeringen.
  - *Grund:* B-006, handläggar-UI §2, X6 och Y11.
- **Z7 Filer från motparterna**
  - *Förslag:*
    - Bankens kvittofil (`payout_receipt_file`) och folkbokföringens avisering (`death_notice_file`) laddas upp
      som JSON i simulatorns format, med samma gräns på 5 MB och samma borttagning av `_label` som paket A.
    - Uppladdningen flyttas från `premium_payments.py` till en gemensam hjälpare, utan ändrat beteende.
    - Sidan skapar inga motpartsfiler. Simulatorn skapar dem ur beståndet (PA8), och facit hålls separat.
    - Den godkända bankfilen kan hämtas som JSON, så att den simulerade banken kan svara på den.
  - *Alternativ:* ingen nedladdning av bankfilen. Kvittofilen skapas då av simulatorn direkt ur databasen.
  - *Motivering:*
    - Samma format som operationerna gör att samma fil kan läsas av sidan, skripten och röktestet.
    - Med en nedladdning syns vad som har lämnats till banken, och det godkända innehållet går att jämföra
      med kontrollsumman.
  - *Grund:* B-046 PA8, X8, X11 och Y14.
- **Z8 Granskning före beslut**
  - *Förslag:*
    - Fyra beslut är bundna till det som visades:
      - planen och delningen till `preview_payout_plan`;
      - stängningen till `prepare_month_close`;
      - godkännandet till bankfilens kontrollsumma.

      Formuläret bär summan som en dold uppgift.
    - Har underlaget ändrats svarar operationen med konflikt. Sidan visar då 409, *Underlaget har ändrats –
      granska igen*, och en ny granskning.
    - Godkännandet av bankfilen visar antal uppdrag, summa brutto, skatt och netto, utförandedag och
      kontrollsumma. Formuläret kräver en bock för *Jag har granskat filen* (X7).
    - Ett formulär som skickas två gånger ger ingen dubbel effekt, eftersom operationerna är idempotenta.
  - *Alternativ:* sidan räknar om granskningen vid beslutet och binder den nya summan.
  - *Motivering:* B-047 och PB3, PB5 och PB8 kräver att beslutet gäller exakt det som granskades. Om summan
    räknades om vid beslutet skulle det bindningen ska skydda mot gå förlorat.
  - *Grund:* PB3, PB5, PB8, S7 och X7.
- **Z9 När steg 4–7:s tabeller saknas**
  - *Förslag:*
    - Varje vy och varje formulär hör till ett steg:
      - steg 1–3: översikten, delarna och månadsstängningen;
      - steg 4: begäran och plan;
      - steg 5: månadsrätter och bolagskonto;
      - steg 6: skatt, konto och bankfiler;
      - steg 7: dödsfall och dödsbo.

      `get_pension_status` avgör vilka steg som är införda.
    - En del som inte är införd visar en notis i stället för innehåll. Notisen säger *Inte införd i vald
      databas*, med steget, tabellerna och migrationsskriptet, och att migrationen förs in efter novembers
      stängning, tidigast 2026-12-01, med Karls OK. Formulären visas inte.
    - Ett POST till en del som inte är införd svarar 409 utan att operationen anropas. Ingenting ändras, och
      ingenting loggas, precis som på *Premier och betalningar*.
    - Notisen skiljer *inte införd* från *inga rader*. En tom lista visas aldrig när tabellen saknas.
    - Ett steg räknas som infört bara när alla dess tabeller finns. Ett delvis infört steg visas som inte infört,
      med en varning att migrationen behöver kontrolleras.
    - Om operationen ändå blockeras för att tabellerna saknas fångar sidan felet och visar notisen.
    - I Lakebase i dag syns alltså översikten, uttagsdelarna (499 delar nr 1 i `not_started`) och
      månadsstängningens granskning. Steg 4–7 visas som inte införda.
    - Sidan ändrar inte stängningens beteende (B-052):
      - `month_close.py`, `ledger_premiums.py`, `payout_orders.py` och `death_reports.py` ändras inte;
      - de nya läsningarna läser bara;
      - granskningen på sidan är samma anrop som körskriptet gör och ger därför samma granskningssumma.
  - *Alternativ:* sidan döljs helt tills alla steg är införda. Ett annat alternativ är att sidan visar fel från
    operationerna som de är.
  - *Motivering:*
    - Lakebase saknar steg 4–7 åtminstone till december, men översikten och stängningens granskning är
      användbara redan nu.
    - Notisen gör läget tydligt och pekar på nästa steg.
    - Att inga formulär visas och att varje POST svarar 409 gör att ingenting kan skrivas halvvägs.
  - *Grund:* B-052, B-053, B-054, B-055 och B-046 steg 7.
- **Z10 Månadsstängningen på sidan och Lakebase**
  - *Förslag:*
    - Granskningen och versionskedjan visas i alla databaser.
    - Bokningen (`close_policy_month`) kan göras från sidan i demo och `svc_test`.
    - I Lakebase visar sidan i stället att bokningen görs med körskriptet enligt B-050 S6. Det gäller tills Karl
      har beslutat att bokningen får göras från sidan, som ett eget val i steg 9. Spärren ligger i servern
      och följer databasvalet, inte en inställning som kan ändras i webbläsaren.
    - Skrivningarna i steg 4–7 blir tillgängliga i Lakebase först när respektive migration är införd (Z9).
      Bankfilens godkännande kräver dessutom verifierad operatör (Z5).
  - *Alternativ:* bokningen kan göras från sidan även i Lakebase, eller så är stängningen bara en läsvy överallt.
  - *Motivering:*
    - Novembers stängning är den första operativa stängningen. Ordningen backup, AVK, granskning, bokning och
      skrivskyddad kontroll är redan godkänd för skripten (S6).
    - Sidan ska inte bli en andra väg till samma första ingrepp.
    - I demo och `svc_test` behövs bokningen för att webbkontrollen ska kunna följa en hel månad.
  - *Grund:* B-050 S6–S7, B-052 och AGENTS.md §4.5.
- **Z11 Ärenden**
  - *Förslag:*
    - Paket B:s ärendetyper ligger utanför ärendepolicyn och handläggs av en människa.
    - Ärendesidan `/arenden/{nummer}` får för dessa typer en länk *Öppna i Pensioner och utbetalningar* till
      pensionsakten eller vyn. Ärenden utan person går till översikten, månadsrätterna eller stängningen.
    - Ärendet stängs som i dag med `close_case`.
    - Knappen för att starta handläggaragenten visas inte för dessa typer, eftersom de inte kan lämnas till
      agenten.
  - *Alternativ:* sidan stänger ärendena själv.
  - *Motivering:* ärendet har redan status, historik och stängning. Pensionssidan gör bara det som ärendet
    kräver, så ingen ny ärendelogik byggs.
  - *Grund:* B-033, §10, X12 och Y11.
- **Z12 Kundportalens kontrakt (projekt 3)**
  - *Förslag:*
    - Sidan använder operationerna utan logik för just sidan, så kundportalen kan senare använda samma
      operationer med en egen aktörstyp.
    - Kontraktet skrivs in i detta avsnitt när sidan byggs, och [projekt 3:s plan](../03_kundportal/PROJEKTPLAN.md)
      får en hänvisning hit. Kontraktet har en rad per operation:
      - *kund kan senare anropa*: `register_payout_request` (start, uppskov, paus, förlängning och delning),
        `register_tax_status` (bara frivilligt högre avdrag), `register_payout_account` (verifieringen görs då
        i portalen) och `preview_payout_plan` som prognos märkt som osäkert scenario (PR-ITP1-029);
      - *kund kan senare läsa, avgränsat till sig själv*: `get_payout_part`, `get_payout_person` och den egna
        delen av `list_pension_claims` och `list_payout_orders`;
      - *aldrig kund*: planbeslut, delningsbeslut, stängning, bankfil, kvitton, dödsfall, dödsbo och bolagskonto.
    - Aktörstypen `customer`, kundautentisering och avgränsningen till en person byggs i projekt 3. Steg 8
      bygger dem inte.
  - *Alternativ:* aktörstypen `customer` och en läsning per person med kundens egen avgränsning byggs redan nu.
  - *Motivering:*
    - PB12 kräver bara att kontraktet förbereds.
    - Kundautentisering är ett eget säkerhetsbeslut.
    - Med en tabell per operation vet projekt 3 vad det kan bygga på utan att läsa koden.
  - *Grund:* PB12, B-020, §10 och PR-ITP1-029.
- **Z13 Webbkontrollen**
  - *Förslag:* två delar.
    - **Automatiska prov** i `tests/test_web_pensions.py` med testklienten mot SQLite:
      - varje vy visas;
      - varje formulär anropar rätt operation med rätt aktör och kanal, och kanalen `customer_portal` nekas;
      - formulärtoken och operatörsinloggningen prövas;
      - konflikt vid ändrad summa ger 409;
      - fel visas med *Ingenting har ändrats*;
      - schemat utan steg 4–7:s tabeller, och med bara steg 4, 5 eller 6: varje sida svarar 200 med notisen,
        varje POST svarar 409, och inga rader eller händelser skrivs;
      - inget personnummer i nya adresser, `HX-Push-Url` eller listvyer, och inget omaskerat kontonummer i
        någon HTML;
      - de befintliga gränsproven (`test_webbkoden_ror_varken_modeller_eller_sessioner` och designproven) är
        gröna;
      - de nya läsningarna prövas också mot Postgres (`--postgres`, B-040).
    - **Kontroll i webbläsaren** i en lokal databas, startad som `handlaggare-ui-demo` i `.claude/launch.json`:
      - affärsdagen sätts med tjänstelagrets `business_day`, samma klocka som paket C:s månadssimulator (S-01).
        En mellanprogramvara i webben sätter dagen för varje anrop;
      - `start_ui.py` får flaggan `--affarsdag` och kan öppna en kopia av paket C:s frysta startbild för
        pensionsprovet (`premium_calendar.py start partial --pension`). Båda godtas bara för lokala databaser,
        aldrig för `lakebase`, och sidhuvudet visar *Simulerad affärsdag*;
      - kontrollen följer paket C:s pensionsprov genom sidan i stället för skripten:
        - den 1 december: novembers stängning;
        - den 15 december: insättningen på bolagskontot, kontot, skattestatusen för 2027 och aviseringen, och
          sedan verifieringen av beskedet;
        - den 4 januari 2027: decembers stängning med standardstarten, avräkningen och arvsvinsten, och sedan
          bankfilen, godkännandet och kvittot;
      - utfallet jämförs med paket C:s öresfacit: brutto 2 040,07 kr, skatt 612,00 kr, netto 1 428,07 kr,
        pool 22 817,23 kr och arvsvinst 44,49 kr och 22 772,74 kr;
      - dessutom prövas fall 23 (avvisning och nytt försök), fall 30 (misstänkt dödsfall) och samma kvittofil
        två gånger;
      - kontrollen görs en gång med steg 4–7:s tabeller borttagna, som i `compare_main.py`, och då ska sidan
        visa notiserna;
      - skärmbilder och utfall skrivs i `scripts/simulation/paket_b_steg8/RAPPORT.md`.
    - **Ingen kontakt med Lakebase i steg 8.** Att öppna sidan mot Lakebase är bara läsning, men det görs
      först i steg 9 efter Karls OK.
  - *Alternativ:* bara automatiska prov, eller en egen kedja för webbkontrollen i stället för paket C:s prov.
  - *Motivering:*
    - Ett facit som redan är verifierat två gånger gör kontrollen oberoende av sidans egen kod.
    - Den gemensamma klockan finns redan (S-01). Paket A:s webbkontroll satte dagen med ett eget lokalt
      startskript, och det behövs inte nu.
    - Att ta bort tabellerna prövar exakt Lakebases läge före migrationerna utan att röra Lakebase.
  - *Grund:* B-040, B-046 steg 7, B-052 och projektets teststrategi.
- **Z14 Befogenheter, dokumentation och merge**
  - *Förslag:*
    - **Befogenheter:** de tre nya läsningarna är `HUMAN_ONLY`. Inga agentroller får rättigheter, och sidan
      monteras inte i någon agentpodd.
    - **Dokumentation:** sidan beskrivs i handläggar-UI §4 och läsningarna i tjänstelager §9.21.
      `tjänstelager_operationer.md` genereras om. Databasschemat ändras inte, eftersom steg 8 inte inför några
      tabeller.
    - **Jämförelse före merge:** `paket_b_steg7/compare_main.py` körs på branchen och ska vara identisk med
      main i alla sju lägen. Hela sviten körs.
    - **Merge** till main görs efter Karls OK. Byggordningens steg 9 (Lakebase) påverkas inte.
  - *Alternativ:* `get_pension_status` får nivån `AGENT`, eftersom den saknar PII (§10).
  - *Motivering:*
    - §10 säger att poddmontering prövas när ett agentuppdrag behöver läsningen. Inget sådant uppdrag finns.
    - Jämförelsen visar att B-052 fortfarande gäller efter bygget.
  - *Grund:* PB12, B-040, B-048 och B-052.

**Verifiering:** proven och webbkontrollen enligt Z13 och jämförelsen enligt Z14.

**Utanför steg 8:**
- Lakebase och bokningen från sidan i Lakebase (steg 9, Z10);
- kundportalens aktörstyp och autentisering (projekt 3);
- skattetabellen för huvudinkomst (X4);
- dröjsmålsränta, verkställt återkrav, KU och AGI;
- agentuppdrag för `payout_request`-ärenden (§13);
- flytten av sidan till operatörscentralen.

**Byggt i steg 8 (2026-11-25, mergat till main 2026-11-26; rör inte Lakebase):**

- **Var det finns:**
  - sidan i `src/web/routes/pensions.py` och mallarna `src/web/templates/pensions*.html` ([handläggar-UI §4](../../02_system/handläggar-ui.md#4-sidor));
  - de tre läsningarna i `src/services/pension_desk.py` och `src/services/operations/pension_desk.py`, alla `HUMAN_ONLY` ([tjänstelager §9.21](../../02_system/tjänstelager.md));
  - den simulerade affärsdagen i `src/simulation/business_day.py` och `src/web/__main__.py`;
  - webbkontrollen och rapporten i `scripts/simulation/paket_b_steg8/`.
- **Verifierat lokalt:**
  - `tests/test_pension_desk.py` och `tests/test_web_pensions.py`;
  - webbkontrollen enligt Z13: paket C:s pensionsscenario dag för dag genom sidan på en SQLite-kopia. Utfallet är facit på öret, och varje verifikations kontrollsumma är densamma som i CLI-körningen;
  - passet utan steg 4–7:s tabeller;
  - jämförelsen med main `895da08` enligt Z14, som är identisk i alla sju lägen ([rapporten](../../scripts/simulation/paket_b_steg8/RAPPORT.md)).
- **Preciseringar vid bygget** (inom valen):
  - bankfilen hämtas genom ett nytt godkännande med samma kontrollsumma, som ger filen utan ny effekt, och skickas som JSON-bilaga. Kontonumret finns därmed aldrig i sidans HTML;
  - `get_payout_person` tar inte med kontots verifieringsreferens, eftersom den kan bära kontonumret;
  - ett POST mot ett steg som inte är infört svarar 409 innan motiveringen prövas och utan något anrop;
  - kvittobeskedet räknar nya ärenden om konto och skiljer avvisade kvitton från utförda.

**Kundportalens kontrakt (Z12).** Sidan anropar operationerna utan egen logik. Aktörstypen `customer`,
kundautentiseringen och avgränsningen till en person byggs i [projekt 3](../03_kundportal/PROJEKTPLAN.md).

| Operation | Kunden senare | Villkor |
|---|---|---|
| `register_payout_request` | Anropar | Start, uppskov, paus, förlängning och delning, i kanalen `customer_portal` |
| `register_tax_status` | Anropar | Bara frivilligt högre avdrag |
| `register_payout_account` | Anropar | Verifieringen görs i portalen |
| `preview_payout_plan` | Anropar | Som prognos märkt som osäkert scenario (PR-ITP1-029) |
| `get_payout_part`, `get_payout_person` | Läser | Bara sig själv |
| `list_pension_claims`, `list_payout_orders` | Läser | Bara den egna delen |
| `decide_payout_plan`, `split_payout_part` | Aldrig | Plan- och delningsbeslut fattas av handläggaren |
| `prepare_month_close`, `close_policy_month`, `get_month_close` | Aldrig | Stängningen |
| `create_payout_orders`, `approve_payout_order`, `import_payout_receipts` | Aldrig | Bankfil och kvitton |
| `register_death_report`, `verify_death_report`, `import_death_notices`, `register_estate_authority`, `get_death_settlement` | Aldrig | Dödsfall och dödsbo |
| `register_company_capital` | Aldrig | Bolagskontot |
| `get_pension_status`, `list_payout_parts` | Aldrig | Bolagsövergripande |

## 11. Verifieringsfall

Beloppen följer produktreglernas kontrollfall och 2026 års parametrar (avgift 0,20 %,
skattebelastning 0,354 %). A-faktorer märkta *syntetisk* är räkneexempel, inte SIM-B
eller SIM-G. Bankdagar är kontrollerade med `bank_calendar`.

| # | Fall | Väntat utfall |
|---|---|---|
| 1 | Fyller 66 i november 2026, inget val, verifierad status | Standardplan livsvarig; november 2026 är första rätt; betalning 2026-12-01 (PR-025) |
| 2 | Uppskov från 66 till 72, i tid | Godkänns utan maxålder; ingen rätt för mellanliggande månader; kapitalet förvaltas (PR-003) |
| 3 | Begäran om start i december inkommer 2026-12-01 | Sen: förslag januari 2027, planen ändras först efter kundens bekräftelse |
| 4 | Tidsbegränsad N = 60 från november 2026; N = 59 | Sista rätt oktober 2031; N = 59 avslås (PR-006) |
| 5 | Paus november 2027–januari 2028 efter 12 av 60 | Återstart februari 2028, 48 kvar, sista rätt januari 2032 (PR-004–006) |
| 6 | Förlängning 12 av 60 till 120; 60 av 60 förbrukade | 108 kvar; det senare avslås som för sent (PR-007) |
| 7 | Deluttag 30/70 av C = 100 000,00; ny del 5 %; fjärde del | 30 000,00 och 70 000,00 med G proportionellt; 5 % och fjärde del avslås (PR-024) |
| 8 | Begäran om uttag före 66 | Blockeras med ärende i första versionen (PB1) |
| 9 | G = 100, B = 130; G = 100, B = 80 | M = 130, inte 230; M = 100 (PR-009) |
| 10 | Livsvarig, tidigare M = 130, rätt nr 20, ny B = 120 | Behåll 130; tidsbegränsad del med samma siffror ger 120 (PR-009) |
| 11 | ΣG_j = 123,4567, B lägre | M = 123,46, golvet avrundat uppåt (PR-009) |
| 12 | Uppskov, G_j = 10, A_gammal = 200, A_ny = 160 (syntetisk) | V_j = 2 000, G_j_ny = 12,5 på samma historiska grund (PR-008) |
| 13 | C0 = 100 000,00, r = 1 %, inga premier eller uttag | +1 000,00, −16,67, −29,50; C1 = 100 953,83 (PR-020) |
| 14 | Som 13 med månadsrätt 500,00 | Skuld 500,00, C1 = 100 453,83; en debit även om betalningen senare misslyckas |
| 15 | Premie 1 000,00 under pågående pension | Garanti på ej startad del med egen referensplan; ingen avkastning denna månad; den pågående delens belopp ändras inte (PR-025) |
| 16 | Samma stängning igen; ändrad källa efter stängning | Samma resultat utan nya poster; ändringen ger ny version med motposter |
| 17 | Ingen antagen AVK för månaden | Stängningen blockeras; inga anspråk eller betalningar |
| 18 | Brutto 1 000,00, sidoinkomst | Skatt 300, netto 700,00, kapitaldebit 1 000,00 (PR-026) |
| 19 | Brutto 333,33, sidoinkomst | 30 % = 99,999; skatt 99 kr, netto 234,33 |
| 20 | Brutto 99,99; brutto 100,00 med förväntad årssumma 1 200 | Inget avdrag; 30 kr i avdrag (gränserna är strikt mindre än) |
| 21 | Rätt för december 2026, huvudinkomst, betalning 2027-01-04 | 2027 års regler; utan 2027 års tabellparameter blockeras betalningen med skulden kvar |
| 22 | Saknat konto vid 66 | Rätten skuldförs, ingen betalning, ärende; inget uppskov (PR-025, PR-026) |
| 23 | Bankavvisning och nytt försök | En bruttopost, en lyckad nettobetalning och en skatteredovisning |
| 24 | Okänt bankutfall | Inget nytt försök före avstämning |
| 25 | Samma bankkvitto två gånger | Ingen ny effekt; samma id med ändrat innehåll ger konflikt |
| 26 | C = 1 000, obetald dödsmånadsrätt 100 ej debiterad; redan debiterad och C = 900 | Skuld 100 och pool 900; pool 900, inte 800 (PR-010) |
| 27 | C = 80, giltig rätt 100 vid dödsfall | Bolagsstöd 20, pool 0 (PR-010, PR-028) |
| 28 | Dödsfall under paus; dödsfall på startdagen | Ingen dödsmånadsrätt; en hel månadsrätt, därefter avslut |
| 29 | Pool 90, samma q, kapital 1 000 och 2 000; pool 0,02 på tre lika vikter | 30 och 60; 0,01, 0,01 och 0,00 efter id-ordning (PR-011) |
| 30 | Misstänkt dödsfall | Nya bankuppdrag stoppas; inga rättigheter raderas |
| 31 | Verifierat dödsdatum före redan betalda månader | Ärende för återkravsprövning; ingen kvittning, ingen negativ arvsvinst (PR-019 p. 5–6) |
| 32 | Sista rätt, M = 100, C = 140 | Slutbelopp 140, C = 0, delen `ended` (PR-027) |
| 33 | Sista rätt, M = 100, C = 80 | Bolagsstöd 20, skuld 100, C = 0 |
| 34 | Banken avvisar sista beloppet | Delen avslutad i rättighetshänseende, hela skulden kvar |
| 35 | C = 80, rätt 100, bolagskonto 0 | Anspråket ej finansierat, körningen ekonomiskt blockerad, eskalering, ingen lyckad betalning (PR-028) |
| 36 | Övergång från S-04 per 2026-10-31 | C 42 087 223,57 kr och G 119 195,6502916268 kr/mån bevarade, varje försäkring exakt i ören |
| 37 | Novemberstängning med paket A:s allokeringar | 51 623,90 kr tillförs som premie vid månadsslut, varav SvenskIndustries delbetalning 15 362,24 kr; avstämningskontots 36 261,66 kr ger ingen effekt |
| 38 | Fribrev under pågående pension | `set_policy_paid_up` stänger premieförloppet; uttagsdelens pension fortsätter oförändrad |

Acceptans för hela leveransen:
- Summan av kapitalspår är alltid lika med delens C, och ingen del har negativt C.
- Kundkapital + betalningsskuld + skatteskuld + pool + bolagskonto stäms av mot
  journalens rörelser varje månad, med bankens utflöde mot verkställda uppdrag.
- Varje månadsrätt finns en gång per del och månad; varje bankförsök pekar på den.
- Varje belopp går att spåra till plan, beslut, grund, parameter och källa.
- Inget fall ger dubbel ekonomisk effekt, och ett avslag eller en blockering räknas
  som lyckat utfall när regeln kräver det.

## 12. Lakebase

Inget i detta designstopp skriver till Lakebase. När ett steg är verifierat lokalt och i `svc_test`:

1. Backup och torrkörning av stegets migration. Bekräfta att ingen annan agent kör
   mot databasen (AGENTS.md §4.5).
2. Efter separat OK: skapa tabellerna tomma och kontrollera att övriga radantal är oförändrade.
3. Efter ytterligare OK: övergången från S-04 per 2026-10-31 och därefter
   novemberstängningen, med en AVK för november som Karl antagit i A4. Kontrollera
   fall 13, 16, 36 och 37 i skrivskyddad läsning.
4. Pensionsfallen i Lakebase kräver ett testbestånd med personer från 66 år. Den äldre
   kohorten (B-035 val K) eller ett märkt testfall införs bara efter eget beslut, eftersom
   det också ändrar S-04 och FTA-underlaget.

Agentrollerna får inga rättigheter på de nya tabellerna i första versionen. Undantag: uttagsdelarna i steg 1, där `agent_forsakring` och `agent_aktuarie` får SELECT (B-048).

### 12.1 Val för steg 9: nytt startläge med pensionärer

**Godkända av Karl i chatten 2026-11-28 (”Godkänn alla”) enligt förslagen. Loggade som **B-057** samma dag efter Karls OK (”Logga och bygg”).** Valen preciserar §12 punkt 3–4 och steg 9 i
byggordningen. De ändrar inga produktregler. Varje val har ett förslag, ett alternativ, en motivering och en grund.

**Utgångsläge.**
- Lakebase har ingen som har passerat 66 eller fyller 66 de närmaste åren. Pensionsflödet i steg 4–8 har därför
  inget att arbeta med där.
- Journalens ingående läge per 2026-10-31 är bokat sedan 2026-11-15: 492 försäkringar och 15 097 garantidelar ur
  S-04 med den frysta utdragshashen `023946…3fefa`. Ingen månad är stängd efter det, så ingenting i journalen
  bygger ännu på startläget.
- S-04 räknar inte fram påbörjade uttag. Försäkringar i utbetalning blir *ej beräknade*
  (`valuation_extract.NOT_CALCULATED`), och journalen tar emot ett enda ingående läge. En ändring blir en länkad
  rättelse, inte en ny övergång (`capital_ledger.apply_opening`).
- Demobeståndet har redan en äldre kohort (B-035 val K): 31 personer födda 1959–1962 (`OLDER_COHORT`), och en
  pensionär, David Dahl, med uttag sedan 2024-05. Ingen av dem finns i Lakebase.
- Karl 2026-11-28: bolaget är i byggfas, och bokföringen behöver stämma först när bolaget går live. Historiken
  behöver inte rekonstrueras, men startläget ska hänga ihop.

- **Q1 Vilka som läggs till**
  - *Förslag:*
    - Den äldre kohorten enligt `OLDER_COHORT`, 31 personer:
      - de 7 födda 1959–1960 fyllde 66 mellan maj 2025 och juli 2026 utan registrerat val och ger var sitt ärende
        `payout_review` (V6). Handläggaren registrerar deras begäran och plan;
      - de 24 födda 1961–1962 får standardstart (V4) i 66-årsmånaden, från februari 2027.
    - Dessutom 4 pensionärer med pågående uttag sedan 2024–2026, varav en är demobeståndets David Dahl.
      Planerna blandas: livsvarig och tidsbegränsad, en med delning på två delar.
  - *Alternativ:* bara kohorten. Då uppstår de första pensionerna när handläggaren beslutar planer för de sju
    som passerat 66, och genom standardstarter från februari 2027.
  - *Motivering:* pågående uttag visar en löpande utbetalningsmånad redan i december. Kohorten visar flödet in i
    pension, med ärenden, planer och standardstarter.
  - *Grund:* B-035 val K och §12 punkt 4.

- **Q2 Anställning och premier**
  - *Förslag:* alla som läggs till har fribrev från en tidigare anställning med registrerat anställningsslut, och
    ingen betalar premie efter 2026-10-31. Det gäller även kohorten.
  - *Alternativ:* kohorten födda 1961–1962 som aktiva och premiebetalande, enligt val K.
  - *Motivering:*
    - Aktiva personer måste finnas i arbetsgivarnas löneunderlagsfiler för november. Annars ger paket A ärenden
      om saknade rader.
    - Fribrev håller paket A:s period 2026-11 oförändrad.
    - Kohortens premieanalys (3c-B) körs fortsatt i demobeståndet. I Lakebase visar den att ingen berörs på flera år.
  - *Grund:* B-046 och PA-flödet; val K gäller demobeståndet.

- **Q3 Kapital och garantier utan historik**
  - *Förslag:*
    - Startvärdena för de nya försäkringarna deklareras i stället för att rekonstrueras ur premiehistorik:
      - kapital C per 2026-10-31;
      - garantidelar på SIM-G med deklarerat belopp och grund;
      - för pågående uttag beslutad plan, startmånad och redan utbetalt.
    - Värdena väljs så att pensionerna blir realistiska: kapital 300 000–1 500 000 kr, ungefär 1 500–7 000 kr
      i månaden.
    - Källan märks `declared_opening` i verifikationens innehåll, med hänvisning till beslutet.
    - De 492 befintliga försäkringarna behåller exakt sina värden ur S-04.
  - *Alternativ:* generera premiehistorik från anställningsstart och låta S-04 rekonstruera. Det kräver
    PR-009-rekonstruktion av utbetalt kapital för pågående uttag, ett eget och större bygge.
  - *Motivering:* Karls besked om byggfasen. Deklarerade startvärden är ett vanligt sätt att flytta in ett
    bestånd, och de går att granska som en lista.
  - *Grund:* B-047 punkt 2 (S-04 som märkt ingående läge). Valet utvidgar den punkten och behöver loggas.

- **Q4 Hur det nya startläget kommer in**
  - *Förslag:*
    - Journalens ingående läge ersätts i Lakebase innan någon månad har stängts: backup, töm journalens
      tabeller (steg 2) och boka ett nytt ingående läge med S-04-delen och den deklarerade delen.
    - Den första verifikationen bevaras i backupen och i en körlogg, inte i journalen.
  - *Alternativ:* en länkad rättelseverifikation som lägger till de nya försäkringarna och bevarar den första
    verifikationen i journalen.
  - *Motivering:* ingen stängning bygger på startläget än. En ren omstart blir enklare att granska, och journalen
    börjar med ett enda sammanhängande läge.
  - *Grund:* §6.2 och Karls besked om byggfasen. Valet är ett avsteg från idempotensregeln för startläget och
    gäller bara före första stängningen.

- **Q5 Ordningen i Lakebase**
  - *Förslag:*
    1. backup;
    2. migrationerna för steg 4, 5, 6 och 7;
    3. de nya personerna, försäkringarna, uttagsdelarna och planerna;
    4. det nya ingående läget;
    5. novembers AVK och novembers stängning;
    6. bolagsinsättningen (Q6) och decembers AVK;
    7. decembers stängning i början av januari, med de första månadsrätterna, och bankfilen.

    Varje punkt kräver Karls separata OK.
  - *Alternativ:* novembers stängning först, sedan migrationerna och därefter startläget som en länkad rättelse
    per 2026-11-30.
  - *Motivering:*
    - Pensionärernas planer kräver steg 4:s tabeller.
    - Startläget bör vara på plats innan novembers stängning bygger på det.
    - Jämförelsen med main (B-052) visar redan att stängningen blir densamma med steg 4–7:s tabeller.
  - *Grund:* ersätter spärren ”migrationerna tidigast efter novembers stängning” (B-052, Y12). Påminnelsen
    2026-12-01 kör bara granskningar och påverkas inte.

- **Q6 Bolagskapital före första utbetalningen**
  - *Förslag:*
    - En provisorisk insättning före decembers stängning: 24 gånger summan av decembers månadsbelopp, avrundat
      uppåt till hela 10 000 kr.
    - Dokumentreferensen anger byggfas och att E_min enligt PR-028 räknas av aktuarien (A8) före live.
  - *Alternativ:* bygg aktuariens beräkning av E_min först och sätt in minst E_min.
  - *Motivering:*
    - Likviditetsdelen av E_min är 12 × ΣM.
    - Stressgapet kan inte räknas förrän A8 finns. Dubbel likviditetsdel ger marginal utan att vänta på A8.
  - *Grund:* PR-028. Valet är ett uttalat avsteg under byggfasen.

- **Q7 Skatt för de första utbetalningarna**
  - *Förslag:*
    - Pensionärerna i Lakebase får skattestatus sidoinkomst 30 % eller ett individuellt beslut. Fördelningen är
      blandad, så att båda vägarna syns.
    - Huvudinkomst med tabell byggs som ett eget steg med Skatteverkets textfil för 2026 och tabellerna för
      2027, inklusive den nya kolumnen för personer födda 1960.
  - *Alternativ:* vänta med de första utbetalningarna tills tabellsteget är byggt.
  - *Motivering:* decembers pension betalas 2027-01-04 och kräver 2027 års tabeller. De är inte publicerade
    2026-11-28.
  - *Grund:* X4 och PR-026.

- **Q8 Dödsbo**
  - *Förslag:* ingen pensionär i startläget är avliden. Dödsfallsflödet provas i paket C:s simulering och, efter
    eget OK, med en simulerad avisering för en pensionär i Lakebase.
  - *Alternativ:* en avliden pensionär redan i startläget.
  - *Motivering:* ett dödsfall i Lakebase bör vara en egen, granskad händelse.
  - *Grund:* Y12.

- **Q9 Agenter**
  - *Förslag:* oförändrat. Agentrollerna får inga nya rättigheter, och agenten startas inte i pensionsärenden
    (Z11).
  - *Alternativ:* låt handläggaragenten förbereda `payout_review`-ärendena för de tre födda 1959.
  - *Motivering:* det kräver en egen ärendepolicy, som B-043.
  - *Grund:* §13.

- **Q10 Verifiering före Lakebase**
  - *Förslag:*
    - Steget byggs och provas lokalt och i `svc_test` med samma ordning som Q5.
    - Kontrollerna är fyra:
      - de 492 försäkringarnas startvärden är oförändrade, per försäkring;
      - de nya försäkringarna stämmer mot den deklarerade listan;
      - novembers stängning går igenom;
      - decembers stängning och bankfil ger ett facit räknat oberoende av koden.
    - Skript och rapport läggs i `scripts/simulation/paket_b_steg9/`.
  - *Alternativ:* prova bara på en kopia av Lakebase-backupen.
  - *Motivering:* samma verifieringsordning som steg 1–7.
  - *Grund:* B-040 och AGENTS.md §4.5.

### Föreslagen byggordning (PB13)

Ett bygge i taget. Varje steg ska vara testat och fungera innan nästa börjar.

| Steg | Innehåll | Fall |
|---|---|---|
| 0 | Karl tar ställning till PB1–PB13. *Klart 2026-11-14: alla godkända* | – |
| 1 | Uttagsdel och tre förlopp, övergång av `policy_states`, anpassade läsare och `set_policy_paid_up`. *Byggt och infört i Lakebase 2026-11-14 (§4): 499 delar nr 1, inga uttag att flytta; agentrollernas läsrätt enligt B-048* | 38 |
| 2 | Operativ kapital- och garantijournal, övergång från S-04, paket A som premiekälla och A6-adapter (`ledger`). *Byggt 2026-11-14 (§6), verifierat lokalt, mot `svc_test` och på en kopia av Lakebase-backupen. Infört i Lakebase 2026-11-15: tabellerna och det ingående läget per 2026-10-31 (492 försäkringar, 15 097 garantidelar); `verify.py` 16 av 16* | 36, 37 |
| 3 | Månadsstängning steg 1–4 och 8 för sparandet, med granskning och rättelseversion. **Första leverans med nytta i Lakebase.** *Byggt 2026-11-19 (§7, val S1–S7), verifierat lokalt och mot `svc_test`; körskript i `scripts/simulation/paket_b_steg3/`. Migrationen införd i Lakebase 2026-11-19 (B-050); novembers AVK och stängning tidigast 2026-12-01* | 13, 15–17 |
| 4 | Begäran, plan, beslut, belopp, standardstart och delning. *Byggt 2026-11-21 (§5.4, val V1–V11), verifierat lokalt och mot `svc_test`; körskript i `scripts/simulation/paket_b_steg4/`. Mergat till main 2026-11-22 (B-052). Inte infört i Lakebase; migrationen tidigast efter novembers stängning (2026-12-01)* | 1–12 |
| 5 | Månadsrätt och skuld (steg 5) samt bolagskonto och bolagsstöd. *Byggt 2026-11-22 (§5.5, val W1–W12, B-053), verifierat lokalt och mot `svc_test`, med slutavräkningen (W6); körskript i `scripts/simulation/paket_b_steg5/`. Mergat till main 2026-11-23. Inte infört i Lakebase; migrationen efter steg 4:s* | 1, 5, 6, 14, 32, 33, 35 |
| 6 | Skattestatus, konto, bankuppdrag, godkännande, kvitton och simulatorns utbetalningssida. *Valen X1–X13 godkända 2026-11-24 (§8.3); byggt samma dag, verifierat lokalt och mot `svc_test`; körskript i `scripts/simulation/paket_b_steg6/`. Mergat till main 2026-11-24. Inte infört i Lakebase; migrationen efter steg 5:s* | 18–25, 34 |
| 7 | Dödsfall och arvsvinst (steg 6–7); slutavräkningen byggs i steg 5 (W6) och fall 34 i steg 6. *Valen Y1–Y14 godkända 2026-11-24 (§9.1, B-055); byggt samma dag, verifierat lokalt och mot `svc_test`; körskript i `scripts/simulation/paket_b_steg7/`. Mergat till main 2026-11-25. Inte infört i Lakebase; migrationen efter steg 6:s* | 26–31 |
| 8 | Handläggarsidan *Pensioner och utbetalningar* med webbkontroll. *Valen Z1–Z14 godkända 2026-11-25 (§10.1, B-056); byggt samma dag med webbkontroll mot paket C, körskript i `scripts/simulation/paket_b_steg8/`. Mergat till main 2026-11-26. Rör inte Lakebase; sidan visar notiser för steg 4–7 tills deras migrationer är körda* | – |
| 9 | Lakebase enligt ovan, med separat OK för varje ingrepp. *Nytt startläge med pensionärer: valen Q1–Q10 i §12.1 godkända 2026-11-28; bygget inte påbörjat* | – |

Postgres-prov körs där ändringen kräver det (B-040). Steg 1–2 delar datamodell med allt
som följer och får inte delas mellan Claude och Codex utan avstämning (AGENTS.md §4.2).
Steg 6 kan byggas parallellt med steg 7 först när anspråkskontraktet i steg 5 är fastställt.

## 13. Öppna frågor och föreslagen beslutsloggspost

**Frågor där Karls svar kan ändra designen:**

- **Personer som passerat 66 utan registrerat val före 2026-11-01** (finns i demobeståndets
  kohort): förslag ärende per person och plan med kundens bekräftelse, inga automatiskt
  retroaktiva rättigheter. Alternativ: standardstart från 2026-11 eller retroaktiv start
  från 66-årsmånaden enligt PR-025:s *beräknas tillbaka*.
  *Avgjord 2026-11-21 (V6, §5.4): ärende `payout_review` per person, plan efter kundens begäran.*
- **Huvudinkomst med skattetabell:** ska en versionsbunden tabell för 2026 och 2027 läggas
  in som parameter från Skatteverkets källa, som Karl hämtar? Utan den kan bara sidoinkomst
  och individuella beslut betalas ut.
  *Avgjord 2026-11-24 (X4, §8.3): huvudinkomst registreras men blockerar med ärende tills tabellen byggs som
  eget steg, efter att Karl hämtat Skatteverkets tabeller för 2026 och 2027.*
- **AVK för november och december 2026:** antar Karl syntetiska versioner i A4 för den
  operativa stängningen, som i P6-MANAD-001 (+0,20 % i november)? Det är beroendet mot projekt 5.
  *November avgjord 2026-11-19 (S5, §7.2): AVK-SIM-2026-02 enligt P6-MANAD-001 D5. December står öppen.*
- **Bolagskapitalets startinsättning:** beloppet bestäms med aktuariens E_min. För dagens
  bestånd utan pågående pension är likviditetsdelen noll; stressgapet återstår att räkna.
- **Skatt vid utbetalning till dödsbo (Y10):** gäller gränserna för småbelopp, 100 och 1 000 kr, när
  pensionen betalas till ett dödsbo? Förslaget i steg 7 är att de inte tillämpas och att avdraget blir 30 %
  som engångsbelopp, om inget individuellt beslut finns. Projekt 4 bekräftar tolkningen.
- **Agentens roll:** handläggaragenten kan senare förbereda `payout_request`-ärenden. Det
  kräver eget beslut om ärendepolicyn, som B-043 för löneunderlag.

**Post i `BESLUTSLOGG.md`:** införd som B-047 efter Karls OK 2026-11-14. Förslaget nedan bevaras som underlag; den införda posten är utförligare.

> **B-047 | 2026-11-14 | Paket B: pensions- och månadsavräkning**
> Operatören godkände designstoppet P1-PENSION-001 med valen PB1–PB13 enligt
> rekommendationerna i chatten 2026-11-14: ”Godkänn alla”. (1) Uttagsdel under
> förmånen med tre oberoende förlopp; `policy_states` bär bara premieförloppet. (2) En
> operativ kapital- och garantijournal med S-04 per 2026-10-31 som märkt ingående läge och
> paket A:s allokeringar som enda premiekälla; P6-MANAD-001 förblir scenarioverktyg och A6
> läser journalen som `ledger`. (3) Månadsstängning för hela kollektivet i PR-020:s ordning,
> hashbunden och `HUMAN_ONLY`. (4) Ett bruttoanspråk per del och månad, skatt vid
> utbetalningsdagen, bankuppdrag med mänskligt godkännande och idempotenta kvitton.
> (5) Dödsfall, arvsvinst och slutavräkning i stängningen; `terminate_policy` utgår som
> egen operation. (6) Bolagskonto med dokumenterad startinsättning och bolagsstöd enligt
> PR-028. (7) Tidigt uttag före 66, återtag och återbetalning är senare steg. (8) Projekt 5
> är fortsatt pausat; AVK antas av aktuarien tills en avkastningsleverans finns.
> **Preciserar:** B-022 (lägen), B-027 (garanti), B-028 (tjänstelagret), B-030 p. 2 och 4,
> B-031 (PR-002–011, 020–028), B-042 (källan `ledger`) och B-046 PA7.
