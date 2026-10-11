# PR-ITP1-001 – ordinarie premietrappa
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Avtalets trappa; eget avrundningsval.
**Källor:** K-ITP-AVTAL-2026, K-IBB-2026/HIST i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-001](../../04_regulatoriskt/tolkningar/T-ITP1-001-premietrappa.md).
**Villkor:** [§3 i v2.0](../försäkringsvillkor.md).

## Grund och indata

ITP avdelning 1 punkt 7.1, [T-001](../../04_regulatoriskt/tolkningar/T-ITP1-001-premietrappa.md).
Lön, premieår och behörighet enligt PR-012–014 måste vara fastställda.
Trappan räknas **en gång per person, arbetsgivare och kalendermånad**,
före fördelning mellan försäkringar. Olika arbetsgivare räknas var för sig.

## Regel

Med pensionsmedförande lön L ≥ 0 och årets IBB > 0:
```text
B1 = 7,5 × IBB / 12
B2 = 30 × IBB / 12
P_låg = round_half_up(0,045 × min(L,B1), 2)
P_hög = round_half_up(0,30 × max(0,min(L,B2)−B1), 2)
P = P_låg + P_hög
```
Gränser avrundas inte före beräkningen. Avrundning per lönedel är valt
bolagsbeteende, inte ett verifierat universellt Collectumkrav. Lön över
taket ökar inte ordinarie premie. Kompletteringar ligger utanför trappan.

## Utfall och kontrollfall

| Lön 2026 | Ordinarie premie |
|---:|---:|
| 0 | 0,00 |
| 35 000 | 1 575,00 |
| 52 125 | 2 345,63 |
| 52 125,05 | 2 345,65 |
| 80 000 | 10 708,13 |
| 208 500 eller 250 000 | 49 258,13 |

Spara lön, år, IBB, exakta gränser, satser, två delbelopp och total.
Saknat år/negativ lön är komplettering/rättelse enligt PR-019, ingen
reservparameter eller negativ ny premie. Beräknad premie är en fordran,
inte mottaget kapital. Allokering och netto följer PR-015/018.

Befintlig [beräkningsfunktion](../../src/skills/calculation/calculate_itp1_premium.py)
beskriver delar av denna regel. Paketets hela flöde är inte implementerat.
