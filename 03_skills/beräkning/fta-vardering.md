# Skill: FTA-värdering – garanterat åtagande, villkorad återbäring och underskott

> **Implementation:** `src/skills/calculation/fta_valuation.py` (beräkningen), `src/services/valuation.py`
> (körningen i betrodd kod) och `src/services/operations/valuations.py` (operationerna) |
> **Tester:** `tests/test_fta_valuation.py`, `tests/test_valuation_runs.py` | **Diagnos:**
> `scripts/diagnostics/valuation_summary.py`
> **Status:** 🟢 Byggd och testad lokalt (A6, B-042). Kontrollfallen K1–K10 körs automatiskt. Tabellerna
> är inte införda i Lakebase.

## Syfte

Värderar bolagets garanterade åtagande för ITP1 ålderspension per försäkring och datum enligt
värderingskontraktet (`projekt/06_avdelningsfunktioner/VARDERINGSKONTRAKT.md` §3–4). FTA, pensionskapitalet
`C` och produktens garantivärde hålls isär.

```text
FTA_i = Σ_j G_ij × a_V(t, D_i) + K_i(t)
VÅ_i  = max(0, C_i − FTA_i)       villkorad återbäring
U_i   = max(0, FTA_i − C_i)       underskott till följd av garanti (PR-ITP1-028)
```

## Metod

| Del | Hur |
|---|---|
| Garantidelar `G_ij` och kapital `C_i` | Ur datautdraget S-04 ([kapitalavräkning](kapitalavrakning.md)); värderingen ändrar dem aldrig |
| Plan `D_i` | Referensplanen livsvarigt från 66-årsmånaden, samma för alla delar i v1 |
| Dödlighet | SIM-V:s modell ([aktuariell annuitet](aktuariell-annuitet.md)), i v1 densamma som garantins |
| Diskontering | Spotkurvan i FI-SIM med linjär interpolation och platt extrapolation: `v(t, n) = (1 + r_⌈n/12⌉ − s_y)^(−n/12)`, n månader till slutet av betalningsmånaden |
| Skatt `s_y` | Årets kundbelastning `customer_tax_rate` i `product_parameters` (15 % × max(SLR, 0,5 %), PR-ITP1-023); under grundens golv stoppar körningen |
| Driftkostnad `K_i` | 180 kr per år under uppskov och 240 kr under utbetalning, en tolftedel per månad med pensionens vikter och diskontering. Uppräkningen 2 % per år läggs på månadsvis: månad n får `1,02^(n/12)`, så nivån gäller vid värderingsdatumet |
| Precision | Dubbel precision i beräkningen, sex decimaler i lagringen, öre först i rapporteringen. Med lagrade belopp gäller `VÅ − U = ΣC − FTA` exakt |

Kurvdiskonteringen finns i `actuarial_annuity.DiscountCurve` och som parameter till `annuity_factor`.
Den livsvariga svansen räknas som geometrisk serie först där kurvan är platt; före det summeras
månaderna explicit. Med konstant nettoränta är beräkningen densamma som tidigare, så
leveranskontrollens facit består.

## Körning, lagring och lås

- **Bas eller scenario.** En basvärdering görs per kvartalsslut med SIM-V och kurvan som gäller
  datumet. Ett scenario får göras vid vilket månadsslut som helst och med uttryckligt angiven grund
  och kurva (kontraktet §2). Det märks och kan aldrig låsas.
- **`run_valuation`** bygger utdraget, stoppar på ett underkänt utdrag och sparar körningen som utkast:
  utdraget (`valuation_extracts`, en gång per kontrollsumma), grund, kurva och skatt med kontrollsummor,
  kodversion (motorns version och en hash av källkoden), totaler, segment och kontroller (`databasschema.md` §9k).
- **Segment** är läge × födelsedecennium. Celler med 1–9 försäkringar döljs, med kompletterande döljning mot
  totalen, och sparas utan belopp. Ej beräknade fall sparas per orsak.
- **`lock_valuation`** är bara för människa. Kontrollerna, utdragets och grundernas kontrollsummor prövas
  igen. En ny låsning för samma datum ersätter den gamla (`superseded`).
- **Agenten** läser bara aggregat (`list_valuation_runs`, `get_valuation_run` i podden `aktuariell`) och kan
  inte läsa utdraget.

## Kontrollfall (kontraktet §7)

| Nr | Prov |
|---|---|
| K1 | En premie på 1 000 kr, 40 år, 0 %-kurva, utan skatt och kostnad ger FTA 1 000,00 kr. Körs också i varje körning |
| K2 | 3 %-kurva ger mindre än premien och samma värde som en oberoende explicit summa. Skatten (M2) prövas mot en explicit skatteprojektion: exakt med motsvarande månadsskatt, under 0,1 % med `s/12` |
| K3, K4 | `C` 500 kr ger U = FTA − 500, och `C` 2 000 kr ger VÅ = 2 000 − FTA. Vid 40 år är FTA på 3 % ungefär 304 kr, så fallen räknas vid 60 år för att K3:s förutsättning ska hålla |
| K5 | IB för en period är den låsta UB:n för förra perioden, på öret och vid omräkning |
| K6 | Samma utdrag, grund och kod ger samma resultat och kontrollsummor |
| K7 | Segment med 1–9 försäkringar döljs, även kompletterande |
| K8 | Oanalyserat över 0,5 % av FTA ger `needs_human` (`unexplained_status`); stegen kommer med förändringsanalysen i A7 |
| K9 | Leveranskontrollens garantifall ger samma faktorer och `G` genom kurvvägen |
| K10 | `VÅ − U = ΣC − FTA` på öret för hela beståndet |

## Gränser

- Inga påbörjade uttag, deluttag, dödsfall eller optioner i v1; de listas som ej beräknade (kontraktet §2).
- K_i räknas per försäkring och kan ge underskott för små försäkringar. Nivån prövas i erfarenhetsanalysen (M3).
- Förändringsanalys, känsligheter och kassaflöden kommer i A7 och A9.
- Startgrunderna gäller först 2026-10-31 (FI-SIM) och 2026-12-31 (SIM-V), och avkastningsserien slutar
  2026-10. En provvärdering per 2026-09-30 är därför ett scenario.
