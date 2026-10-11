# T-ITP1-007 – skattebärare och betalningsanspråk

> **Version:** 1.0 | **Status:** Dokumenterad egen tolkning och vald tillämpning i PR-ITP1 v1.0.
> **Källkontroll:** 2026-10-11 | **Ägare:** Operatören. Införande/extern professionell validering separat.


K-IL-UTTAG-2026, K-AVPL, K-SKV-SLR, K-SKV-PENSION, K-SKV-SINK,
K-SFF, K-SFL, K-SKV-TABELL-2026, K-SKV-RANTA och K-RANTA är kontrollerade i [registret](../kallregister.md).

Tre flöden hålls isär: arbetsgivarens pensionskostnad/löneskatt,
bolagets avkastningsskatt och mottagarens inkomstskatt på pension.
Vår månatliga kundbelastning s×öppningskapital är ett villkorsval;
den är inte bolagets lagstadgade årsdeklarationsformel.
2026 års s=0,354 % bygger på genomsnittlig SLR 2025=2,36 %.

Pensionens preliminära avdrag följer verklig betalningsdag och giltigt
beslut/tabell/utbetalarroll. SINK kräver beslut; adress räcker inte.
KU18/19 med kod 400 används för individuppgifter från pensionsförsäkring.
AGI:s utbetalartotal är separat; samma pension rapporteras inte dubbelt
som individuell AGI och KU. Avdrag avrundas enligt SFF 22 kap. 1 §,
inte pensionsbeloppets öresregel. Retroaktiva särskilda utbetalningar
skatteklassificeras, inte göms som ny vanlig månadsrätt.

Småbeloppsgränsen gäller utbetalarens samlade ersättning till personen,
inte varje försäkringsdel. För svensk A-skatt är gränserna strikt mindre
än 100 kr per ersättning respektive förväntad årsutbetalning mindre än
1 000 kr. SINK kräver egen gren. Pensionskolumn 2026 är 2 för födda
1959 eller tidigare, annars 6. Saknad kundtabell kan kräva förhöjt avdrag
enligt SFL, inte en obegränsad väntan på kundens komplettering.

Månadsrätt, finansiering och bankförsök är olika händelser. Bankfel ger
ingen ny rätt eller skatt på en betalning som inte verkställts.
Laglig dröjsmålsränta vid bolagets dröjsmål är bolagskostnad, inte C-debit.
Mottagarens ränteinkomst och KU20-/avdragsgren prövas separat från pensionen,
inte som KU18/19 eller automatiskt med pensionens SINK-sats.
Beloppsgolv/grenarna i IL 11/11 a/11 b preciseras i PR-009.
PR-023/026/027 och §11 i villkoren är resultatet.
