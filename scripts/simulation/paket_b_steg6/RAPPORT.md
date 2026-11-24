# Paket B steg 6 – skatt, konto, bankuppdrag och kvitton: rapport och körordning

> **Design:** [P1-PENSION-001 §8](../../../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md) och §8.3, PB7 och PB8, PR-ITP1-026, B-047 punkt 6, Karls val X1–X13 (2026-11-24, ”Godkänn alla”). Loggade som **B-054** samma dag efter Karls OK (”Logga och bygg”).
> **Status 2026-11-24:** byggt och verifierat lokalt och mot `svc_test` på branchen `claude/paket-b-steg-6-design-03306f`. Jämförelsen med main `2ed556d` är identisk i alla fem lägen. **Mergat till main 2026-11-24** efter Karls OK; **inte infört i Lakebase.**

## Vad som är byggt

- **Skatten** (`src/skills/calculation/payout_tax.py`), utan databas:
  - per uppdrag på summan av personens rader, i hela kronor med öretalet bortfallet;
  - gränserna 100 kr per uppdrag och 1 000 kr förväntat under året för A-skatt, inte för SINK;
  - sidoinkomst minst 30 %, individuellt beslut med procent eller belopp, SINK med sats;
  - huvudinkomst blockeras (`table_missing`) tills skattetabellen byggts (X4).
- **Tjänstelogiken** (`src/services/payout_orders.py`):
  - skattestatus och konto som versionskedjor per person, idempotenta på innehållet;
  - betalbara anspråk (X2), bankfilen per betalningsdag med blockering och ärenden, ersättning av en förberedd fil och hashbundet godkännande (X7);
  - kvittofilen med övergångarna och verifikationen `payout_settlement` (X8, X9);
  - anspråkens betalningsläge och läsningarna med maskerade konton.
- **Sex operationer**, alla `HUMAN_ONLY` (X12): `register_tax_status`, `register_payout_account`, `create_payout_orders`, `approve_payout_order` (`external`), `import_payout_receipts` och `list_payout_orders`.
- **Stängningen** (`src/services/month_close.py`): med steg 6:s tabeller räknar steg 8 in månadens utbetalningar i skuldens utgående saldo och lägger kontrollen *utbetalningar* (X10). Utan tabellerna är allt som i steg 5.
- **Simulatorn** (`src/simulation/counterparties.py`): bankens kvittofil `payout_receipt_file` med källan `bank-sim-payout`, utfall per uppdrag och omgång, facit separat (X11).
- **Migrationen** (`scripts/migrations/migrate_payout_orders.py`):
  - skapar sex tomma tabeller;
  - vidgar fyra villkor (verifikationens slag, postens orsak, de icke-negativa kontona och ärendetypen);
  - kräver steg 5;
  - ändrar inga rader.

## Verifierat

| Fall | Var | Utfall |
|---|---|---|
| 18–20 | lokalt | 1 000,00 kr sidoinkomst ger 300 kr skatt; 333,33 kr ger 99 kr; 99,99 kr ger inget avdrag; exakt 100 och 1 000 kr omfattas inte av gränserna; SINK har inga gränser |
| 21 | lokalt | Saknat och overifierat konto, saknad skattestatus och huvudinkomst utan tabell blockerar med ärendena `payout_hindrance` och `tax_status`, en gång per hinder respektive person och år. Skulden står kvar. Ett verifierat konto och en registrerad status stänger ärendena |
| 22 | lokalt | Bankfilen för 2026-12-01 skapas 2026-12-04 med utförandedag 2026-12-04 (försenad). 10 000 kr brutto ger 3 000 kr skatt och 7 000 kr netto. Godkännandet lämnar kontonumret till banken, läsningen visar det maskerat. Det utförda kvittot bokar `payout_settlement` i december: skulden 0, skatteskulden 3 000 kr. Samma kvitto igen ger ingen effekt; samma id med annat utfall ger konflikt |
| 23 | lokalt | Avvisat kvitto bokar inget och öppnar ett hinder. Nästa fil blockeras tills ett nytt verifierat konto registrerats; då blir det försök 2 med samma anspråk |
| 24 | lokalt | Återkommen betalning ger exakta motposter: skulden 10 000 kr och skatteskulden 0 igen. Retur av retur ger konflikt |
| 25 | lokalt | Okänt utfall bokar inget, och inget nytt försök görs förrän bankens senare kvitto (utfört) kommer |
| 34 | lokalt | En ändrad skattestatus ersätter den förberedda filen (försök 2, skatt 3 500 kr). Den ersatta filen kan inte godkännas, och ändrat konto eller ändrad utförandedag ger konflikt vid godkännandet |
| X5 | lokalt | Sidoinkomst under 30 % eller i bråkdels procent avvisas; frivilligt 40 % gäller från mottagandet + 14 dagar och påverkar inte en tidigare utförandedag; SINK och individuellt beslut kräver beslutsreferens |
| X10 | lokalt | Decembers stängning efter en utbetalning: kontrollen *utbetalningar* godkänd, skulden 10 000 + (−10 000) + decembers rätt = 10 000 kr, och verifikationen kontrolleras |
| B-052 | lokalt | Utan steg 6:s tabeller saknar stängningen kontrollen och sektionen, och operationerna blockeras med hänvisning till migrationen |
| Befogenheter | lokalt | Agenter nekas alla sex operationerna och systemaktören de fem skrivande |
| Migrationen | `svc_test` | Från läget efter steg 5 blockeras bankuppdragen; torrkörningen skriver inget; migrationen ger tabellerna, journalens villkor och `cases` identiska med `create_all`, är idempotent och lämnar det ingående läget orört. Delvis införd migration och saknat steg 5 stoppar |
| 22 | `svc_test` | Bankfil, godkännande och utfört kvitto bokar `payout_settlement`: skulden 0 och skatteskulden 3 000 kr. Villkoret tillåter bara en förberedd fil, och skatteskulden kan inte bli negativ |

### Jämförelsen med main (B-052, X10)

`compare_main.py` bygger testbeståndet med main:s kod och kör sedan novembers granskning och bokning, en gång med main:s kod och en gång med branchens, på var sin kopia av samma databas. Steg 6:s tabeller finns aldrig i databasen. Resultatet 2026-11-24 mot main `2ed556d`:

| Läge | Utfall |
|---|---|
| `steg3` (steg 4:s och steg 5:s tabeller borttagna; B fyller 66, C har passerat 66) | Identiskt: samma granskningssumma, 20 poster, 8 garantidelar, 2 ärenden |
| `steg4` (steg 4:s tabeller; C har passerat 66) | Identiskt: 20 poster, 8 garantidelar, 3 ärenden |
| `steg5` (steg 5:s tabeller; B fyller 66 och bolagskontot har en insättning, första månadsrätten bokas) | Identiskt: 20 poster, 7 garantidelar, 3 ärenden |
| `steg5-ung` (steg 5:s tabeller, ingen som fyllt 66) | Identiskt: 20 poster, 8 garantidelar, 2 ärenden |
| `steg5-66` (som `steg5` med C som passerat 66 utan plan) | Identiskt: 20 poster, 7 garantidelar, 4 ärenden |

## Körordning i Lakebase (X13)

Ingenting körs utan Karls separata OK för varje skarpt steg och samordning enligt AGENTS.md §4.5.

1. Steg 4:s och steg 5:s migrationer, var och en efter eget OK (deras rapporter).
2. Backup med `scripts/maintenance/backup_database.py`.
3. Torrkörning: `python scripts/migrations/migrate_payout_orders.py`.
4. Skarp körning: `python scripts/migrations/migrate_payout_orders.py --apply --backup backups/<mapp>`.
5. Därefter registreras skattestatus och konton för personerna med en månadsrätt innan den första bankfilen skapas.

## Utanför steg 6

Skattetabellen för huvudinkomst (eget steg när Karl hämtat Skatteverkets tabeller), dröjsmålsränta, dödsbo och dödsfall (steg 7), KU och AGI, skatteinbetalningen till Skatteverket, prognosen till projekt 5 och handläggarsidan (steg 8).
