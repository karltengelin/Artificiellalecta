# Företagsöversikt – uppdatering 25 oktober 2026

Den klickbara [företagsöversikten](foretagsoversikt.html) är uppdaterad mot
`main` @ `5fd10ab`. Rotkopian och projektkopian har samma innehåll, med anpassade
relativa hänvisningar. Det tidigare [uppdateringsunderlaget](UPPDATERING_2026-10-24.md)
bevaras som historik. Detta dokument är Markdown-underlaget; HTML är den visuella leveransen.

## Vad som ändrats

- B-036:s gemensamma plattform, operatörscentral och teamområden ingår nu i kartan
  och bland de tio projektkorten. Centralen är plan och skiss, inte driftsatt.
- B-037:s verksamhetsdrivna AI-native bolagsvision ersätter flaggskeppsdemon som
  byggmål. Regeländringsbilden visar möjliga följder och ansvar, inte en färdig
  obligatorisk körkedja. Framtida demonstrationer hålls separata.
- Ärenden och handläggaragent för `salary_report` visas som byggda. `cases` och
  agentrollens läsrätt finns i Lakebase. F5-5–6:s slutverifiering från 1 november,
  fler ärendetyper och självständiga körningar står kvar som återstående arbete.
- Harness 3b-1–8 inklusive modellröktest visas som genomfört. Compliance- och
  aktuarieprofiler, dokumentgateway, parameterinsikt och flödesmotor finns lokalt.
  Delegering, bakgrundsarbetare, körgränssida och journal i databas återstår.
- Det byggda `rule_change_parameter` beskrivs som ett enparameterflöde med egna
  begränsningar. Den skriptade demomodellen är borttagen. Ordinarie webbapp ansluter
  inte flödet automatiskt; `FlowConsole` kräver en uttrycklig AI-klient.
- Operations- och datamodelltabeller, diagram, kartans detaljrutor, kodrader,
  teststatistik och kvarstående byggbehov är uppdaterade tillsammans.
- Pensions-/betalningsmotorer, kapitaljournal, ekonomi, rapportkontrakt och
  månadssimulering visas som återstående verksamhetsbygge enligt processöversikten.
  En rapportmall eller premiescenarioanalys visas inte som en färdig avdelningsfunktion.

## Fakta och källor

| Uppgift | Kontrollerat underlag |
|---|---|
| 37 beslut; 34 produktregler | `BESLUTSLOGG.md`, produktpaketets README |
| PR-ITP1 v1.0 gäller från 2026-11-01 | B-031; reglerna är fortfarande kommande den 25 oktober |
| 25 operationer: 12 read, 1 compute och 12 write | Operationsregistret och `02_system/tjänstelager_operationer.md` |
| Register-/effektiv åtkomst den 25 oktober och från 1 november | `ServiceLayer.decision()` med uttryckliga datum; inga operationer verkställda |
| 18 tabellmodeller; 12 dokumenterat införda i Lakebase | `Base.metadata`, `02_system/databasschema.md` §§1/12 |
| `cases` införd 24 oktober; `product_parameters` 25 oktober | Dokumenterade migrationer och verifieringar i databasschemat och ATT_GORA |
| Tre flödes- och tre portföljmodeller bara lokalt | Databasschemat, flödes- och kapitalprojektets status |
| Tre agentprofiler, fem poddar och 13 mappade verktyg | `src/agents/ecosystem.yaml`, `03_skills/skillkatalog.md`. Faktisk åtkomst kan vara snävare |
| AI-röktest godkänt 11 oktober; harness-röktest 24 oktober | B-025 och ATT_GORA 3b-8. Detta intygar inte dagens nycklar eller nya användningsfall |
| Senast dokumenterat bestånd: 20 arbetsgivare, 501 försäkrade, 499 försäkringar, 15 097 premier | ATT_GORA och migrationsverifieringarna, ingen ny databasavläsning |
| 39,0 Mkr betalda premier i genererat grundbestånd | Återuppbyggnaden 11 oktober. Detta är inte komplett pensionskapital eller kapitaljournal |
| Kvarvarande processer och byggpaket | `01_domän/processer_översikt.md`, ATT_GORA och de tio projektplanerna |

Pythonradantal räknar `.py` rekursivt i respektive visad mapp inklusive tomrader,
kommentarer och docstrings. HTML, CSS, YAML och testkod ingår inte i dessa radantal.
Historiska beståndsuppgifter är inte livevärden; manuella ändringar och journaler
kräver fortfarande backup.

## Testinventering och tidigare kodverifiering

`python -m pytest --collect-only -q -p no:cacheprovider` samlade in **1 124 testfall
i 59 filer**, utan insamlingsfel. Varje testfall räknas i exakt en kategori nedan.
Kategorierna är en inventering för översikten, inte testkatalogens överlappande sviter.

| Område | Insamlade testfall |
|---|---:|
| Tjänstelagret inklusive produktparametrar och beståndsinsikt | 309 |
| Harness och flöden | 300 |
| Webb och designkoppling | 171 |
| Kapitalmodeller | 100 |
| AI-lagret | 84 |
| Skriptens ingångar | 30 |
| Testurval | 29 |
| Rapportering och design | 26 |
| Ärende- och UUID-modeller | 22 |
| Analys | 21 |
| Premiemotorn | 17 |
| Backup och migration | 15 |
| **Summa** | **1 124** |

Den tidigare kodverifieringen den 25 oktober gav **1 088 godkända testfall och
36 undantagna Postgres-testfall** med `-m "not postgres"`. Den testade committen
`b196564` har samma filträd som mergecommitten `5fd10ab`. Den fulla kodsviten körs
inte på nytt för denna HTML- och dokumentuppdatering. Ingen riktig modell eller
delad Lakebase har anropats i detta uppdrag.

## Leveranskontroller

- Båda HTML-kopiorna kontrollerade: samma innehåll, endast uppdateringsunderlagets
  relativa länk skiljer dem åt.
- Alla 25 operationsnamn, typer och åtkomstnivåer kontrollerade mot körkodens
  register för den 25 oktober respektive 1 november, utan databasanslutning.
- 19 kartknappar och motsvarande detaljrutor kontrollerade; samtliga klick provade
  i webbläsare, med rätt rubrik och exakt en aktiv markering efter varje klick.
- Åtta SVG-diagram, unika element-ID:n, interna ankare, kartans filhänvisningar,
  kodradantal och teststatistik kontrollerade. Testkategorierna summerar till 1 124.
- Sidhuvud, bolagskarta, byggordning, datamodell och agent-/regeländringsdiagram
  granskade visuellt i webbläsare. Vid skrivbordsvyn (1 237 px) har sidan inget
  horisontellt överflöde. Diagrammet för regeländring visar möjliga berörda
  åtgärdsområden och uppföljning, utan numrerat visningsmanus.
- `git diff --check` godkänd. Ingen ny produktregel, behörighetsändring,
  databasoperation eller driftsättning ingår.
