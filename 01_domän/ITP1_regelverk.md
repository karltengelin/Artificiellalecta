# ITP1-regelverk – ålderspension

> Domändokument: beskriver kollektivavtalets regler för ITP1 ålderspension så som de gäller i verkligheten. Detta är **lager 1-kunskap** (vad avtalet säger) – bolagets egna villkor och tillämpningar finns i `försäkringsvillkor.md`.
>
> **Siffror verifierade 2026-07-12** mot Avtalat, Collectum och Regeringskansliet. Basbelopp och brytpunkter ändras årligen – se §6 för uppdateringsrutin.

---

## 1. Bakgrund och parter

ITP (Industrins och handelns tilläggspension) är kollektivavtalad tjänstepension för privatanställda tjänstemän, avtalad mellan **Svenskt Näringsliv** och **PTK**. ITP1 är den premiebestämda avdelningen och gäller tjänstemän **födda 1979 eller senare** (företag som tecknat ITP-avtal efter 2007 kan tillämpa ITP1 för alla anställda oavsett ålder).

**Collectum** är valcentral och administratör i det verkliga systemet: tar emot löneanmälningar, fakturerar arbetsgivare månadsvis och förmedlar premier till det pensionsbolag den försäkrade valt. I vår simulering axlar Artificiellalecta både rollen som valbart pensionsbolag och (förenklat) administratörsrollen – se avgränsning i `försäkringsvillkor.md`.

## 2. Premietrappan

Arbetsgivaren betalar varje månad en premie för ålderspension beräknad på den anställdes **pensionsmedförande lön** (se §3):

| Lönedel (per månad) | Premiesats |
|---|---|
| Upp till 7,5 IBB/12 (**52 125 kr/mån 2026**) | **4,5 %** |
| Över 7,5 IBB/12 upp till 30 IBB/12 (**52 125–208 500 kr/mån 2026**) | **30 %** |
| Över 30 IBB/12 | Ingen premie |

Formel (månadspremie, `L` = pensionsmedförande månadslön, `B1` = 7,5 × IBB/12, `B2` = 30 × IBB/12):

```
premie = 0,045 × min(L, B1) + 0,30 × max(0, min(L, B2) − B1)
```

Skälet till den höga satsen över brytpunkten: allmän pension tjänas bara in på inkomster upp till 7,5 IBB – de 30 procenten kompenserar för det.

## 3. Pensionsmedförande lön

- **Kontant utbetald bruttolön varje månad** – inklusive rörliga delar som provision, bonus och övertidsersättning den månad de betalas ut
- Kostnadsersättningar (traktamenten, bilersättning etc.) ingår **inte**
- Premien beräknas **per kalendermånad på faktiskt utbetald lön** – ingen årsutjämning i efterhand. Hög lön en enskild månad (t.ex. bonusutbetalning) ger hög premie just den månaden, vilket kan slå över brytpunkten
- Arbetsgivaren rapporterar lönen månadsvis till valcentralen

## 4. Åldersgränser

| Händelse | Regel |
|---|---|
| Premiebetalning börjar | Fr.o.m. **månaden den anställde fyller 25 år** |
| Premiebetalning slutar | T.o.m. **månaden innan den anställde fyller 66 år** |
| Frivillig fortsättning | Arbetsgivare kan betala kompletterande premie 66–67 år (minst ordinarie satser) |

Notera för datamodellen: gränserna är **månadsbaserade**, inte dagbaserade. En person född 1998-08-15 får sin första premie för augusti 2023 (månaden 25-årsdagen infaller).

## 5. Placering och uttag

**Placering:** Den försäkrade väljer pensionsbolag och sparform via valcentralen. Minst **50 % av premien måste placeras i traditionell försäkring**; resten får placeras i fondförsäkring. Den som inte väljer (ickevalsalternativet) får hela premien i traditionell försäkring hos default-bolaget.

**Uttag:**
- Uttag kan påbörjas tidigast från **63 års ålder** *(gäller nuvarande regler; verifieras på nytt när uttagslogik implementeras)*
- Standard är **livsvarig utbetalning**; tidsbegränsat uttag (kortast 5 år) kan väljas
- Sedan regeländring är det möjligt att **pausa ett påbörjat uttag** – direkt relevant för kundportalens "pausa uttag"-funktion (Fas 4+)

## 6. Basbelopp och årlig uppdatering

| Parameter | Värde 2026 | Källa |
|---|---|---|
| Inkomstbasbelopp (IBB) | **83 400 kr** | Förordning (2025:1002) |
| Brytpunkt 7,5 IBB/12 | **52 125 kr/mån** (625 500 kr/år) | Avtalat/Collectum |
| Tak 30 IBB/12 | **208 500 kr/mån** (2 502 000 kr/år) | Avtalat/Collectum |

**Uppdateringsrutin:** IBB fastställs av regeringen i november året innan. Vid årsskifte ska denna tabell uppdateras och nya brytpunkter läggas in i systemets parametertabell (premiemotorn ska läsa basbelopp per år ur data, aldrig ha dem hårdkodade).

Historik (för beräkning av retroaktiv premiehistorik i mockdata):

| År | IBB | 7,5 IBB/12 | 30 IBB/12 |
|---|---|---|---|
| 2026 | 83 400 | 52 125 | 208 500 |
| 2025 | 80 600 | 50 375 | 201 500 |
| 2024 | 76 200 | 47 625 | 190 500 |
| 2023 | 74 300 | 46 438 | 185 750 |

## 7. Angränsande delar – utanför scope (B-002)

ITP1-paketet innehåller mer än ålderspension. Dessa administreras i verkligheten parallellt men ingår **inte** i vår produkt:

- **Premiebefrielseförsäkring (PBF)** – betalar premien vid sjukdom/föräldraledighet (0,125 % / 1,415 % 2026)
- **ITP sjukpension** – åldersgräns höjd till 67 år fr.o.m. 2026
- **TGL, TFA, TRR-omställningsstöd** – liv-, arbetsskade- och omställningsskydd

Att de listas här är medvetet: handläggaragenten ska kunna svara "det ingår inte i vår produkt, men så här fungerar det" på kundfrågor.

**Arbetsgivarens totalkostnad** (kontext): utöver premierna betalar arbetsgivaren särskild löneskatt **24,26 %** på pensionspremien.

## 8. Konsekvenser för systemet

Regler premiemotorn (Fas 1c) ska implementera:

1. Premie beräknas **per person och kalendermånad** på inrapporterad utbetald lön
2. Trappan enligt §2 med **årsspecifika brytpunkter ur parametertabell**
3. Ålderfönster enligt §4: `månad(25-årsdag) ≤ premiemånad ≤ månad(66-årsdag) − 1`, månadsupplösning
4. Ingen premie under månader utan anställning (kontrollera `employment_start_date`/`employment_end_date`)
5. Premie ≥ 0, avrundas till hela ören

## 9. Källor

- [Avtalat – Premier tjänstemän ITP1](https://www.avtalat.se/arbetsgivare/kostnader-och-premier/premier-tjansteman-itp1/) (premiesatser, brytpunkter, åldersgränser 2026)
- [Regeringen – Inkomstbasbelopp för 2026 fastställt](https://www.regeringen.se/artiklar/2025/11/inkomstbasbelopp-och-inkomstindex-for-ar-2026-faststallt/) (IBB 83 400 kr)
- [Förordning (2025:1002) om inkomstbasbelopp för år 2026](https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/forordning-20251002-om-inkomstbasbelopp-for-ar_sfs-2025-1002/)
- [Collectum – Aktuella premier och basbelopp](https://collectum.se/avtal-och-faktura/faktura-och-premier/aktuella-premier-och-basbelopp)
- [PTK – Höjd åldersgräns för ITP sjukpension 2026](https://www.ptk.se/sakfragor/pension-och-forsakring/tjanstepension-itp/hojd-aldersgrans-2026/)
