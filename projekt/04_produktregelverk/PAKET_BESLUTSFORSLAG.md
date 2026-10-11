# Samlat införandeförslag – produktpaket PR-ITP1 v1.0

> **Datum:** 2026-10-11 | **Status:** Fullständigt förslag för operatörens samlade införandebeslut.
> Egna produktval är utarbetade på sessionens mandat. Ingen post har skrivits i BESLUTSLOGG.

## Föreslagen beslutstext

”Artificiellalectas produktunderlag för traditionell ITP1 ålderspension
fastställs som produktpaket PR-ITP1 v1.0 med regler 001–034,
försäkringsvillkor v2.0, aktuariell grund v1.0 och tillhörande parameterregister.
B-002/B-003/B-021/B-022/B-027 består. Endast ålderspension utan
efterlevandeskydd erbjuds.

Paketet väljer SIM-G-2026-01, SIM-B-2026-01 och SIM-R-2026-01:
SCB:s dödsrisker 2025, unisex 50/50, 1,5 % årlig förbättring och
20 % extra livslängdsmarginal för garanti/utbetalning, noll nettoränta
och explicit oändlig högålderssvans. Grunderna är bestämda simulerings-
antaganden och påstås inte vara professionellt kalibrerade marknadstariffer.

Intjänad garanti följer B-027 och varje historisk garantidel behåller sin grund.
Uttagsplanen kan ändras med värdebevarande omräkning, inom angivna
avtals-/skattebegränsningar. Kapital, garanti, betalningsskuld, faktisk
arvsvinstpool och bolagets egna finansiering särredovisas.

Paketet föreslås gälla nya produktbeslut i simuleringen från 2026-11-01,
efter erforderligt införandebeslut och senare teknisk driftsättning.
Dokumenten skriver inte om äldre transaktioner. Importerad rätt
bevaras med sin ursprungsgrund. SIM-HIST används endast vid separat,
uttryckligt beslutad omgenerering av ett märkt syntetiskt scenario.

Dokumentunderlaget färdigställer delprojektets produktutredning.
Programimplementation, koppling till automatiserade tester samt full
företags-/risk-/tillståndsvalidering genomförs i respektive senare session
och verksamhetsprojekt. Ingen verklig produkt lanseras genom detta beslut.”

## Produktval som omfattas av förslaget

| Val | Precisering |
|---|---|
| Premie | Trappa en gång per person/arbetsgivare/månad; delavrundning till ören; faktiskt netto ger kapital/garanti |
| Avtal och komplettering | Verifierad anslutning, slutlönsprövning, dokumenterad komplettering; erbjudande 66–67, inga 67+-lösningar |
| Kapitalmodell | Månadsvis faktisk avkastning, 0,20 % kapitalavgift och egen skattebelastning; ingen utjämningsreserv eller dold kostnad |
| Tidigt/sent uttag | Tidigast månaden efter 55, pensioneringsprövning före 66, livsvarig standard 66; inget 70-tak |
| Deluttag | Högst tre delar per ursprungsförsäkring, 10 %-gränser vid delning; kapital och historiska garantidelar följer delarna |
| Tidsbegränsat/livsvarigt | Minst 60 betalningsmånader, valfritt längre helt antal; ingen förkortning efter start eller livsvarigt → tidsbegränsat |
| Paus/förlängning | Hela månader/delar, upprepning, bestämd återstart; noll särskild avgift/hälsoprövning |
| Beloppsbeslut | Start/januari/återstart/planändring; garantigolv uppåt till öre och eget starkare livsvarigt golv första 60 rättigheter |
| Betalning | Första bankdagen efter pensionsmånaden, verifierad mottagare; ett anspråk trots upprepade bankförsök |
| Skatt | Betalningsår, myndighetsbeslut, A-/SINK-/engångsgren, summering mellan delar och hela kronor för avdrag |
| Sista månad | Hela återstående kapitalet inom sista planbetalningen, minst beslutat belopp; bolaget finansierar brist |
| Dödsfall | Giltig ej pausad pension hela dödsmånaden, även vid ny start/återstart på dödsdagen; gamla anspråk separat |
| Arvsvinst | Bara faktiskt frigjort kapital, hel månads exponering, aktuell SIM-R-vikt, centbevarande; ingen ny garanti |
| Finansiering | Separat bokförd ägarinsättning, stress-/likviditetsbuffert och faktisk kapitalöverföring; inget påhittat kundkapital |
| Rättelse/klagomål | Spårbara motposter, människa vid negativ rättelse/återkrav, bevarade rättsliga tidsfrister |
| Information/behörighet | Besked, prognos, ändringsinformation, minimerade personuppgifter och verifierad fullmakt |
| Begränsat erbjudande | Ingen flytt/återköp/privat insättning; rättsliga specialfall prövas, inga andra riskprodukter |
| Tvärgående krav | Korrekt kollektiv tillämplighet, SFDR-grundupplysningar och gränssnitt för DORA/GDPR/AI-verksamhetsarbete |

Detta är en läsöversikt. Vid detaljfråga gäller [hela regelpaketet](../../01_domän/produktregler/README.md),
[villkor](../../01_domän/försäkringsvillkor.md), grunder och parametrar tillsammans.
[Leveranskontrollen](LEVERANSKONTROLL.md) visar beräknade resultat och gränssnitt.

## Registrering efter godkännande

Operatörens beslut registreras med ledigt B-nummer, godkännandedatum,
beslutad produktdag, paket-/dataversion och eventuell övergångsändring.
Det ska vara möjligt att anta hela paketet och sedan driftsätta det i
byggsessionen utan att godkänna varje PR-fil separat.
