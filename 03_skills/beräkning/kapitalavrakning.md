# Skill: kapitalavräkning och datautdrag S-04

> **Implementation:** `src/skills/calculation/capital_rollforward.py` (avräkningen) och
> `src/services/valuation_extract.py` (datautdraget) | **Tester:** `tests/test_capital_rollforward.py`,
> `tests/test_valuation_extract.py` | **Diagnos:** `scripts/diagnostics/s04_extract_summary.py`
> **Status:** 🟢 Implementerad i betrodd kod (A5 del 2, B-042 val L). Ingen podd: värderingsmotorn (A6)
> bygger utdraget som systemsteg i `valuation_close`, och agenten ser bara aggregat.

## Syfte

Rekonstruerar startbeståndet S-04 enligt värderingskontraktet (`VARDERINGSKONTRAKT.md` §5): varje
försäkrings garantidelar `G_j` och pensionskapital `C` vid ett månadsslut, ur premiehistoriken
och antagandebiblioteket. Utdraget är det som värderingen och förändringsanalysen räknar på, och
märks `reconstructed_s04` tills paket B ersätter det med bokförda värden.

## Avräkningen (PR-ITP1-020–023)

Varje månad, för hela kollektivet:

| Steg | Regel | Beräkning |
|---|---|---|
| Avkastning | PR-021 | Kollektivets resultat `round_half_up(Σ C_öppning × r)` fördelas i ören efter `C_öppning`, största bråkrest |
| Kapitalavgift | PR-022 | `round_half_up(C_öppning × 0,002/12)`, högst kapitalet efter avkastning |
| Skattebelastning | PR-023 | `round_half_up(C_öppning × s_y/12)` med årets sats ur parameterregistret, högst kapitalet efter avgift |
| Premier | PR-020 steg 4, PR-018 | Betalmarkerade premier tillförs vid mottagningsmånadens slut och får avkastning först nästa månad |

Det som inte kan debiteras avstås av bolaget och redovisas som avstått. Arvsvinst och
pensionsdebitering ingår inte: beståndet har inga dödsfall eller påbörjade uttag, så poolen är noll.

## Datautdraget

- **Garantidelar:** en del per betalmarkerad premie eller positiv justering, med premiens id
  som spår. `G_j = P_j / A_g` vid mottagningsmånadens slut på den garantigrund som gäller då
  (SIM-HIST-2023-01 till och med 2026-10, SIM-G-2026-01 därefter), med `guarantee_part`.
- **Pensionskapital:** rullas fram från 2023-01 med avkastningsserien `AVK-SIM-2026-01`. Kapital
  före 2023 finns inte i beståndet.
- **Ålder:** utdraget har födelsemånaden och om personen är född den första. Det är allt av
  födelsedagen som påverkar åldern vid månadens första dag, så garantin blir exakt utan att
  födelsedatumet följer med.
- **Ej beräknat:** påbörjat eller pausat uttag (PR-009), avslutad försäkring med premier
  (PR-027) och negativ premierad (återtag enligt PR-019) listas med orsak och ingår inte i
  kollektivet.

## Kontroller

- Produktreglernas kontrollfall: PR-020 (100 000 kr, 1 %: +1 000, 16,67 och 29,50), PR-021
  (−100/−200), PR-022 (noll kapital och −100 %), PR-023 (negativ avkastning, saknat år) och
  fördelningen i ören i PR-011.
- Skattesatserna och kapitalavgiften prövas mot `PARAMETERREGISTER.md`.
- Utdragets kontroller enligt kontraktet §5.3: antal försäkringar, premiesumma mot beståndet,
  fullständiga uppgifter, premiehistorik, inga negativa belopp, kända grunder och
  kapitalavstämning. En underkänd kontroll ger `approved = False`.
- Ett handräknat bestånd i testerna och samma kontrollsumma för samma bestånd (K6).
- Saknad avkastning, saknad årssats eller ändrad grund blockerar utdraget.

## Gränser

Utdraget sparas inte; samma bestånd, grunder och kod ger samma kontrollsumma, och A6 sparar
körningen med utdragets kontrollsumma. Utdraget innehåller individrader och lämnar aldrig betrodd
kod. Diagnosskriptet skriver bara aggregat.
