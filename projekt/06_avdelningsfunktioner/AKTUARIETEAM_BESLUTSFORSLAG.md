# A0 – beslutsförslag för aktuarieteamets harness och arbetsyta

> **Datum:** 2026-10-31. **Version:** 0.1. **Status:** valen A–N godkända av operatören i
> chatten 2026-10-31 (”Godkänn A–N”) och loggade som **B-042**.
> **Omfattning:** endast Markdown. Ingen kod, databasändring, ny behörighet eller ändrad
> körpolicy införs genom dokumentet. Bygget följer §5.
> **Bygger på:** [utredningen och planförslaget](AKTUARIETEAM_PLAN.md) v0.2 med operatörens svar
> på Q1–Q7 2026-10-31, [skissen](aktuarie-arbetsyta.html), B-008, B-026, B-027, B-028, B-036,
> B-037, B-039 och B-041.
> **Ägare:** projekt 6 (aktuariell värdering). Berör projekt 2, 4, 10 och compliance-teamet.

## 1. Sammanfattning

Aktuarieteamet kan i dag svara på frågor om bestånd och premieeffekter men inte värdera
bolagets åtaganden. Förslaget fastställer **hur teamet ska arbeta** – metod för FTA, analys,
bokföringsunderlag, scenarier och rapportunderlag – och **vilken harness och arbetsyta** som
bär arbetet, så att byggstegen A1–A10 kan avgränsas ett i taget.

Metoden efterliknar Alecta, enligt operatörens val. FTA är det prospektiva kapitalvärdet av
den garanterade pensionen på en aktsam värderingsgrund med FI-kurva. Pensionskapitalet byggs
retrospektivt med faktisk avkastning. Överskottet över garantin redovisas som villkorad
återbäring, och ett underskott bärs av bolagets kapital.

Förslaget skapar inga nya agenter. Aktuarieagenten får nya verktyg i betrodd kod. Människan,
det vill säga operatören som ansvarig aktuarie, låser värderingar, antar grunder och släpper
rapportunderlag.

## 2. Beslutsval

| Val | Rekommendation | Alternativ och avvägning | Plan |
|---|---|---|---|
| A | **Metod:** Alecta-modellen. FTA = kapitalvärdet av garanterad pension `G` på värderingsgrunden. Villkorad återbäring `VÅ = max(0, C − FTA)` och underskott `U = max(0, FTA − C)` per försäkring | `max(C, garantivärde)`: enklare, men avviker från Alecta och blandar ihop garanti och överskott. Stokastiskt tidsvärde: senare utbyggnad | §3.1 |
| B | **Redovisning:** villkorad återbäring som egen skuldpost, eftersom bolaget har en ägare (PR-028). Underskott täcks av bolagets kapital enligt PR-028 | Alectas ömsesidiga modell med återbäringen i eget kapital, vilket kräver ändrad bolagsform | §3.1 |
| C | **Värderingsgrund `SIM-V`** som versionerad data skild från SIM-G/B/R: FI-kurva enligt 4 kap. FFFS 2019:21 som versionerad indata, aktsam dödlighet, kapitalvärde av driftskostnader och avkastningsskatt. Talen fastställs i A1 | Återanvända SIM-G som FTA-grund: enkelt, men garantigrunden har 0 % ränta och är ingen FTA-grund (`aktuariell_grund.md` §1) | §3.1, §3.5 |
| D | **FTA-analys** i fast, versionerad stegordning efter Alectas förklaringsmodell, med FI-radkoppling. Oanalyserat över **0,5 % av FTA** stoppar för mänsklig granskning | Fri ordning eller ingen tröskel: förklaringen blir inte jämförbar mellan perioder | §3.2 |
| E | **Bokföringsunderlag:** förändring i livförsäkringsavsättning och i villkorad återbäring, som verifikationsförslag på nivån APPROVAL. Underlaget sparas tills ekonomins bokföringstjänst finns (V-10) | Vänta med bokföringsunderlaget tills ekonomi byggs: då saknas kopplingen mellan värdering och bokslut | §3.3 |
| F | **FI-rapportering i verklig storlek:** kvartal avsnitt C, E och F, år A–K, EU-mallar L–O, årlig kvalitativ sammanfattning. Rapportnivån är en parameter | Öva full rapportering som ett större bolag: mer bygge utan verksamhetsbehov | §2.4 |
| G | **Ansvar:** operatören är ansvarig aktuarie och aktuariefunktion. Granskningen är en skill som körs hos en annan leverantör; ingen egen agent. Data scientist byggs i A9 | En agent för aktuariefunktionen: kräver avsteg från B-008 och kan inte inneha en nyckelfunktion | §4.1 |
| H | **Poddar och skills** enligt planens §4.2: `antaganden`, `aktuariell`, `rapportunderlag`, `ekonomiunderlag`, `granskning` och två nya läsverktyg i `bestand`. Nivåerna sätts i åtkomstregistret: lås, införande och släpp är HUMAN_ONLY | En stor podd för allt: enklare montering men grövre behörighet | §4.2 |
| I | **Verksamhetsdata i tjänstelagret** (B-028): tabellerna `valuation_bases`, `valuation_runs`, `valuation_results`, `change_analyses`, `report_bases`, med migrationer först efter backup och OK | Harnessens egna tabeller: men värderingar är verksamhetsdata som UI, agent och skript ska dela | §4.2 |
| J | **Guardrails** enligt planens §4.3, bland annat reproducerbarhet, skyddad bas, periodlås, avstämning som hårda stopp och storheter i resultatscheman | – | §4.3 |
| K | **Flöden** i flödesmotorn: `valuation_close`, `assumption_review`, `product_report`, `regulatory_basis`. `monthly_actuarial_check` efter paket B | Egna körmiljöer per process: dubblerar flödesmotorn | §4.4 |
| L | **Startbestånd:** rekonstruerat S-04. `G_j` räknas ur premiehistoriken med SIM-HIST-2023-01 och `C` med en deklarerad avkastningsserie. Märkt och ersättningsbart när paket B finns | Vänta på paket B: korrekt, men FTA-motorn skjuts långt fram | §3.5 |
| M | **Arbetsyta:** `/team/aktuarie` inom OC-8 enligt skissen. Första versionen visar befintliga data (översikt, rapporter, uppdrag) | Vänta tills motorerna finns: arbetsytan och rapporten skjuts upp i onödan | §5 |
| N | **Produktrapport** enligt planens §7, med v0 (avsnitt 1–3, 8, 9) som första leverans | – | §7 |

## 3. Följder utanför projekt 6

- **Projekt 4 (produktregelverk):** begreppen kundkapital och villkorad återbäring stäms av
  i `aktuariell_grund.md` §1, PR-ITP1-021 och villkoren §4–6 före FTA-motorn (A6). Valet ändrar
  ingen produktregel.
- **Compliance:** prövar FI:s ändrade metod för diskonteringsräntan 2026 som källändring, och
  kontrollerar FFFS 2019:22:s radkoder mot gällande konsoliderad version innan rapportkontraktet
  låses. Rapporteringsagentens roll preciseras i A8.
- **Projekt 5 (pausat):** tillgångssidan och konsolideringsnivån väntar. Avkastningen är
  versionerad scenarioindata som aktuarien äger tills kapitalförvaltningen återupptas.
- **Projekt 10:** centralens FTA-mått använder låsta värderingar ur tjänstelagret och visar
  *ej beräknat* tills de finns.

## 4. Acceptans för hela förmågan

Förmågan är verifierad när följande gäller:

- En kvartalsvärdering kan köras om med samma resultat.
- FTA-analysen går ihop till öret, med oanalyserat under tröskeln.
- `ΣVÅ − ΣU = ΣC − FTA` gäller vid både IB och UB.
- Leveranskontrollens oberoende kontrollfall godkänns.
- Ett scenario ändrar aldrig basen.
- Ett FI-underlag kan spåras från radkod till värderingskörning.
- Agenten kan inte låsa, anta eller släppa något.
- Allt är visat i både normalfall och avvikelsefall: underskott, dold kohort, rättad värdering
  och oanalyserat över tröskeln.

## 5. Byggordning

Planens §8 gäller. Förslaget ändrar inte ATT_GORA:s prioritering, där OC-3a är närmast.
Rekommenderad första leverans efter godkännandet:

1. **A1, värderings- och förklaringskontraktet** (Markdown): tal och källor för SIM-V, dataformat
   för S-04, kontrollfall, FI-radmappning och resultatscheman.
2. **A2, produktrapport v0** på befintliga data, med `get_portfolio_snapshot` och
   `get_premium_flows`. Kan gå parallellt med A1 eftersom den inte berör FTA.

Migrationer, nya databasroller och körningar mot Lakebase görs först efter backup och
operatörens OK (AGENTS.md §4.5).

## 6. Förslag till beslutspost

Numret blir nästa lediga B-nummer när posten loggas.

> **B-0xx | 2026-xx-xx | Aktuarieteamets metod, harness och arbetsyta (A0)**
>
> **Beslut:** Operatören godkände valen A–N i
> `projekt/06_avdelningsfunktioner/AKTUARIETEAM_BESLUTSFORSLAG.md`.
>
> 1. **Metod (A–D).** FTA beräknas som i Alecta-modellen: det prospektiva kapitalvärdet av den
>    garanterade pensionen på värderingsgrunden SIM-V, med FI-kurva enligt FFFS 2019:21.
>    Pensionskapitalet är retrospektivt. Överskottet redovisas som villkorad återbäring
>    (skuld) och underskottet bärs av bolagets kapital. FTA-förändringen förklaras i en fast
>    stegordning, och oanalyserat över 0,5 % stoppar.
> 2. **Underlag (E, F).** Aktuarien levererar bokföringsunderlag på nivån APPROVAL och
>    FI-underlag i verklig storlek till compliance.
> 3. **Ansvar och harness (G–K).** Operatören är ansvarig aktuarie. Granskningen sker med en
>    skill, och ingen ny agent skapas. De nya poddarna och verksamhetstabellerna ligger i
>    tjänstelagret, och flödena körs i flödesmotorn.
> 4. **Data, yta och rapport (L–N).** Startbeståndet rekonstrueras och märks S-04. Arbetsytan
>    blir `/team/aktuarie` inom OC-8, och produktrapporten följer planens §7.
>
> **Motivering:** Att efterlikna en etablerad svensk ITP1-aktör ger en känd och spårbar metod.
> Garanti och överskott hålls isär, och arbetet återanvänder tjänstelagret, flödesmotorn och
> harnessen.
>
> **Konsekvenser:** Byggstegen A1–A10. Avstämning av begreppen med projekt 4 och prövning av
> FI:s räntemetod hos compliance. Ingen ändring av körkod, databas eller behörighet genom
> beslutet.
>
> **Preciserar:** B-027 (garantin), B-028 (tjänstelagret), B-036 (teamområden) och projekt 6:s
> kontraktsuppdrag.
