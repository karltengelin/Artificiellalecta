# A1 – värderings- och förklaringskontrakt för FTA

> **Version:** 1.0 | **Datum:** 2026-10-31 | **Status:** fastställt kontrakt enligt B-042, steg A1.
> Operatören fastställde M1–M6 (§12) i chatten 2026-10-31: ”Fastställ M1–M6”. Ingen kod,
> databasändring eller ny behörighet ingår.
> **Underlag:** [beslutsförslaget A0](AKTUARIETEAM_BESLUTSFORSLAG.md) (B-042),
> [planen](AKTUARIETEAM_PLAN.md), `01_domän/aktuariell_grund.md`, `PARAMETERREGISTER.md`,
> PR-ITP1-008/011/020–023/028, [Alectas försäkringstekniska riktlinjer](https://www.alecta.se/media/f5inriwi/forsakringstekniska-riktlinjer.pdf)
> och FFFS 2019:21–23.

Kontraktet gör projektplanens första kontraktsarbete uttryckligt: ändamål, omfattning, grund
och metod, data, kontroll, förklaring och leverans. Motorbygget (A4–A8) avgränsas mot det.
Garantivärdet `V_g`, pensionskapitalet `C` och FTA hålls isär genom hela kontraktet.

## 1. Ändamål och ansvar

| Del | Innehåll |
|---|---|
| Vad som värderas | Bolagets garanterade åtagande för ITP1 ålderspension (FTA) per värderingsdatum, samt villkorad återbäring och underskott per försäkring (B-042 punkt 1) |
| Användning | Bokslut enligt FFFS 2019:23, solvensuppgifter och FI-rapportering enligt FFFS 2019:22, ledningens uppföljning i centralen, produktrapporten. Samma beräkning för alla ändamål, som hos Alecta (riktlinjerna §4) |
| Ansvar | Operatören är ansvarig aktuarie och aktuariefunktion: låser värderingen (G1), antar grunder och släpper underlag |
| Utförande | Värderingsmotorn körs i betrodd kod som systemsteg. Aktuarieagenten startar, kommenterar och skriver utkast men räknar aldrig själv |
| Granskning | Granskningsskillen (second opinion hos annan leverantör) och operatören. Oberoende kontrollfall enligt §7 |
| Mottagare | Ekonomi (bokföringsunderlag), compliance och rapporteringsagenten (FI-underlag), centralen (mått), styrelse och VD (rapporter) |

## 2. Omfattning

**Värderingsdatum:** sista dagen i varje kvartal. Årsvärderingen per 31 december är
fullständig, med antagandeöversyn före. Värdering vid annat datum är tillåten för scenarier
men blir aldrig bas.

**Population:** varje försäkring med minst en garantidel `G_j > 0` eller `C > 0` vid
värderingsdatumet, i lägena premiebetalande, fribrev, ej påbörjad uttag, paus och pågående
utbetalning.

| Ingår i v1 | Ingår inte i v1, markeras *ej beräknat* |
|---|---|
| Garanterad pension per garantidel och uttagsdel | Pågående deluttag med flera uttagsdelar (PR-024) tills paket B |
| Kapitalvärdet av framtida driftskostnader | Betalningsskuld och obetalda månadsrätter (PR-020 steg 5) tills paket B |
| Kapitalvärdet av avkastningsskatt på reserven | Dödsfall under månaden och slutavräkning (PR-010/027) tills paket B |
| Villkorad återbäring och underskott per försäkring | Optionsjustering för uttagsval (§12, M5) |
| Kassaflödesprognos för garanterade utbetalningar | Flytt: stöds inte i produkten (försäkringsvillkor v2.0) |

Fall som saknas räknas aldrig som noll. De listas i resultatet med antal och orsak.

## 3. Storheter och formler

För försäkring `i` vid värderingsdatum `t`:

```text
FTA_i = Σ_j G_ij × a_V(t, D_i)  +  K_i(t)
VÅ_i  = max(0, C_i − FTA_i)
U_i   = max(0, FTA_i − C_i)
FTA   = Σ_i FTA_i,   VÅ = Σ_i VÅ_i,   U = Σ_i U_i,   kontroll: VÅ − U = Σ_i C_i − FTA
```

- `G_ij` är garantidelarna med sin egen historiska grund (B-027). De ändras aldrig av värderingen.
- `D_i` är försäkringens återstående betalningsmånader enligt gällande plan. Ej påbörjad
  försäkring använder referensplanen: livsvarigt från 66-årsmånaden (`aktuariell_grund.md` §4).
- `a_V` är annuitetsfaktorn på värderingsgrunden SIM-V:
  `a_V(t, D) = Σ_{d∈D} w_V(t, d) × v(t, n_d)`. Här är `w_V` överlevnad enligt SIM-V:s dödlighet
  och `v` diskonteringsfaktorn i §4.
- `K_i` är kapitalvärdet av framtida driftskostnader för försäkringen (§4, K).
- Avkastningsskatten på reserven ingår genom diskonteringen (§4, S).

Månadsmodell, svans över 100 år och avrundning följer `aktuariell_grund.md` §2–3, med SIM-V:s
parametrar i stället för SIM-G:s. Belopp lagras i hög precision och avrundas till öre först i
rapportering.

## 4. Värderingsgrund SIM-V-2026-01

Grunden är versionerad data i `valuation_bases`, med källa, kontrolldatum, beslut och
kontrollsumma (B-042, val C). Tabellen och startgrunderna finns sedan A4 (`databasschema.md` §9j). Första versionen, fastställd 2026-10-31 (§12):

| Kod | Antagande | Värde v1 | Källa och motivering |
|---|---|---|---|
| R | Diskonteringskurva | Versionerad spotkurva `FI-SIM-ÅÅÅÅ-MM` med årliga löptider 1–150 år, konstruerad enligt 4 kap. FFFS 2019:21. Interpolation mellan löptider och månadsvis diskontering `v(t, n) = (1 + r_⌈n/12⌉)^(−n/12)` | FFFS 2019:21 4 kap., Alecta §4.1. Värdena är syntetiska i sandboxen; FI:s metodändring 2026 prövas av compliance (M1) |
| S | Avkastningsskatt | Diskontera med `r − s_y`, där `s_y = 0,15 × max(SLR, 0,005)` från parameterregistret (2026: 0,354 %) | AvPL och PR-ITP1-023. Motsvarar Alectas "kapitalvärdet av den avkastningsskatt som förväntas betalas på tillgångar motsvarande FTA". Approximationen prövas i M2 |
| Q | Dödlighet | SIM-G:s modell: SCB 2025 unisex, 1,5 % årlig förbättring, faktor 0,80, svans enligt grunden | Aktsamt och samma som garantin, så att en premie på 0 %-kurva ger FTA = premie (kontrollfall K1). Erfarenhetsanalysen (A9) prövar nivån |
| K | Driftskostnader | 180 kr per försäkring och år under uppskov, 240 kr under utbetalning, uppräknat 2 % per år, diskonterat med samma kurva | Eget simuleringsval (M3). Avser bolagets kostnad, inte kapitalavgiften på `C` |
| P | Uttagsantagande | Livsvarigt från 66-årsmånaden för ej påbörjade försäkringar | Referensplanen i `aktuariell_grund.md` §4 |
| O | Optioner | Ingen justering i v1 | Materialitet bedöms med uttagsdata (M5) |

## 5. Data: datautdrag och startbestånd S-04

### 5.1 Datautdrag per värderingsdatum

Ett datautdrag är oföränderligt och har en SHA-256-kontrollsumma. Alla värderingar och analyser
refererar till det.

| Fält | Innehåll |
|---|---|
| `policy_id` | Intern nyckel; inget personnummer i utdraget |
| `birth_month` | Födelseår och månad |
| `state` | Läge vid datumet: premiebetalande, fribrev, ej påbörjad, paus, utbetalning |
| `plan` | Uttagsplan: start, slut eller livsvarig, pausmånader |
| `guarantee_parts[]` | Per del: premie `P_j`, mottagningsmånad, grund (SIM-HIST-2023-01 eller SIM-G-2026-01), `G_j` |
| `capital` | `C` vid datumet |
| `source` | `reconstructed_s04` eller `ledger` (när paket B finns) |

### 5.2 Rekonstruktion S-04 (B-042, val L)

- **Garantidelar:** varje betalmarkerad premie ger `G_j = P_j / A_g(t_j, D_ref)`.
  Grunden är SIM-HIST-2023-01 för 2023-01 till och med 2026-10 och SIM-G-2026-01 därefter
  (`PARAMETERREGISTER.md`).
- **Pensionskapital:** `C` rullas fram månad för månad enligt PR-020:s ordning. Avkastningen
  kommer ur den versionerade serien `AVK-SIM-2026`. Därefter dras kapitalavgift (PR-022) och
  skattebelastning (PR-023). Månadens premier tillförs vid månadsslut, och arvsvinst fördelas
  enligt PR-011 med SIM-R.
- **Utbetalningar:** demobeståndet har inga påbörjade uttag. Om sådana finns räknas de enligt
  PR-009; annars markeras fallet *ej beräknat*.
- **Märkning:** utdraget får `source = reconstructed_s04`. Rapporter och centralen visar
  märkningen. Inga individuppgifter lämnar betrodd kod.

### 5.3 Datakvalitet (kontroller före värdering)

Datautdraget godkänns bara om alla följande kontroller passerar:

- Antal försäkringar och summa betalmarkerade premier stämmer mot beståndet.
- Inga saknade födelsemånader, lägen eller planer, och inga motstridiga lägen.
- Inget negativt `C` och ingen garantidel med negativt `G_j`.
- Varje garantidel har en känd grund med kontrollsumma.

Ett underkänt utdrag stoppar flödet `valuation_close` före värderingen.

## 6. Leverans och resultatscheman

Resultaten sparas i tjänstelagret (B-042, val I) och kan inte ändras efter lås.

| Schema | Fält (urval) |
|---|---|
| `ValuationRun` | id, version, värderingsdatum, grund och version, datautdrag och hash, kodversion, status (`draft`, `locked`, `superseded`), låst av och när, ersätter |
| `ValuationResult` | per segment (läge × födelsekohort): antal, `C`, FTA, därav `K`, VÅ, `U`, dolda celler (< 10), ej beräknade fall med orsak |
| `ChangeAnalysis` | IB-körning, UB-körning, stegordningens version, belopp per steg, oanalyserat i kronor och procent, FI-radkoppling per steg |
| `CashFlowProjection` | per år: förväntade garanterade utbetalningar, kostnader, premier (om antagna); grund och kurva |
| `ProvisionEntryProposal` | period, poster (förändring i livförsäkringsavsättning, förändring i villkorad återbäring), belopp per analyssteg, underlagets hash |
| `ReportBasis` | rapport-id, period, version, rader (radkod, belopp, enhet, källa), kontroller, status (`draft`, `released`, `superseded`) |

Varje schema anger storhet och grund (B-042, guardrail 6). Ett `ValuationResult` med
`source = reconstructed_s04` kan inte släppas som FI-underlag utan att märkningen följer med.

## 7. Kontroll

Motorn ska klara följande kontrollfall innan en värdering får låsas. Fallen körs automatiskt
vid varje ny motorversion.

| Nr | Kontrollfall | Väntat utfall |
|---|---|---|
| K1 | En premie 1 000 kr, 40 år, platt kurva 0 %, ingen skatt, inga kostnader | FTA = 1 000,00 kr, eftersom SIM-V-dödligheten är densamma som garantins |
| K2 | Som K1 med platt kurva 3 % | FTA < 1 000 kr. Värdet räknas oberoende i kalkylblad med samma formel |
| K3 | `C` = 500 kr och FTA enligt K2 över 500 kr | U = FTA − 500 och VÅ = 0 |
| K4 | `C` = 2 000 kr med samma garanti | VÅ = 2 000 − FTA och U = 0 |
| K5 | Två perioder i följd | IB i period 2 = UB i period 1, på öret |
| K6 | Samma utdrag, grund och kod två gånger | Identiska resultat och hashar |
| K7 | Segment med 1–9 försäkringar | Visas som dolt, även genom kompletterande döljning mot totalen |
| K8 | Förändringsanalys med konstruerat avvikande steg | Oanalyserat över 0,5 % ger `needs_human` |
| K9 | Leveranskontrollens garantifall (`projekt/04_produktregelverk/LEVERANSKONTROLL.md`) | Samma `G` som där |
| K10 | Summakontroll på hela beståndet | VÅ − U = ΣC − FTA på öret |

## 8. Förklaring: förändringsanalysens beräkning

Analysen räknar om beståndet stegvis från IB:s läge till UB:s läge. Varje stegs belopp är
`V(läge_k) − V(läge_k−1)`, där `V` är FTA. Stegordning v1:

| Steg | Ändring av läget | FI-rad |
|---|---|---|
| 0 | IB: låst värdering vid förra datumet | F1 |
| 1 | Lägg till periodens nya garantidelar, värderade på deras garantigrund | F2 |
| 2 | Värdera samma nya delar på SIM-V i stället | E8 |
| 3 | Ta bort utbetalda månadsrätter och slutavräknade försäkringar | F3 |
| 4 | Flytta värderingsdatumet till UB-datumet med IB:s kurva och antaganden (förräntning efter skatt och kostnader) | F4, F5 |
| 5 | Ta bort försäkringar som avgått genom dödsfall | E1–E2 |
| 6 | Byt till de planer som gäller vid UB | E11 |
| 7 | Byt till UB:s kurva | E17, F6 |
| 8 | Byt till UB:s övriga antaganden | E11, F6 |
| 9 | Byt till UB:s modell- och dataversion | – |
| 10 | Oanalyserat = UB − läge 9 | E23 |

Stegordningen är versionerad. En ny version kräver att föregående period räknas om med den
nya ordningen, så att perioder kan jämföras.

**Villkorad återbäring** förklaras bredvid: förändringen i ΣC per orsak (premier,
återbäringsränta, avgifter och skatt, utbetalningar, arvsvinst) minus FTA-förändringen, plus
förändringen i U.

**Känsligheter** vid varje kvartalsvärdering: räntekurvan ±50 och ±100 bp parallellt,
dödsrisken −10 % och −20 %, driftkostnader +10 % och en avkastningschock på `C` (−20 % aktier).
Utfallet är ΔFTA, ΔVÅ och ΔU per kohort. Konsolideringsnivån är ej beräknad tills det finns en
tillgångssida.

## 9. FI-radkoppling

Kopplingen ska kontrolleras mot gällande konsoliderad FFFS 2019:22 innan rapportkontraktet låses (M6).

| FI-rad | Källa i kontraktet |
|---|---|
| Bilaga 1 F1–F7 (FTA, år) | `ChangeAnalysis` steg 0–8 |
| E8 Omvärdering från premie- till avsättningsantaganden | Steg 2 |
| E17 Ändrat ränteantagande | Steg 7 |
| E1–E2, E29–E48 Dödlighetsresultat | Steg 5 och arvsvinst i `C` |
| E23 Oanalyserat | Steg 10 |
| I Kassaflödesprognoser | `CashFlowProjection` |
| C4–C7, C29 Premier, avgiftsbestämd traditionell | Premieflöden (`get_premium_flows`), inte FTA |
| Balansposter för livförsäkringsavsättning och villkorad återbäring | `ValuationResult` totalt |

## 10. Beroenden

| Beroende | Behövs för | Ägare |
|---|---|---|
| Premiehistorik och bestånd i tjänstelagret | S-04 | Projekt 1 (finns) |
| `AVK-SIM-2026` avkastningsserie | `C` | Aktuarien tills kapitalförvaltningen återupptas |
| SLR per år i parameterregistret | Skatt (S) | Projekt 4 (finns för 2026) |
| Syntetisk FI-kurva | R | Aktuarien, med compliance för metoden |
| Paket B | Ersätter S-04, utbetalningar och dödsfall | Projekt 1/6 |
| Begreppsavstämning kundkapital/villkorad återbäring | Kundinformation | Projekt 4 (B-042) |

## 11. Acceptans för A1

A1 är klart när följande är uttryckligt i detta dokument och operatören har fastställt
punkterna M1–M6 i §12. **Uppfyllt 2026-10-31.**

- omfattning och ej beräknade fall,
- grundens parametrar,
- dataformat och kontroller,
- kontrollfall,
- förklaringens stegordning,
- resultatscheman och FI-koppling.

Därefter avgränsas A4 (antagandebibliotek), A5 (S-04) och A6 (motor) som byggsteg mot kontraktet.

## 12. Fastställda ställningstaganden

Operatören fastställde förslagen M1–M6 oförändrade 2026-10-31. M6 är ett uppdrag till
compliance som ska vara utfört före A8.

| Nr | Fråga | Fastställt |
|---|---|---|
| M1 | Startkurvans värden och form | Syntetisk kurva som stiger från 2,5 % (1 år) till 3,0 % (20 år) och närmar sig 3,4 % på lång sikt, märkt syntetisk. Compliance prövar FI:s metodändring 2026 |
| M2 | Skatt genom diskontering med `r − s_y` | Godta i v1; kontrollera mot en explicit skatteprojektion i K2-varianten |
| M3 | Driftkostnad 180/240 kr och 2 % uppräkning | Godta som simuleringsval och pröva i erfarenhetsanalysen |
| M4 | Dödlighetsnivå = garantins (0,80) | Godta i v1; erfarenhetsanalysen visar om nivån är för försiktig |
| M5 | Optioner (tidigt uttag, tidsbegränsat uttag) | Ingen justering i v1; pröva när uttagsdata finns |
| M6 | FI-radkoder | Compliance kontrollerar mot gällande konsoliderad version före A8 |
