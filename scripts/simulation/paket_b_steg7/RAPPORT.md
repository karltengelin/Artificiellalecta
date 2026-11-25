# Paket B steg 7 – dödsfall, avräkning, arvsvinst och dödsbo: rapport och körordning

> **Design:** [P1-PENSION-001 §9 och §9.1](../../../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md), PB9 och PB10, PR-ITP1-010, -011 och -020 steg 6–7, B-047 punkt 7, Karls val Y1–Y14 (2026-11-24, ”Godkänn alla”). Loggade som **B-055** samma dag efter Karls OK (”Logga och bygg”).
> **Status 2026-11-24:** byggt och verifierat lokalt och mot `svc_test` på branchen `claude/paket-b-steg-7-design-c61002`. Jämförelsen med main `df93ea2` är identisk i alla sju lägen, och efter synken med main `70bba89` (paket C) också. **Mergat till main 2026-11-25** efter Karls OK; **inte infört i Lakebase.**

## Vad som är byggt

- **Besked och dödsbo** (`src/services/death_reports.py`):
  - besked som versionskedja per person: misstänkt, verifierat eller tillbakadraget (Y2);
  - personens status `deceased` vid verifieringen, med tidigare status sparad och återställd vid tillbakadragning;
  - folkbokföringens avisering som misstänkta besked, idempotent per besked-id (Y14);
  - dödsboets behörighet med konto (Y10) och läsningarna för stängningen, bankfilen och `get_death_settlement`.
- **Stängningen** (`src/services/month_close.py`), PR-020 steg 6–7, bara när steg 7:s tabeller finns:
  - avräkningen i första stängningen på eller efter dödsdagen: dödsmånadens rätt står kvar, ingen rätt efter, kapitalet till poolen, G = 0 och delen `ended` (`death`) (Y4, Y6);
  - återföring av ej betalda anspråk efter dödsmånaden, väntan på kvitto för skickade och okända, och ärendet `death_recovery` för utförda (Y5);
  - poolens fördelning samma månad efter `E = C_öppning × q/(1 − q)` ur SIM-R, eller ärendet `inheritance_pool` när poolen står kvar (Y7);
  - premien efter dödsfallet hålls utanför journalen och redovisas i ärendet `death_report` (Y6);
  - kontrollerna *dödsfall* och *arvsvinstpool*, och *kapital totalt* med de nya flödena (Y9);
  - rättelse av en månad med avräkning blockeras (Y8).
- **Bankfilen** (`src/services/payout_orders.py`): misstänkt dödsfall blockerar (`death_suspected`, Y3); dödsboets uppdrag med rätt senast dödsmånaden, verifierad behörighet och avräknade delar (annars `estate_missing`), och skatten utan småbeloppsgränser (`payout_tax.withholding(..., thresholds=False)`, Y10).
- **Fem operationer**, alla `HUMAN_ONLY` (Y11): `register_death_report`, `verify_death_report`, `import_death_notices`, `register_estate_authority` och `get_death_settlement`.
- **Simulatorn** (`src/simulation/counterparties.py`): `death_notice_file` med källan `population-register-sim` och scenariot bara i facit (Y14).
- **Migrationen** (`scripts/migrations/migrate_death_reports.py`):
  - skapar fyra tomma tabeller;
  - vidgar fem villkor (postens orsak, de icke-negativa kontona, garantins orsak, ärendetypen och ärenden utan person);
  - kräver steg 6;
  - ändrar inga rader.

## Verifierat

| Fall | Var | Utfall |
|---|---|---|
| 26 | lokalt och `svc_test` | En sparare dör 2026-11-10. Novembers stängning för kapitalet till poolen, sätter G = 0 och avslutar delen från december. Poolen fördelas samma månad på tre mottagare efter SIM-R-2026-01; den avlidnes del får ingen arvsvinst och poolen är 0. Premien efter dödsfallet hålls utanför. Sjutton kontroller godkända och verifikationen kontrolleras. I december ingen ny avräkning. Mot `svc_test` kan poolen inte bli negativ |
| 27 | lokalt | B dör 2026-11-20 efter novembers stängning. Bankfilen blockeras (`estate_missing`) tills delarna är avräknade i decembers stängning, som inte bokar någon decemberrätt. Dödsboets fordran är novembers 10 000 kr, som betalas till dödsboets verifierade konto med 3 000 kr skatt |
| 28 | lokalt | Död före första rätten: ingen standardstart, ingen rätt och delen `ended` från november. Död på startdagen: standardstart och dödsmånadens rätt, delen `ended` från december. Död under paus: ingen rätt i januari, delen `ended` från februari |
| 29 | lokalt | Utan antagen SIM-R står poolen kvar med ärendet `inheritance_pool` utan person, och kontrollen *arvsvinstpool* är godkänd |
| 30 | lokalt | Ett misstänkt besked blockerar bankuppdraget (`death_suspected`) utan hinderärende och påverkar inte stängningen; en förberedd fil ger konflikt vid godkännandet; ett tillbakadraget besked släpper stoppet |
| 31 | lokalt | Sent besked i januari med dödsdag i november: decembers ej betalda rätt återförs exakt (skulden 0, kapitaldelen och bolagsstödet tillbaka) och betalas inte. En redan betald decemberrätt ger i stället ärendet `death_recovery`, utan kvittning |
| Y2 | lokalt | Misstänkt → verifierat → ny dödsdag som versioner; ett verifierat besked nedgraderas inte; dödsdag efter rapportdagen och framtida mottagning avvisas; tillbakadraget återställer statusen; efter avräkningen kan beskedet inte ändras |
| Y8 | lokalt | Rättelse av november med avräkning blockeras |
| Y10 | lokalt | Dödsboets skatt utan gränserna: 99,99 kr ger 29 kr och 500 kr med låg årssumma 150 kr |
| Y14 | lokalt | Aviseringen ger ett misstänkt besked med kanalen `system`, redovisar ett okänt personnummer och ger ingen ny effekt andra gången; fel kontrollsumma blockeras |
| B-052 | lokalt | Utan steg 7:s tabeller saknar stängningen sektionen och kontrollerna, och operationerna blockeras med hänvisning till migrationen |
| Befogenheter | lokalt | Agenter nekas alla fem operationerna och systemaktören de fyra skrivande; systemaktören får läsa |
| Migrationen | `svc_test` | Från läget efter steg 6 blockeras läsningen; torrkörningen skriver inget; migrationen ger tabellerna, journalens villkor och `cases` identiska med `create_all`, är idempotent och lämnar det ingående läget orört. Delvis införd migration och saknat steg 6 stoppar |

### Jämförelsen med main (B-052, Y13)

`compare_main.py` bygger testbeståndet med main:s kod och kör sedan novembers granskning och bokning, en gång med main:s kod och en gång med branchens, på var sin kopia av samma databas. Steg 7:s tabeller finns aldrig i databasen. Resultatet 2026-11-24 mot main `df93ea2`:

| Läge | Utfall |
|---|---|
| `steg3` (steg 4:s, 5:s och 6:s tabeller borttagna; B fyller 66, C har passerat 66) | Identiskt: samma granskningssumma, 20 poster, 8 garantidelar, 2 ärenden |
| `steg4` (steg 4:s tabeller; C har passerat 66) | Identiskt: 20 poster, 8 garantidelar, 3 ärenden |
| `steg5` (steg 5:s tabeller; B fyller 66 och bolagskontot har en insättning) | Identiskt: 20 poster, 7 garantidelar, 3 ärenden |
| `steg5-ung` (steg 5:s tabeller, ingen som fyllt 66) | Identiskt: 20 poster, 8 garantidelar, 2 ärenden |
| `steg5-66` (som `steg5` med C som passerat 66 utan plan) | Identiskt: 20 poster, 7 garantidelar, 4 ärenden |
| `steg6` (alla main:s tabeller och den första månadsrätten) | Identiskt: 20 poster, 7 garantidelar, 3 ärenden |
| `steg6-avliden` (som `steg6` med B avliden utan besked) | Identiskt: samma granskningssumma, ej godkänd med ett problem (standardstarten), ej bokad |

Granskningssumman bygger på testbeståndets slumpade id och jämförs inom samma bygge. Det som inte beror på id:na – godkänd, kontrollerna, sektionerna, summafälten och antalet rader – står i `main_shape.json` (skriven med `--write-shape`) och låses av `tests/test_death_reports.py`. Jämförelsen körs om mot den main som gäller före merge.

## Körordning i Lakebase (Y12)

Ingenting körs utan Karls separata OK för varje steg och samordning enligt AGENTS.md §4.5.

1. Novembers stängning och steg 4:s, 5:s och 6:s migrationer, var och en efter eget OK (deras rapporter).
2. `python scripts/simulation/paket_b_steg7/survey.py` (skrivskyddad): personer med status `deceased`. Var och en behöver ett verifierat besked innan nästa stängning avräknar dem.
3. Backup med `scripts/maintenance/backup_database.py`.
4. Torrkörning: `python scripts/migrations/migrate_death_reports.py`.
5. Skarp körning: `python scripts/migrations/migrate_death_reports.py --apply --backup backups/<mapp>`.
6. Före varje stängning med dödsfall: `survey.py --month <månad>` visar avräkningar, återföringar, poolen och kontrollerna.

## Utanför steg 7

Sen dödsfallsrättelse efter avräkningen (ändrad dödsdag eller tillbakadraget verifierat besked), verkställt återkrav och återbetalt belopp till poolen, dröjsmålsränta, KU och AGI, och handläggarsidan (steg 8).
