# PR-ITP1-001 – ordinarie premietrappa

> **Version:** 0.1 | **Granskningsstatus:** Utkast | **Ägare:** Operatören
> **Implementationsstatus:** Implementerad som befintlig beräkningsfunktion; fullständigt premieflöde ingår inte
> **Upprättad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Period som källkontrollen avser:** Premiemånader 2026-01–2026-12
> **Ursprung:** Extern avtalsregel för trappan; eget implementationsval för avrundning

## Källor och tolkning

- [Källregister](../../04_regulatoriskt/kallregister.md): K-ITP1-2026 och K-IBB-2026.
- [T-ITP1-001](../../04_regulatoriskt/tolkningar/T-ITP1-001-premietrappa.md): formel, beräkningsnivå och avrundningsval.
- [ITP1-regelverk](../ITP1_regelverk.md) §2 och §6: befintlig domänsammanställning.
- [Försäkringsvillkor](../försäkringsvillkor.md) §3.2: befintlig villkorskoppling.

## Förutsättningar och avgränsning

Regeln beräknar ordinarie bruttopremie för ITP1 ålderspension för en given
pensionsmedförande månadslön. Anroparen ska ha fastställt personens rätt till
premie för månaden och löneunderlaget. Ålder, anställning och vilka lönedelar
som ingår är separata regelområden. Ålderskontroll finns som valfri kontroll i
funktionen; den ersätter inte anroparens ansvar för övriga förutsättningar.

Regeln beräknar ingen valcentralsavgift, kompletterande premie, riskpremie,
löneskatt eller kapitalavgift. Fördelning mellan försäkringar/förmåner enligt
B-022 återstår att specificera och får inte leda till dubblerad premie.

## Indata

| Parameter | Krav |
|---|---|
| `L` | Pensionsmedförande månadslön i kronor, minst noll |
| `IBB` | Positivt inkomstbasbelopp för premiemånadens år; 83 400 kronor för 2026 |
| Premiemånad | Kalenderperiod som styr årsparametern; hämtningen görs av anroparen |

Saknad årsparameter ska utredas innan premien beräknas; användning av ett annat
års belopp är inte en godkänd reservregel. Funktionen får IBB som indata och
validerar inte själv årskopplingen.

## Regel och utfall

Låt `B1 = 7,5 × IBB / 12` och `B2 = 30 × IBB / 12`.

```text
låg del   = 0,045 × min(L, B1)
hög del   = 0,30 × max(0, min(L, B2) − B1)
```

Lön över `B2` ökar inte den ordinarie premien. Noll lön ger noll premie.
Negativ lön avvisas av funktionen; korrigeringar behöver ett separat flöde.

**Befintligt avrundningsval, under granskning:** Avrunda varje delbelopp till
två decimaler med ROUND_HALF_UP och summera de avrundade delarna. Räkna med
Decimal. Beräkningsgränserna härleds utan föregående avrundning.

Utfallet är låg del, hög del och total premie samt beräkningsunderlag med
lön, IBB, gränser och satser. Ett beräknat belopp är inte i sig en mottagen
betalning eller en kapitaltransaktion.

## Acceptansfall för befintligt beräkningsval

IBB = 83 400 kronor, B1 = 52 125 kronor och B2 = 208 500 kronor.

| Lön, kronor | Låg del | Hög del | Total premie |
|---|---|---|---|
| 0 | 0,00 | 0,00 | 0,00 |
| 35 000 | 1 575,00 | 0,00 | 1 575,00 |
| 52 125 | 2 345,63 | 0,00 | 2 345,63 |
| 52 125,05 | 2 345,63 | 0,02 | 2 345,65 |
| 80 000 | 2 345,63 | 8 362,50 | 10 708,13 |
| 208 500 | 2 345,63 | 46 912,50 | 49 258,13 |
| 250 000 | 2 345,63 | 46 912,50 | 49 258,13 |

Negativ lön eller IBB ≤ 0 ska ge fel. Fallet 52 125,05 visar varför
avrundningsmetoden behöver ett uttryckligt ställningstagande.

## Implementation och verifiering

- [Premiemotor](../../src/skills/calculation/calculate_itp1_premium.py): `calculate_itp1_premium`, `RATE_LOW`, `RATE_HIGH`, `BREAKPOINT_LOW_IBB`, `BREAKPOINT_HIGH_IBB`.
- [Skillbeskrivning](../../03_skills/beräkning/beräkna-itp1-premie.md).
- [Befintliga tester](../../tests/test_calculate_itp1_premium.py): `TestPremieTrappan`, `TestFelhantering` och `TestSparbarhet`.
- Befintliga tester täcker flera exempel och parameterbyte. Tabellen ovan innehåller även granskningsfall som inte har egna testmetoder.
- Verifiering av källor: 2026-10-11. Teknisk kontroll av utkastets exempel redovisas i sessionsrapporten.

Satserna är konstanter i dagens kod. Regel-ID/version lagras ännu inte i
`calculation_basis`. Dokumentkedjan ger en första hänvisning, men ersätter
inte framtida versionsspårbarhet för varje beräkning.

## Giltighet och öppna frågor

Detta utkast beskriver befintligt beteende för 2026. Det ändrar inga äldre
premier och fastställer inget nytt ikraftträdandedatum för villkoren.
Historik 2023–2025, exakt avtalsreferens, avrundning, nettoinflöde och
fördelning mellan försäkringar behöver kompletteras enligt T-ITP1-001.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första provregel; dokumenterar befintlig kod |
