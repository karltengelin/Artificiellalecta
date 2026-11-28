# Paket B steg 9 – nytt startläge med pensionärer: rapport och körordning

> **Design:** [P1-PENSION-001 §12.1](../../../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md#121-val-för-steg-9-nytt-startläge-med-pensionärer), Karls val Q1–Q10 (2026-11-28, ”Godkänn alla”), loggade som **B-057** samma dag (”Logga och bygg”). Q1 och Q3 justerades efter loggningen (”Ja, bygg så”); justeringarna står i §12.1 och föreslås som tillägg till B-057.
> **Status 2026-11-28:** byggt och verifierat lokalt och mot `svc_test` på branchen `claude/nifty-lovelace-d19817`. **Inte mergat och inte kört i Lakebase.** Novembers AVK och stängning kan göras tidigast 2026-12-01, decembers tidigast 2027-01-01, och varje skrivande punkt kräver backup och Karls separata OK.

## Vad som är byggt

- **Beståndet** (`src/simulation/pension_population.py`), 35 personer, alla fiktiva och fasta:
  - kohorten `OLDER_COHORT` (B-035 val K), 31 personer födda 1959–1962, med premier dragna med ett fast frö i hela
    10 000 kr mellan 300 000 och 1 500 000 kr;
  - fyra pensionärer som har passerat 66:

    | Person | Startpremie | Plan från december 2026 | Skatt 2027 |
    |---|---|---|---|
    | David Dahl (1959) | 900 000 kr | livsvarig | sidoinkomst 30 % |
    | Margareta Berg (1958) | 1 200 000 kr | tidsbegränsad, 120 månader | sidoinkomst 30 % |
    | Lars Ekström (1960) | 450 000 kr | livsvarig | individuellt beslut 25 % |
    | Karin Sjöberg (1959) | 700 000 kr | delning från november: del 1 livsvarig, del 2 (40 %) på 60 månader | sidoinkomst 30 % |

  - Alla har fribrev från en avslutad anställning hos den första ITP-arbetsgivaren efter organisationsnummer (Q2).
  - Varje försäkring får en syntetisk premie, märkt `declared_opening` i `calculation_basis` och betald 2026-10-30
    (Q3, justerad). S-04 räknar fram C och G som för övrigt bestånd.
  - Tillägget har en granskningssumma, stoppar vid krock med befintligt personnummer och ger ingen ny effekt när
    det görs igen.
- **Ersättningen av det ingående läget** (`src/services/ledger_reopening.py`, Q4):
  - Granskningen bygger det nya läget ur S-04 och jämför per försäkring med det bokade. Den läser det sparade
    utdraget, inte journalens rader, eftersom SQLite lagrar G som flyttal.
  - Ersättningen stoppas när journalen har någon annan verifikation, när en befintlig försäkring får annat C
    eller G och när en försäkring faller bort.
  - Bokningen sker i en transaktion med låset för det ingående läget. Den tar bort den gamla verifikationens
    kontroller, kapitalposter och garantidelar och bokar det nya läget med `capital_ledger.apply_opening`.
    Därefter prövar den de befintliga försäkringarna en gång till.
  - Det gamla lägets sammanställning lämnas i svaret (`replaced_content`), och körskriptet sparar den i loggen.
    Det sparade S-04-utdraget för det gamla läget ligger kvar i `valuation_extracts`.
- **Underlaget för pensionärernas operationer** (samma modul): delning, begäran om start per uttagsdel,
  skattestatus, konto i den simulerade banken (clearing 0000) och bolagsinsättningen, 24 × decembers
  månadsbelopp uppåt till hela 10 000 kr (Q6).
- **Körskripten** i den här mappen, se körordningen nedan.
- Inga nya tabeller, operationer eller agentbefogenheter (Q9).

## Verifierat

`tests/test_pension_population.py` (9 prov) kör hela ordningen på paket A:s testbestånd. Det började med journalens
första ingående läge, som i Lakebase sedan 2026-11-15:

- **Befintliga försäkringar oförändrade:** alla har exakt samma C och G per försäkring, och bara de 35 nya tillkommer.
- **De nya:** C är lika med startpremien per försäkring, och G är större än noll.
- **Novembers stängning** går igenom med 11 ärenden `payout_review`, ett per person som passerat 66 utan plan
  (7 i kohorten och de 4 pensionärerna, vars begäran registreras först efter stängningen).
- **Decembers stängning och bankfilen** stämmer mot ett facit som räknas i provet, utanför koden, på öret:

  | Person | Brutto | Skatt | Netto |
  |---|---|---|---|
  | Margareta Berg | 10 540,68 | 3 162 | 7 378,68 |
  | Karin Sjöberg (två delar) | 6 262,15 | 1 878 | 4 384,15 |
  | David Dahl | 3 278,70 | 983 | 2 295,70 |
  | Lars Ekström (25 %) | 1 583,10 | 395 | 1 188,10 |
  | **Summa** | **21 664,63** | **6 418** | **15 246,63** |

  - Summa brutto är lika med summa M för planerna. Bolagsinsättningen blir 520 000 kr (24 × 21 664,63 = 519 951,12).
  - Efter bankens kvitton är pensionsskulden noll per januari, skatteskulden 6 418 kr, och alla fem anspråk är
    betalda.
- **Ersättningen** är idempotent och stoppas efter en stängning.
- **Körskripten** körs i provet i Q5:s ordning mot provets databas: granskning, sedan `--apply` med granskningens
  summa. Samma fas igen ger ingen ny effekt, och `verify.py` ger sju godkända kontroller och facit.
- **Mot `svc_test`** (isolerad Postgres): samma kedja från det första ingående läget till kvittona
  (`test_kedjan_mot_postgres`), med låset. Grupperna `pensions` och `payments` med `--postgres`: 261 godkända,
  inga överhoppade. Provfilen kördes igen efter de sista ändringarna: 9 av 9, också mot Postgres.

Bygget hittade ett fel: avrundningen uppåt av bolagsinsättningen gick nedåt, eftersom `Decimal` delar mot noll.
Provet med 12 345,67 kr fångade det, och felet är rättat (`ROUND_CEILING`).

Beloppen i Lakebase blir desamma för de nya försäkringarna om grunderna är desamma: SIM-G, AVK-SIM-2026-02 med
+0,002 för november och samma premier. Decembers avkastning påverkar C men inte månadsbeloppen.

## Körordning i Lakebase (Q5)

**Spärrar:** novembers AVK och stängning tidigast 2026-12-01, decembers tidigast 2027-01-01. Varje skrivande punkt
kräver en färsk backup (`scripts/maintenance/backup_database.py`), samordning enligt AGENTS.md §4.5 och Karls
separata OK. Varje skript granskar `READ ONLY` som standard och skriver loggen till huvudkatalogens
`logs/simulation/paket-b-steg9/`.

1. Backup.
2. Migrationerna för steg 4–7 i ordning, var och en torrkörd först: `migrate_payout_plans.py`,
   `migrate_pension_claims.py`, `migrate_payout_orders.py` och `migrate_death_reports.py`.
3. `add_population.py`, sedan `--apply --backup <mapp> --reviewed-checksum <summa>`.
4. `reopen_ledger.py` på samma sätt. Granskningen ska visa 492 oförändrade, 0 ändrade, 0 bortfallna och 35 nya.
5. `pensioners.py --phase split` – Karin Sjöbergs delning, före novembers stängning.
6. Tidigast 2026-12-01: `../paket_b_steg3/adopt_avk.py` och `../paket_b_steg3/close_month.py`.
7. `pensioners.py --phase start`, `--phase inputs` och `--phase capital`.
8. Tidigast 2027-01-01: `adopt_avk_december.py --rate <sats>`, där Karl bekräftar satsen (standard +0,002), och
   `../paket_b_steg3/close_month.py --month 2026-12-01`. Därefter bankfil, godkännande och kvitton på pensionssidan
   (steg 8).
9. `verify.py` efter varje punkt, med `--replaced <loggen från punkt 4>` från och med punkt 4.

## Att känna till

- **Äldre körskripts väntade värden** gäller läget före punkt 4. `paket_b_steg2/verify.py` och
  `paket_b_steg3/verify.py` jämför mot det första ingående läget (utdragshashen `023946…3fefa` och
  42 087 223,57 kr). Efter punkt 4 körs steg 3:s kontroll med `--expected none`.
- **P6-MANAD-001:s månadsförsök** (`services.premium_month_inputs`) kräver den frysta utdragshashen och att
  ingen har en plan som startat. Efter punkt 3–4 går det inte att köra mot Lakebase. Det var ett engångsförsök
  för oktober–november 2026 och är redan gjort (2026-11-03).
- **2027 års kundbelastning** (`customer_tax_rate`, PR-ITP1-023) behövs inte för decembers stängning. Den behövs
  före januaris stängning och läggs in som parameterändring, när SLR för november 2026 är känd.
- **Huvudinkomst med skattetabell** (X4) är ett eget steg och ingår inte. Pensionärerna har sidoinkomst eller
  individuellt beslut.
- **Kohortens 24 födda 1961–1962** får standardstart från februari 2027 (V4). Det kräver januaris stängning och
  bolagskapital för deras belopp.

## Prov

```
python scripts/testing/run_tests.py --suite pensions --suite payments --run
python scripts/testing/run_tests.py --suite pensions --suite payments --run --postgres
```
