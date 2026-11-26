# Paket B steg 8 – handläggarsidan Pensioner och utbetalningar: rapport och webbkontroll

> **Design:** [P1-PENSION-001 §10.1](../../../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md), Karls val Z1–Z14 (2026-11-25, ”Godkänn alla”). Loggade som **B-056** samma dag efter Karls OK (”Logga och bygg”).
> **Status:** byggt och verifierat lokalt 2026-11-25 på branchen `claude/nifty-lovelace-d19817`. **Mergat till main 2026-11-26** efter Karls OK. Steg 8 är bara webb och läsningar och rör inte Lakebase – ingen migration och ingen skarp körning (Z13).

## Vad som är byggt

- **Tre läsningar i tjänstelagret** (`src/services/pension_desk.py`, `src/services/operations/pension_desk.py`), alla `HUMAN_ONLY` (Z4):
  - `get_pension_status`: stegen 1–7 i vald databas, månaderna, delarnas lägen, öppna ärenden per typ och saldona;
  - `list_payout_parts`: lista med filter och sökning, utan personnummer;
  - `get_payout_person`: personens delar, skattestatus och konton. Kontonumret är maskerat, och verifieringsreferensen följer aldrig med.
- **Sidan `/pensioner`** (`src/web/routes/pensions.py`, sju mallar):
  - översikten och pensionsakten per försäkring;
  - fem flöden: månadsrätter och bolagskonto, bankfiler, dödsfall och månadsstängning;
  - pensionsaktens formulär för begäran, plan, skatt, konto, dödsfall och dödsbo (Z1–Z10).
- **Spärrar på sidan:**
  - Ett steg som inte är infört visar en notis och inga formulär. Ett POST mot ett sådant steg ger 409 utan anrop.
  - Operatörsåtgärderna kräver inloggning och operatörens token: bolagskonto, godkänn och hämta bankfil, och stängningen.
  - I Lakebase bokas stängningen aldrig från sidan.
- **Ärendelänkar:** varje paket B-ärende leder till rätt vy. Agenten startas inte i pensionsärenden (Z11).
- **Simulerad affärsdag** (`--affarsdag`, `--demo-fil`, `--behall-schema`, Z13):
  - bara för DEMO;
  - en gul banderoll visar dagen;
  - middleware sätter dagen för varje förfrågan.

## Webbkontrollen (Z13)

Paket C:s pensionsscenario kördes **dag för dag genom sidan**, i webbläsaren och som operatör, på en lokal SQLite-kopia av körningen `9f1b75a8…`:s startbild. Jämförelsen gjordes mot en CLI-referens av samma bild. Inget kördes mot Lakebase eller testbeståndet.

| Affärsdag | Genom sidan | Utfall |
|---|---|---|
| 2026-12-01 | Granska och boka novembers stängning | Kontrollerna går igenom. Granskningssumman `88a5cbcd…` är densamma som i kalendern. ”Månaden 2026-11 är stängd.” |
| 2026-12-15 | Bolagsinsättning 10 000,00 kr (operatör) | Bokad på bolagskontot i 2026-12 |
| 2026-12-15 | Pensionärens skattestatus, sidoinkomst 2027 | Version 1, sats 0,3000 från 2027-01-01 |
| 2026-12-15 | Pensionärens konto 0000/00000001 ”Simulerad bank”, verifierat | Visas bara maskerat: `0000 ****0001` |
| 2026-12-15 | Folkbokföringens avisering (fil) | 1 nytt misstänkt besked och ärendet *Dödsfall* för AL-000002 |
| 2026-12-15 | Verifiera dödsfallet, 2026-12-14, Folkbokföringen | Version 2 verifierad, personen avliden |
| 2027-01-04 | Granska och boka decembers stängning | Kontrollerna går igenom: brutto 2 040,07, pool in och ut 22 817,23, ΣG −73,55 kr/mån |
| 2027-01-04 | Skapa, granska och godkänn bankfilen | 1 uppdrag: brutto 2 040,07, skatt 612,00, netto 1 428,07 |
| 2027-01-04 | Hämta bankfilen | JSON som bilaga (`attachment`, `no-store`). Kontonumret finns bara i filen, aldrig på sidan |
| 2027-01-04 | Bankens kvittofil två gånger | Första gången: 1 nytt kvitto, och utbetalningarna är bokade. Andra gången: 0 nya och 1 redan inläst, ingenting nytt |

**Facit** (`web_check.py facit`): **0 avvikelser** mot `simulation.pension_calendar.EXPECTED`:

- brutto 2 040,07, skatt 612,00 och netto 1 428,07;
- betalningsskuld 0,00 och skatteskuld 612,00;
- arvsvinst 44,49 och 22 772,74;
- saldon 11 257,70, 0,00 och 621 378,25;
- poolen 22 817,23, med utgående saldo 0,00.

**Kontrollsummor:** webbkörningen och CLI-referensen är identiska på varje verifikation:

| Verifikation | Kontrollsumma |
|---|---|
| Stängningen november | `88a5cbcd…` |
| Stängningen december | `3defaae1…` |
| Bolagsinsättningen | `41c29240…` |
| Avräkningen | `b771a980…` |
| Bankfilen | `0ead1082…` |

**Utan steg 4–7:** en kopia utan stegens tabeller (som Lakebase före migrationerna), på affärsdag 2026-12-15.

- Översikten, akten, bankfilerna och dödsfallen visar vilka steg och tabeller som saknas, med migreringsskriptet och spärren ”tidigast 2026-12-01 och med Karls OK”.
- Sidorna visar inga formulär.
- Månadsstängningen, som bara bygger på steg 1–3, granskas som vanligt.

### Rättat under webbkontrollen

- Kvittobeskedet skrev listan av ärendenummer rått (`['CASE-…'] nya ärenden`). Det sa också ”Ingenting nytt att boka” när ett nytt avvisat kvitto lästs in. Nu står det ”1 nya ärenden om konto (CASE-…)” och ”Inga utförda utbetalningar att boka”. Fall 23 har fått ett eget webbtest.
- Bankfilens skattemetod visades som `percent`. Den har nu svenska etiketter: procentsats, fast belopp och de två småbeloppsgränserna.
- Beskedet efter ”skapa bankfil” nämnde operationsnamnet. Nu: ”Bankfilen är skapad. Granska uppdragen och godkänn filen nedan.” Om filen redan fanns: ”Bankfilen för dagen finns redan – inget nytt skapades.”
- Bolagskontots rad löd ”Saldon per 2026-12. ej beräknat …”. Nu: ”Stressgap: ej beräknat …”.

**Jämförelsen med main (Z14, B-052):** `scripts/simulation/paket_b_steg7/compare_main.py` mot main `895da08` gav **IDENTISKT** i alla sju lägen:

- `steg3`, `steg4`, `steg5`, `steg5-ung`, `steg5-66`, `steg6` och `steg6-avliden`;
- samma granskningssumma, verifikation, rader och ärenden, och i `steg6-avliden` samma blockering.

## Testerna

- `tests/test_pension_desk.py`: 16 lokala tester och 1 Postgres-test.
- `tests/test_web_pensions.py`: 35 tester.
- Båda ligger i sviterna enligt `tests/suites.toml`.
- Hela sviten (`run_tests.py --all --run --postgres`) gav först 3 fel, som är rättade:
  - `migrate_payout_parts.py --help` föll på en cirkelimport. Läsningarna tar nu steg 1:s och 2:s tabellnamn ur modellerna, och ett test håller dem lika med migreringarnas.
  - Inloggningslänken på pensionssidan saknade `hx-boost="false"`.
  - Skillkatalogen saknade de tre nya läsningarna och är omgenererad.

## Köra om webbkontrollen

Allt körs lokalt. Bilderna och testlösenordet ligger i `logs/simulation/paket_b_steg8/web/`, som är gitignorerat. Lösenordet skrivs aldrig ut.

```powershell
python scripts/simulation/paket_b_steg8/web_check.py copy START.sqlite logs/simulation/paket_b_steg8/web/webb.sqlite
python scripts/simulation/paket_b_steg8/web_check.py serve logs/simulation/paket_b_steg8/web/webb.sqlite --day 2026-12-01
python scripts/simulation/paket_b_steg8/web_check.py receipt BANKFIL.json --day 2027-01-04 --seed 1
python scripts/simulation/paket_b_steg8/web_check.py facit logs/simulation/paket_b_steg8/web/webb.sqlite
```

- `.claude/launch.json` har förinställningar för affärsdagarna 2026-12-01, 2026-12-15 och 2027-01-04, och för kopian utan steg 4–7.
- Servern startas om mellan dagarna.

## Kvar

- Sidan blir användbar mot Lakebase först när steg 4–7 är införda. Migrationerna körs tidigast efter novembers stängning (2026-12-01), i ordningen steg 4, 5, 6 och 7, var och en med Karls OK.
