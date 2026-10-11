# T-ITP1-004 – garanti och aktuariell modell

> **Version:** 1.0 | **Status:** Dokumenterad egen tolkning och vald tillämpning i PR-ITP1 v1.0.
> **Källkontroll:** 2026-10-11 | **Ägare:** Operatören. Införande/extern professionell validering separat.


B-027 bestämmer garanti för hela mottagna nettopremien och nettoränta
0 %, utan automatisk garantiförstärkning. Premiebestämdhet utesluter
inte garanti. K-ITP-SPARFORM och K-GARANTI-ALECTA/AMF är jämförelser;
ingen allmän bindande ITP-tariff har identifierats.

LTF 9 kap. 4–5 §§ och FFFS 2019:21 8 kap. 30–31/36–38 §§ ger ram för
dokumentation av tekniska principer/underlag. De föreskriver inte vår
konkreta dödlighet, ränta, fördelningsformel eller kostnadsmodell.

Vi väljer i [aktuariell grund](../../01_domän/aktuariell_grund.md) en
komplett reproducerbar **SIM-modell**: SCB 2025, 50/50 unisex,
årlig förbättring 1,5 %, 20 % lägre dödsrisk i garanti/utbetalning,
0 % nettoränta och explicit oändlig högålderssvans.
SCB-koden är BE0101A¤; tidigare BE0101AW var fel kod (risktid).
Valda marginaler är försiktighets-/scenarioantaganden, inte professionellt
kalibrerad försäkringstariff eller skuldvärdering.

Garantidelarnas historiska grunder låses. Ändrad plan omräknas med
värdebevarande kvarvarande rätt, marknadsfall gör inte det.
C, G och V_g har skilda betydelser. PR-028 visar finansiering och
spärr vid brist; att sätta M=G skapar inga tillgångar.

PR-008/009/020–023/028 och parameterregistret är specificerat utfall.
Professionell bestånds-/solvensvalidering före verklig drift hör till
aktuariell/riskfunktion, inte till denna simuleringsspecifikations status.
