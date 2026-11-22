# Paket B steg 4 – begäran, uttagsplan och delning: rapport och körordning

> **Design:** [P1-PENSION-001 §5](../../../projekt/01_ärendehantering/PENSIONSAVRAKNING_DESIGNSTOPP.md#5-begäran-plan-och-belopp-pb3-pb6) och §5.4, B-047 punkt 3, Karls val V1–V11 (2026-11-21, ”Godkänn alla”). Loggade som B-051.
> **Status 2026-11-22:** byggt och verifierat lokalt och mot `svc_test`, mergat till main efter Karls OK (B-052). **Inte infört i Lakebase**; migrationen först när novembers stängning är bokad och kontrollerad (V11).

## Vad som är byggt

- **Kalender och belopp** (`src/skills/calculation/payout_plan.py`), utan databas:
  - frist och nästa möjliga månad, start, uppskov, paus och förlängning;
  - M = max(round_half_up(max(G, B)), ceil_öre(ΣG_j), golv);
  - värdebevarande omräkning och delningsandelens gränser.
- **Tjänstelogiken** (`src/services/payout_plans.py`) och fem operationer, alla `HUMAN_ONLY`:
  - `register_payout_request`: begäran med frist och ärende `payout_request`;
  - `preview_payout_plan`: förhandsberäkning med granskningssumma;
  - `decide_payout_plan`: hashbunden planversion;
  - `split_payout_part`: delning (PR-ITP1-024);
  - `get_payout_part`: läsning.
- **Stängningens steg 1** (`src/services/month_close.py`):
  - genomför beslutade planer och delningar i ändringsmånaden;
  - visar standardstarten vid 66 och öppnar ärenden `payout_review`;
  - blockerar månader med rätt enligt plan till steg 5;
  - efter migrationen ersätter kontrollen *standardstart* steg 3:s *standardstart väntar på steg 4*, och *rätt enligt plan* tillkommer;
  - före migrationen är stängningen identisk med steg 3.
- **Premierna** (`ledger_premiums.py`, premieunderlaget): en ny premie på en del med beslutad plan får G_j på planen. Premieunderlaget går till delningens premiemottagare.
- **Utdragen:** ledger-utdraget redovisar en försäkring med planbaserad garanti som ej beräknad (`payout_plan`).
- **Migrationen** (`scripts/migrations/migrate_payout_plans.py`):
  - skapar tre tomma tabeller;
  - vidgar två villkor;
  - lägger till `ledger_guarantee_parts.plan_id`.
  - Inga rader ändras.

## Verifierat

| Fall | Var | Utfall |
|---|---|---|
| 1 | lokalt | Ägaren fyller 66 i november 2026. Granskningen visar standardplanen livsvarig från 2026-11 med betalning 2026-12-01, och månaden blockerar till steg 5 |
| 2, 12 | lokalt och `svc_test` | Uppskov till 72 bokas i ändringsmånaden. Varje G_j räknas om värdebevarande som ny version med plankoppling (10 × 200/160 = 12,5), och utdraget markerar försäkringen som ej beräknad |
| 3 | lokalt | En begäran efter fristen ger förslag på nästa möjliga månad. Bekräftelsen är en ny begäran |
| 4 | lokalt | Tidsbegränsad med 60 rätter godkänns, 59 avslås |
| 5, 6, 10 | lokalt | Paus efter 12 av 60, förlängning och golvet för livsvarig del, som indikativ beräkning |
| 7 | lokalt och `svc_test` | En delning 30/70 i stängningen bevarar C och G. Andelen 5 % och en fjärde del avslås |
| 8 | lokalt | Uttag före 66 blockeras med ärende |
| 9, 11 | lokalt | M är max av G och B, inte summan. Garantigolvet avrundas uppåt |
| Overifierat och passerat 66 | lokalt | Ett ärende `payout_review` per person, en gång. Sparandet stängs |
| Utan steg 4:s tabeller | lokalt | Stängningen beter sig som i steg 3 |
| Migrationen | `svc_test` | Från läget efter steg 3, med november stängd, blir resultatet identiskt med `create_all`. Den är idempotent, och delvis infört stoppar. Paket A:s testbestånd i Postgres ger garantidelar med `plan_id` och en delning med kapital |
| Före migrationen | lokalt, 2026-11-22 | På en databas byggd med main:s kod (utan steg 4:s tabeller och kolumn) ger main:s och branchens kod samma granskningssumma för november, samma verifikation, samma 20 poster och 8 garantidelar och samma ärenden. Det gäller också med två ägare som fyllt 66 |
| Befogenheter | lokalt | Agenter nekas alla fem operationerna, och systemaktören de skrivande |

Körskripten är provade på en lokal SQLite-kopia med dagen satt till 2026-12-01:
- `survey.py` för november visar fall 1:s standardstart och ett ärende för den som passerat 66;
- efter novembers stängning stoppar `survey.py` för december, som väntat;
- `verify.py` ger 5 av 5 både före och efter stängningen.
Kontrollerna som bara gäller Postgres (migrationens läge, kolumner, agenträttigheter och radantal mot backupen) prövas först i Lakebase.

## Avvikelser

Se designstoppet §5.4. I korthet:
- standardplanen sparas inte i steg 4;
- paus och förlängning av startade delar är bara indikativa;
- delning av en del med planbaserad garanti blockeras;
- M vid uppskov räknas om vid den verkliga starten;
- premie utan mottagande del täcks av `salary_file_deviation`;
- den nya ärendetypen `payout_review` för systemets egna fynd vid 66 ligger utanför §10:s lista; `payout_hindrance` (utbetalningshinder) byggs i steg 6.

## Körordning i Lakebase (val V11)

Varje steg kräver Karls separata OK i chatten och samordning enligt AGENTS.md §4.5.

1. **Före allt:** novembers stängning är bokad och `paket_b_steg3/verify.py` godkänd (tidigast 2026-12-01). Steg 4 är redan mergat (B-052).
2. Kör översikten `python scripts/simulation/paket_b_steg4/survey.py` (bara läsning). Lakebase har ingen som passerat 66 (V6), så den väntas visa noll sådana ärenden. Läs standardstarterna: en ägare som fyller 66 i stängningsmånaden blockerar den till steg 5.
3. Ta en backup med `scripts/maintenance/backup_database.py`.
4. Torrkör `python scripts/migrations/migrate_payout_plans.py`.
5. Kör `--apply --backup backups/<mapp>` (**OK**).
6. Kontrollera med `python scripts/simulation/paket_b_steg4/verify.py --backup backups/<mapp>`. Det är bara läsning.
