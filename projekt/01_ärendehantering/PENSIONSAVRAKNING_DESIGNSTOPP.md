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

**Byggt 2026-11-22 på branchen `claude/paket-b-steg-5-manadsr-e22262`; inte mergat till main och inte infört i Lakebase.**

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

Nya ärendetyper: `payout_request`, `payout_hindrance`, `death_report` och `tax_status`. *Steg 4 byggde `payout_request` och dessutom `payout_review` för systemets egna fynd vid 66 (§5.4); `payout_hindrance` byggs i steg 6.*
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

### Föreslagen byggordning (PB13)

Ett bygge i taget. Varje steg ska vara testat och fungera innan nästa börjar.

| Steg | Innehåll | Fall |
|---|---|---|
| 0 | Karl tar ställning till PB1–PB13. *Klart 2026-11-14: alla godkända* | – |
| 1 | Uttagsdel och tre förlopp, övergång av `policy_states`, anpassade läsare och `set_policy_paid_up`. *Byggt och infört i Lakebase 2026-11-14 (§4): 499 delar nr 1, inga uttag att flytta; agentrollernas läsrätt enligt B-048* | 38 |
| 2 | Operativ kapital- och garantijournal, övergång från S-04, paket A som premiekälla och A6-adapter (`ledger`). *Byggt 2026-11-14 (§6), verifierat lokalt, mot `svc_test` och på en kopia av Lakebase-backupen. Infört i Lakebase 2026-11-15: tabellerna och det ingående läget per 2026-10-31 (492 försäkringar, 15 097 garantidelar); `verify.py` 16 av 16* | 36, 37 |
| 3 | Månadsstängning steg 1–4 och 8 för sparandet, med granskning och rättelseversion. **Första leverans med nytta i Lakebase.** *Byggt 2026-11-19 (§7, val S1–S7), verifierat lokalt och mot `svc_test`; körskript i `scripts/simulation/paket_b_steg3/`. Migrationen införd i Lakebase 2026-11-19 (B-050); novembers AVK och stängning tidigast 2026-12-01* | 13, 15–17 |
| 4 | Begäran, plan, beslut, belopp, standardstart och delning. *Byggt 2026-11-21 (§5.4, val V1–V11), verifierat lokalt och mot `svc_test`; körskript i `scripts/simulation/paket_b_steg4/`. Mergat till main 2026-11-22 (B-052). Inte infört i Lakebase; migrationen tidigast efter novembers stängning (2026-12-01)* | 1–12 |
| 5 | Månadsrätt och skuld (steg 5) samt bolagskonto och bolagsstöd. *Byggt 2026-11-22 (§5.5, val W1–W12, B-053), verifierat lokalt och mot `svc_test`, med slutavräkningen (W6); körskript i `scripts/simulation/paket_b_steg5/`. Inte mergat och inte infört i Lakebase; migrationen efter steg 4:s* | 1, 5, 6, 14, 32, 33, 35 |
| 6 | Skattestatus, konto, bankuppdrag, godkännande, kvitton och simulatorns utbetalningssida | 18–25, 34 |
| 7 | Dödsfall och arvsvinst (steg 6–7); slutavräkningen byggs i steg 5 (W6) och fall 34 i steg 6 | 26–31 |
| 8 | Handläggarsidan *Pensioner och utbetalningar* med webbkontroll | – |
| 9 | Lakebase enligt ovan, med separat OK för varje ingrepp | – |

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
- **AVK för november och december 2026:** antar Karl syntetiska versioner i A4 för den
  operativa stängningen, som i P6-MANAD-001 (+0,20 % i november)? Det är beroendet mot projekt 5.
  *November avgjord 2026-11-19 (S5, §7.2): AVK-SIM-2026-02 enligt P6-MANAD-001 D5. December står öppen.*
- **Bolagskapitalets startinsättning:** beloppet bestäms med aktuariens E_min. För dagens
  bestånd utan pågående pension är likviditetsdelen noll; stressgapet återstår att räkna.
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
