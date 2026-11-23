# Paket B steg 5 – månadsrätt, skuld och bolagskonto: rapport och körordning

> **Design:** [P1-PENSION-001 §5.5](../../../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md), §7.1 steg 5 och §9, PR-ITP1-026–028, B-047 punkt 4 och 6, Karls val W1–W12 (2026-11-22, ”Godkänn alla”). Loggade som **B-053** 2026-11-23 efter Karls OK.
> **Status 2026-11-22:** byggt och verifierat lokalt och mot `svc_test` på branchen `claude/paket-b-steg-5-manadsr-e22262`. **Inte mergat till main och inte infört i Lakebase.**

## Vad som är byggt

- **Beräkningen** (`src/skills/calculation/pension_claim.py`), utan databas:
  - finansieringen brutto = ur C + bolagsstöd + ej finansierat (PR-ITP1-028);
  - slutavräkningen max(M, C) för den sista rätten (PR-ITP1-027);
  - debiteringen per kapitalspår i ören med största bråkrest.
- **Tjänstelogiken** (`src/services/pension_claims.py`):
  - beloppsbeslut i ordningen W2 (planens M, start, återstart, januari, senaste beslut);
  - bolagskontot och skulden;
  - äldsta ej finansierade anspråk först;
  - läsningarna.
- **Två operationer**, båda `HUMAN_ONLY`:
  - `register_company_capital`: ägarens insättning, idempotent;
  - `list_pension_claims`: läsning.
- **Stängningen** (`src/services/month_close.py`):
  - steg 1: standardstart vid 66 med sparad plan (`standard_start`), lägena `in_payout`, `paused` och `ended`;
  - steg 5: beloppsbeslut, anspråk, debitering, bolagsstöd, ej finansierat och senare finansiering;
  - kontrollerna *månadsrätt*, *förbrukade rätter* och *skuld och bolagskonto*;
  - ärendet `company_capital` vid ekonomiskt block.
- **Premierna** (`ledger_premiums.py`): en premie på en del som startar eller har startat hålls utanför journalen med ett ärende `payout_review` (W9). Det gäller bara när steg 5:s tabeller finns.
- **Migrationen** (`scripts/migrations/migrate_pension_claims.py`):
  - skapar tre tomma tabeller;
  - vidgar fyra villkor och lägger till ett;
  - kräver steg 4;
  - ändrar inga rader.

## Verifierat

| Fall | Var | Utfall |
|---|---|---|
| 1 och 14 | lokalt och `svc_test` | Ägaren fyller 66 i november. Novembers stängning sparar standardplanen (`standard_start`), beslutar M (`start`), sätter delen i `in_payout` och bokar första rätten. Debiteringen fördelas på spåren, skulden blir M och betalningsdagen är 2026-12-01 |
| 14 (beräkning) | lokalt | C 100 953,83 kr och M 500 kr ger skuld 500 kr och C 100 453,83 kr |
| 35 | lokalt | C räcker inte och bolagskontot räcker inte. Månaden stängs, skulden bokas för den finansierade delen och resten står som ej finansierat, med ärendet `company_capital`. Efter en ny insättning finansierar nästa stängning det äldsta först (`pension_claim_fundings`) |
| PB11 | lokalt | En stängning med en rätt utan registrerad insättning blockerar. En månad utan rätt kräver ingen insättning |
| W9 | lokalt | Premien på delen som startar hålls utanför journalen, och ett ärende `payout_review` öppnas en gång |
| 5 | lokalt | En tidsbegränsad del pausas januari–februari 2027. Då flyttas kalenderslutet två månader, och pausmånaderna har ingen rätt. Återstarten i mars ger `restart` och rätt nummer 3. Lägena blir `not_started` → `in_payout` → `paused` → `in_payout` |
| 6 | lokalt | En startad tidsbegränsad del förlängs till livsvarig. Det ger ett nytt belopp, `plan_change`, med planens M |
| Januari | lokalt | Januariomräkningen beslutar ett nytt M med golvet |
| 32 och 33 (beräkning) | lokalt | Sista rätten med M 100 och C 140 ger 140 och C = 0. Med C 80 ger den bolagsstöd 20 och skulden 100 |
| W10 | lokalt | En rättelse med ändrad AVK ändrar bara spårens fördelning; anspråket är oförändrat |
| Utan steg 5:s tabeller | lokalt | Stängningen beter sig som steg 4, och utan steg 4:s som steg 3 |
| Migrationen | `svc_test` | Från läget efter steg 4 blir resultatet identiskt med `create_all`. Migrationen är idempotent; delvis införd och saknat steg 4 stoppar |
| Befogenheter | lokalt | Agenter nekas båda operationerna, och systemaktören insättningen |

Grupperna `pensions` och `data` kördes med `--postgres` mot `svc_test` 2026-11-22, med resultatet 343 godkända och 4 underkända:

- Tre av de underkända var migrationstester för steg 1–4 som bygger en del av schemat. Steg 5:s tabeller kom med i det urvalet fast tabellerna de pekar på saknades. Filtren är rättade, och de tre testerna godkänns.
- Det fjärde, steg 5:s eget prov för delvis införd migration, föll på samma sätt. Det föll sedan i teardown efter en körning som tog över sju timmar och gick över natten. Ensamt godkänns det på 43 sekunder.

### Jämförelsen med main (B-052)

`compare_main.py` bygger testbeståndet med main:s kod och kör sedan novembers granskning och bokning, en gång med main:s kod och en gång med branchens, på var sin kopia av samma databas. Resultatet 2026-11-22 mot main `1d8f869` (paket C inräknat), efter att main mergats in i branchen:

| Läge | Utfall |
|---|---|
| `steg3`: utan steg 4:s och steg 5:s tabeller, B fyller 66 och C har passerat 66 | Identiskt: granskningssumma `c7e6a33a…`, 20 poster, 8 garantidelar, 2 ärenden |
| `steg3-ung`: som ovan utan någon som fyllt 66 | Identiskt: granskningssumma `7c1c30a8…`, 20 poster, 8 garantidelar, 2 ärenden |
| `steg4`: steg 4:s tabeller utan steg 5:s, C har passerat 66 | Identiskt: granskningssumma `96006c42…`, 20 poster, 8 garantidelar, 3 ärenden |
| `steg4-66`: som ovan och B fyller 66 | Blockeras lika i båda: granskningssumma `3b1cc531…`, ett problem |

Jämförelsen omfattar granskningssumma, problem, kontroller, innehåll och bokade rader, utom väggklockans tidsstämplar. Summorna skiljer sig mellan två byggen, eftersom testbeståndet får nya slumpade id, men inom en körning är de lika. Samma jämförelse mot main `a90fd7f` gav också identiskt i alla fyra lägen. Den ska köras igen mot aktuell main före en merge.

### Körskripten

Körskripten är provade på en lokal SQLite-kopia av testbeståndet med steg 5:s tabeller och dagen satt till 2026-12-01:

- `verify.py` ger 8 av 8 före stängningen.
- `survey.py` för november visar en standardplan, ett beloppsbeslut, en rätt med debitering 40,83 kr, två innehållna premier och ett ärende. Den visar också PB11:s blockering, eftersom ingen insättning finns.
- Efter en insättning på 10 000 kr godkänns granskningen, och november bokas.
- Efter stängningen ger `verify.py` 8 av 8, med skulden 40,83 kr och bolagskontot 10 000 kr. `survey.py` för december stoppar, eftersom december inte har tagit slut.

Kontrollerna som bara gäller Postgres prövas först i Lakebase: migrationens läge, kolumner, agenträttigheter och radantal mot backupen.

## Avvikelser

Se designstoppet §5.5. I korthet:

- kapitalposterna har inget `claim_id`; den senare finansieringen ligger i en egen tabell;
- bolagsstödet passerar inte C;
- slutavräkningen i stängningen är byggd men inte provad hela vägen, eftersom en del når sin sista rätt först efter minst 60 bokade rätter;
- `company_capital` är ett ärende utan person;
- en premie efter start bokas först i ett senare steg.

## Körordning i Lakebase (val W12)

Varje steg kräver Karls separata OK i chatten och samordning enligt AGENTS.md §4.5.

1. **Före allt:**
   - novembers stängning är bokad och `paket_b_steg3/verify.py` godkänd (tidigast 2026-12-01);
   - steg 4:s migration är införd och `paket_b_steg4/verify.py --backup` godkänd;
   - steg 5 är mergat efter Karls OK, med `compare_main.py` grön mot dåvarande main.
2. Kör översikten `python scripts/simulation/paket_b_steg5/survey.py`. Den bara läser. Lakebase har i dag ingen pågående pension, så den väntas inte visa någon rätt.
3. Ta en backup med `scripts/maintenance/backup_database.py`.
4. Torrkör `python scripts/migrations/migrate_pension_claims.py`.
5. Kör `--apply --backup backups/<mapp>` (**OK**).
6. Kontrollera med `python scripts/simulation/paket_b_steg5/verify.py --backup backups/<mapp>`. Det är bara läsning.
7. **Före den första stängningen med en månadsrätt** registrerar Karl bolagskapitalets startinsättning med `register_company_capital` (**OK**). Han bestämmer beloppet och dokumentreferensen, helst efter aktuariens E_min.
