# Parameterregister – produktpaket v1.0

> Dokumentdatum 2026-10-11. Beloppens år och tariffens giltighet är skilda saker.
> SIM betyder eget simuleringsantagande, inte myndighets- eller branschtariff.

## Avtals- och skatteparametrar

| År | IBB kr | 7,5 IBB/12 kr | 30 IBB/12 kr | Genomsnittlig SLR året före | Kundbelastning avkastningsskatt/år |
|---|---:|---:|---:|---:|---:|
| 2023 | 74 300 | 46 437,50 | 185 750 | 1,46 % | 0,2190 % |
| 2024 | 76 200 | 47 625 | 190 500 | 2,48 % | 0,3720 % |
| 2025 | 80 600 | 50 375 | 201 500 | 2,15 % | 0,3225 % |
| 2026 | 83 400 | 52 125 | 208 500 | 2,36 % | 0,3540 % |

Sista kolumnen är `15 % × max(SLR, 0,5 %)`. Den används för bolagets
månadsvisa kundbelastning enligt PR-023; bolagets verkliga skatteunderlag
beräknas separat. [Skatteverkets SLR-historik](https://www4.skatteverket.se/rattsligvagledning/edition/2025.2/341469.html),
[SLR 2024, SKV A 2025:1](https://www4.skatteverket.se/download/18.af8c508193bf21a0a6a369/1736323421343/SKV%20A%202025_1.pdf),
[SLR 2025, SKV A 2026:1](https://www4.skatteverket.se/rattsligvagledning/edition/2026.13/468722.html)
och [IBB 2026](https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/forordning-20251002-om-inkomstbasbelopp-for-ar_sfs-2025-1002/).
IBB-historiken ska läsas tillsammans med K-IBB-HIST i källregistret.

Ordinarie premiesatser är 4,5 % respektive 30 %. Ordinarie premieålder är
25-årsmånaden till månaden före 66 år; ordinarie pensionsstart 66-årsmånaden
för start från 2023. Frivillig 66–67-premiegren gäller i paketet från 2026.

SINK: 25 % för betalningar 2023–2025, 22,5 % 2026 och beslutad 20 % från
2027. Giltigt myndighetsbeslut, skatteavtal och eventuella undantag har
företräde. Svensk sidoinkomst: 30 % preliminärt avdrag. Huvudinkomst använder
årets tabell och rätt pensionskolumn, eller myndighetsbeslut; ingen
påhittad kommunalskatt används. [Skatteverkets SINK-information](https://www.skatteverket.se/privat/skatter/arbeteochinkomst/internationellainkomster/bosattutomlands/sinksarskildinkomstskattforutomlandsbosatta.4.6fdde64a12cc4eee23080002583.html).

## Valda simuleringsparametrar

| Parameter | Val | Motivering/ägare |
|---|---|---|
| Produkt | Traditionell ITP1 ålderspension, SEK, utan efterlevandeskydd | B-002/B-021 |
| Garantigrundande andel | 100 % mottagen nettopremie | B-027 |
| Garanti- och utbetalningsränta | 0 % effektiv nettoränta | B-027 för garanti; eget försiktigt val för utbetalning |
| Kapitalavgift | 0,20 % nominellt per år, 1/12 varje månad | B-021; bas enligt PR-022 |
| Fast avgift, premieavgift, riskpremie | 0 kr | Inga sjuk-/efterlevanderisker i produkten |
| Paus-/förlängningsavgift | 0 kr | ITP-flexibilitet |
| Valcentralsavdrag i intern simulering | 0 kr | B-021; verkligt nettoflöde kan importeras separat |
| Unisexvikt | 50 % män, 50 % kvinnor | Eget neutralt modellval, samma för alla individer |
| Basstatistik | SCB ettårig livslängdstabell 2025, ålder 0–100 | [Låst tabell](DODLIGHET_SCB_2025.md), innehållskod BE0101A¤ |
| Årlig dödlighetsförbättring | 1,5 % lägre dödsrisk per kalenderår efter 2025, t.o.m. ålder 100 | Eget scenario, inte SCB-prognos |
| Livslängdsmarginal i garanti/utbetalning | Dödsrisk multipliceras med 0,80 | Egen försiktighetsmarginal, inte kalibrerad försäkringstariff |
| Riskgrund arvsvinst | Samma bas/förbättring men utan 0,80-marginal | Aktuell exponering, skild från låst garanti |
| Svans över 100 år | 10 % årlig ökning av dödsintensiteten, tak q = 0,995 | Explicit oändlig svans; se aktuariell grund |
| Start före ordinarie ålder | Tidigast månaden efter 55-årsmånaden | Eget månadsval inom ITP:s 55-årsram |
| Tidsbegränsad första plan | Minst 60, valfritt helt antal betalningsmånader | Ingen egen övre tidsgräns |
| Deluttag | Högst 3 uttagsdelar per ursprunglig försäkring, minst 10 % vid varje delning | Eget produktutbud; inga gränser för antalet försäkringar per person |
| Ansökningsfrist | Senast sista kalenderdagen föregående månad | Eget administrativt villkor |
| Paus | Minst 1 hel månad, bestämd återstart; kan upprepas | Eget genomförande av avtalsrätten |
| Beloppsomräkning | Start, återstart, planändring och varje januari | Eget bolagsval |
| Utbetalningsbart garantigolv | Summan G avrundad uppåt till öre; positiv rätt minst 0,01 kr | Eget avrundningsskydd; G_j bevaras i hög precision |
| Utbetalningsdag | Första svenska bankdagen efter pensionsmånaden | Eget villkor; stängd månad före bankuppdrag |
| Prognos, nominell bruttoavkastning | Låg 0 %, bas 3 %, hög 5 %; kostnad/skatt separat | Scenarier, ingen utfästelse eller avkastningstransaktion |
| Initialt riskkapital i nytt simuleringsscenario | Enligt PR-028:s stressformel | Verklig separat finansieringskälla inom scenariot |

Garantitariff **SIM-G-2026-01**, utbetalningsgrund **SIM-B-2026-01** och
arvsvinstgrund **SIM-R-2026-01** gäller för nya händelser från föreslagen
simuleringsdag 2026-11-01. SIM-B använder samma dödlighet som SIM-G.
Gammal garantidel behåller alltid sin egen tariffversion.

**SIM-HIST-2023-01** tillåts enbart för uttryckligen omgenererad mockhistorik
2023-01–2026-10 och har samma antaganden som SIM-G. Användning av 2025-statistik
i äldre mockår är ett retrospektivt simuleringsval och ger inte anspråk på
historisk marknadstariff. Importerad historik får aldrig fyllas med denna
grund utan uttryckligt rekonstrueringsbeslut.

## Parameterändring

Varje post/version lagrar värde, enhet, syfte, giltighetsintervall, källa,
kontrolldatum och beslut. Aktuariella grunder sparar även full tabell,
formelversion och kontrollsumma. Publicerad framtida lagändring får ett eget
framtida intervall. Saknade årsparametrar blockerar bara berörd beräkning.
Avkastning för en månad är observerad indata från förvaltningen, inte en
stående parametersats. Kalendrar och skattetabeller är versionsstyrd indata.
