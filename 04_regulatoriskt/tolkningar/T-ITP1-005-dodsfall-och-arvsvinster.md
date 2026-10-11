# T-ITP1-005 – dödsfall och faktiska arvsvinster

> **Version:** 1.0 | **Status:** Dokumenterad egen tolkning och vald tillämpning i PR-ITP1 v1.0.
> **Källkontroll:** 2026-10-11 | **Ägare:** Operatören. Införande/extern professionell validering separat.


ITP 7.5 anger pension längst under dödsmånaden. Produkten saknar
återbetalningsskydd enligt B-002/B-021. Ett redan uppkommet obetalt
anspråk är något annat än efterlevandeskydd eller återstående kapital.

Vår tillämpning ger hela dödsmånaden på en pågående ej pausad del.
Pausad del ger ingen ny rätt. Ny första start/återstart hindras när
dödsdatum är före startmånadens första dag. Datum samma dag räknas
kundgynnande som en uppkommen rätt, eftersom underlaget saknar klockslag.
Detta ger samma dödsmånadsprincip utan ett särskilt första-dagen-avslag.
Datumkonventionen är egen och framgår av villkoren. Verifierat datum och rapportdatum
bevaras, även när underrättelsen kommer sent.

Efter avräkning av obetalda rättigheter förs faktiskt återstående C
till pool. Frigjort V_g/skuld tillför inga extra pengar.
Vi väljer ett kollektiv, månadsvis faktisk fördelning och riskvikten
C_öppning × q/(1−q) för levande hela-månadsmedlemmar, inklusive fribrev/
paus. Grund/småbeståndsbuffert är explicit SIM-val, inte branschformel.
Sena rättelser finansieras spårbart utan tyst negativ kundtilldelning.

K-DODSFALL-ALECTA är bolagsjämförelse, K-FFFS-PENSIONSBESKED anger
redovisningsramen. PR-010/011/019/028 är utfallet.
[Källregister](../kallregister.md).
