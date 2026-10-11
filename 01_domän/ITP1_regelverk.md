# ITP1 – avtalsram för vår ålderspension

> **Version:** 2.0 | **Källkontroll:** 2026-10-11
> Detta är extern domänkunskap. Bolagets exakta tillämpning finns i [produktpaketet](produktregler/README.md).

## 1. Tillhörighet och avgränsning

ITP-planen avdelning 1 gäller verifierad ITP1-tillhörighet. Huvudregeln
avser födda 1979 eller senare, men företag kan ha ITP1 för fler årskullar.
Födelseår ensamt är därför inte anslutningsbeslut. Planens undantag och
utlands-/företagarfall kräver det faktiska anslutningsunderlaget.

Vår produkt är enbart traditionell ITP1 ålderspension, utan återbetalnings-
eller familjeskydd, enligt B-002/B-021. ITP2, ITPK, sjukpension, TGL och
premiebefrielseförsäkring ingår inte. En verifierad premie finansierad av
extern premiebefrielse kan vara indata; bolaget försäkrar inte den risken.

## 2. Ordinarie premie

[ITP-planen 2026](https://www.ptk.se/wp-content/uploads/2025/12/Avtal_ITP_och_TGL_2026.pdf),
avdelning 1 punkt 6 och 7.1: faktisk pensionsmedförande månadslön,
4,5 % upp till 7,5 IBB/12 och 30 % däröver upp till 30 IBB/12.
Ingen ordinarie ålderspensionspremie på lön över taket.
Trappan räknas per person/arbetsgivare/månad före bolagets fördelning.

Ordinarie premie från 25-årsmånaden till månaden före 66.
Anställning under del av månad ger beräkning på faktiskt utbetald lön,
inte en ytterligare dagproratering. Slutlön/bonus efter anställning kan
fortfarande vara pensionsmedförande i utbetalningsmånaden inom rätt
premieålder. Collectums gräns för tre efterföljande löner är en
administrativ filgräns, inte en universell tre månaders preskription.
Saknad lön är inte noll; negativ rapport kräver rättelsehantering.

## 3. Pensionsmedförande lön och komplettering

[Collectums löneslagslista](https://collectum.se/administration/sa-rapporterar-du-ratt/pensionsmedforande-lon)
styr klassificeringen i ITP1-kolumnen. Kontant lön efter löneväxling,
bonus/provision/övertid och semesterersättning ingår normalt.
Naturaförmån och kostnadsersättning ingår inte. Lagstadgad sjuklön
och extra sjuk-/föräldralön måste skiljas åt. Detaljer och okända
löneslag hanteras i PR-014; ingen okänd ersättning döps automatiskt till lön.

Kompletterande premie enligt punkt 7.2 är separat från ordinarie trappa.
Fast belopp, procent/flex eller engångspremie kräver det verkliga avtalet.
Ingen generell branschflexsats antas. [Collectums fortsättning 66–67](https://collectum.se/administration/sa-rapporterar-du-ratt/lopande-premier)
gäller från 2026 med minst ordinarie trappa när den grenen valts.
Bolagets erbjudande efter 67 är avgränsat, inte ett påstått lagförbud.

## 4. Sparform, garanti och uttag

ITP-valet medger olika bolag/sparformer; minst hälften av premien ska
placeras traditionellt. Vårt bolag erbjuder bara traditionell försäkring.
Den interna administratörsrollen enligt B-021 ersätter verklig valcentral
i simuleringen och får inte påstås vara faktisk Collectumanslutning.

ITP punkt 7.5: ordinarie pension från 66-årsmånaden, livsvarigt som
utgångspunkt och tidsbegränsat minst fem år. Tidigaste avtalsålder 55;
vårt månadserbjudande börjar månaden efter 55-årsmånaden. Annan start kan
begäras; ingen generell maxålder 70 i den kontrollerade bestämmelsen.
Unisex används och pågående pension omfattar dödsmånaden.

[ITP-parternas flexibilitet](https://www.avtalat.se/arbetsgivare/nyheter-for-arbetsgivare/nu-blir-det-mojligt-att-pausa-uttaget-av-tjanstepension/)
omfattar paus och förlängning även efter start, utan särskild avgift eller
hälsoprövning. Bolagets frister, delutbud och beräkningsval finns i PR-002–009/024–027.
IL 58 kap. är skatteramen; en planetikett ensam ger inte rätt till ett undantag.

Traditionell försäkring kan ha garanti även när premien är premiebestämd.
B-027 väljer hela mottagna nettopremien och 0 % nettoränta som vår
garantigrund. Historiska garantidelar bevaras. Det är bolagets val,
inte en universell ITP-garantiprocent.

## 5. Årsparametrar och historik

| År | IBB | 7,5 IBB/12 | 30 IBB/12 |
|---|---:|---:|---:|
| 2023 | 74 300 | **46 437,50** | 185 750 |
| 2024 | 76 200 | 47 625 | 190 500 |
| 2025 | 80 600 | 50 375 | 201 500 |
| 2026 | 83 400 | 52 125 | 208 500 |

Exakta gränser används före öresavrundning av delpremier.
Årsbelopp ska inte ersättas av senaste års värde vid historisk beräkning.
[Parameterregistret](parametrar/PARAMETERREGISTER.md) och
[källregistret](../04_regulatoriskt/kallregister.md) anger förordningar och
övriga årsvärden. PR-032 skiljer verklig importerad rätt från uttryckligt
omgenererad syntetisk mockhistorik. För 2027 används inte en gissad IBB.

## 6. Byggunderlag

[Regelkatalogen med PR-ITP1-001–034](produktregler/README.md) är den fullständiga
produktpreciseringen. [Villkor v2.0](försäkringsvillkor.md) beskriver rättigheter,
[aktuariell grund](aktuariell_grund.md) beräkningar och
[tolkningarna](../04_regulatoriskt/tolkningar/T-ITP1-006-premie-lon-och-anslutning.md)
avvägningarna. Befintlig kod täcker bara delar; någon ny implementation
påstås inte av denna sammanställning.
