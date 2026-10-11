# T-ITP1-001 – premietrappa och beräkningsnivå

> **Version:** 1.0 | **Status:** Dokumenterad egen tolkning och vald tillämpning i PR-ITP1 v1.0.
> **Källkontroll:** 2026-10-11 | **Ägare:** Operatören. Införande/extern professionell validering separat.


ITP avdelning 1 punkt 7.1 styr trappan, inte ett bolags allmänna exempel.
K-ITP-AVTAL-2026, K-IBB-2026/K-IBB-HIST och K-ITP-LON i
[källregistret](../kallregister.md) är kontrollerade.

Vi tolkar månadslön som en samlad pensionsmedförande rapport per
person/arbetsgivare/månad. Att B-022 tillåter flera försäkringar
förändrar inte arbetsgivarens ordinarie premie på samma lön.
Det förhindrar att trappan räknas flera gånger. Fördelning sker därefter.

Avrundning av respektive lönedels premie med ROUND_HALF_UP är bolagsval
som bevarar befintlig motor. Ingen universell administratörsavrundning
har kunnat beläggas och behövs inte som antagande för vår egen simulering.
2023-gränsen är exakt 46 437,50 kr, inte avrundade 46 438 vid beräkning.

Utfallet är PR-001, PR-013–015 och PR-032. F-001/002/006/007 i
arbetsfrågorna är lösta för det dokumenterade simuleringspaketet.
Importerad verklig premiehistorik behåller sin källavrundning; vid
avvikelse dokumenteras skillnaden, inte tyst ersättning.
