# Paket B steg 3 – månadsstängning för sparandet: rapport och körordning

> **Design:** [P1-PENSION-001 §7](../../../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md#7-månadsstängningen-pb5), B-047 punkt 3, Karls val S1–S7 (2026-11-19, ”Godkänn alla”).
> **Status 2026-11-19:** byggt och verifierat lokalt och mot `svc_test`, mergat till main efter Karls OK (`b6b9ebb`). **Inte infört i Lakebase**.

## Vad som är byggt

- **Stängningen** (`src/services/month_close.py`): PR-ITP1-020 steg 1–4 och 8 för hela kollektivet.
  - Avkastning, kapitalavgift och skattebelastning per kapitalspår.
  - Månadens premier ur paket A vid månadsslut, med garantidel och utan avkastning.
  - Elva kontrollposter.
- **Granskning och rättelse:**
  - `prepare_month_close` räknar utan att skriva.
  - `close_policy_month` bokar med granskningssumman.
  - `get_month_close` visar versionerna.
  - Alla tre är `HUMAN_ONLY`.
  - En rättelse är en ny verifikation med motposter som pekar på versionen den ersätter.
- **Migrationen** (`scripts/migrations/migrate_month_close.py`):
  - lägger till `ledger_batches.supersedes_id`;
  - vidgar verifikationsslagen med `month_close` och `month_correction`;
  - lägger till versionskedjans villkor. Inga rader ändras.
- **Ledger-utdraget och A6** täcker varje stängd månads slut.

## Verifierat

| Fall | Var | Utfall |
|---|---|---|
| 13 | `tests/test_month_close.py` | C0 = 100 000,00 kr och r = 1 % ger +1 000,00, −16,67 och −29,50 kr, alltså C1 = 100 953,83 kr |
| 15 | lokalt | En premie på en ej startad del medan en annan del på försäkringen pågår ger en egen garantidel med referensplan från 66-årsmånaden. Den får ingen avkastning, och den pågående delen rörs inte |
| 16 | lokalt och `svc_test` | Samma stängning igen ger ingen ny post. Ändrad AVK ger en rättelse med bara avkastningens motposter. Bara den senast stängda månaden kan rättas |
| 17 | lokalt och `svc_test` | Saknad eller bara föreslagen AVK blockerar, och ingenting skrivs |
| 37 i stängningen | lokalt | Novembers premier bokas vid månadsslut. Avstämningskontot och mottagningar efter månadsslutet ger ingen effekt. En sen registrering bokas i nästa öppna månad |
| Migrationen | `svc_test` | Från Lakebase-läget efter steg 2 blir resultatet identiskt med `create_all`. Den är idempotent, och delvis infört stoppar. Det ingående läget är orört, och novemberstängningen går igenom med låset |

Körskripten är provade hela vägen på en lokal SQLite-kopia med dagen satt till 2026-12-01:
- AVK-granskningen och antagandet;
- stängningen, som blockeras utan AVK, granskas och bokas, och ger ingen ny effekt andra gången;
- `verify.py --backup`, med 16 av 16 kontroller.

## Körordning i Lakebase (val S6)

Varje skarpt steg kräver Karls separata OK i chatten och samordning enligt AGENTS.md §4.5.

1. **Efter merge:**
   1. Ta en backup med `scripts/maintenance/backup_database.py`.
   2. Torrkör `python scripts/migrations/migrate_month_close.py`.
   3. Kör `--apply --backup backups/<mapp>` (**OK**).
2. **Tidigast 2026-12-01, efter novembers sista bankfil:**
   1. Granska AVK med `python scripts/simulation/paket_b_steg3/adopt_avk.py`.
   2. Anta AVK med `--apply --backup <mapp> --reviewed-checksum <summa>` (**OK**). Skriptet stoppar före 2026-12-01.
3. Granska stängningen med `python scripts/simulation/paket_b_steg3/close_month.py`.
4. Boka den med `--apply --backup <mapp> --reviewed-checksum <summa>` (**OK**).
5. Kontrollera med `python scripts/simulation/paket_b_steg3/verify.py --backup <mapp>`. Det är bara läsning.

Väntade värden i Lakebase (`common.py`):
- öppningskapitalet 42 087 223,57 kr;
- novembers premier 51 623,90 kr, varav SvenskIndustries 15 362,24 kr;
- avstämningskontot 36 261,66 kr utan effekt.

Avkastning, avgift och skatt för november ger granskningen. Den ska läsas och godkännas före bokningen.

## Kvar och öppet

- **December:** AVK för december 2026 står öppen (§13). Utan den blockeras decembers stängning.
- **Pensionsförloppet:** steg 4–7 återstår, alltså begäran och plan, månadsrätt, dödsfall och arvsvinst. Tills dess blockerar en startad del med kapital och ett registrerat dödsfall stängningen (S4).
- **Beslutsloggen:** en post för S1–S7 är föreslagen men inte skriven.
