# Skill: aktuariell annuitet och garantidelar

> **Implementation:** `src/skills/calculation/actuarial_annuity.py` | **Tester:** `tests/test_actuarial_annuity.py`
> **Status:** 🟢 Implementerad som ren beräkning (A5, B-042). Ingen podd ännu: värderingsmotorn (A6) och
> startbeståndet (A5 del 2) använder den i betrodd kod, och podden `aktuariell` monteras med A6.

## Syfte

Räknar dödsrisker, annuitetsfaktorer och garantidelar enligt den aktuariella grunden
(`01_domän/aktuariell_grund.md` §2–4). Grundens parametrar kommer ur antagandebiblioteket
(`valuation_bases`, schemat `Mortality`). Samma motor används för garantitariffen (SIM-G,
SIM-HIST), utbetalningsgrunden (SIM-B), riskgrunden (SIM-R) och värderingsgrunden (SIM-V).

## Funktioner

| Funktion | Vad den ger |
|---|---|
| `annual_q`, `monthly_q` | Årlig och månatlig dödsrisk för ålder (fyllda år vid månadens första dag) och kalenderår, med förbättring, marginal och svans över 100 år |
| `annuity_factor` | A(t, D) för en plan: start, antal betalningsmånader eller livsvarigt, pausmånader och nettoränta. Livsvarig plan med exakt geometrisk svans |
| `guarantee_part` | G_j = P_j / A_g(t_j, livsvarigt från 66-årsmånaden), med referensstart enligt §4 |
| `MortalityBasis.scaled` | Samma grund med dödsrisken multiplicerad, t.ex. PR-028:s stress |

## Kontroller

- Dödlighetstabellen läses ur `01_domän/parametrar/DODLIGHET_SCB_2025.md` och prövas mot sin
  dokumenterade kontrollsumma (LEVERANSKONTROLL.md §2). En ändrad tabell stoppar beräkningen.
- Testerna återger leveranskontrollens facit (§3) på alla angivna decimaler:
  - månadsrisk, 0,0474694047 %;
  - A för 60 månader, 59,019956697;
  - A för livsvarigt, 293,440405905;
  - stressad A, 316,675957776;
  - omräkningarna efter tolv rättigheter;
  - garantidelen med väntetid, 347,157063780 och 2,880540552.
- Flyttal med dubbel precision. Anroparen avrundar belopp enligt PR-009.

## Gränser

Ingen data hämtas och inget skrivs. Diskontering med räntekurva (SIM-V) kommer med
värderingsmotorn (A6); i dag tar motorn en konstant nettoränta.
