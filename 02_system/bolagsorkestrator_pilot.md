# Bolagsorkestratör i lokal demo

Öppna **Operatörscentral → Fråga bolaget** på `/central/fragor`.
Starta en lokal demo med `python scripts/web/start_ui.py --db demo --company-orchestrator`
och konfigurera [operatörsinloggningen](operator_inloggning.md). Modellklienten
väljs av den befintliga AI-konfigurationen. För skriptad modell och isolerad
demo kör `python scripts/testing/run_tests.py --suite orchestration --run`.

1. Ställ en dokumentfråga, exempelvis *Vad säger försäkringsvillkoren om
   uppskjutet uttag?* Registrera och kör nästa del. Läs källhänvisning och
   körspår. En följdfråga visas som ny beställningsversion.
2. Ange *Utred den här nya regeln, visa premieeffekten om den behövs för
   beslutet och förbered genomförandet.* Lägg till fiktiva bevakningskällan
   `K-SIM-PARAM-2027`. Kör en del i taget. Läs Compliance-utkastet, granska
   tolkningen, kontrollera aktuariens beräkning och granska regelbeslutet.
   Ange verifierad regeltextreferens före förslaget till schemaläggning.
   Avgör förslaget i godkännandekön. Läs sedan domänkvitton i bolagsuppdraget.
   En schemalagd framtida parameter är verifierad när registrets versioner
   på båda sidor av giltighetsdagen motsvarar beslutet. Den äldre
   `K-SIM-ITP-2027` innehåller även en övergångsfråga om återupptagen
   premiebetalning som kan kräva en separat bedömning.
3. Upprepa med `K-SIM-KOD-2027`. Läs tolkning och utkast, välj berörd regel,
   ange version, giltighet och verifierbar effekt. Nästa körning registrerar
   beställningen i projekt 11. Följ U5:s demogranskning från ändringsärendet.
   I det automatiserade provet levereras kod- och testbevis från en
   avgränsad demokandidat. Uppdraget läser in kvittot efter verifieringen.
   Om en premieanalys kräver den nya koden är utfallet en uppföljningspunkt
   knuten till den testade versionen.
4. Stäng av pilotflaggan vid omstart för att pausa nya starter och
   fortsättningar. Inloggad operatör kan öppna tidigare uppdrag, utkast,
   körspår och domänlänkar. Domänytorna har egna beslutsvägar. Vid avbrott
   som lämnat ett aktivt anspråk ska operatören först stoppa den tidigare
   processen och därefter markera avbrottet på uppdragssidan. Vid ett okänt
   domänutfall väljer operatören avstämning. Vid ett avbrutet agentsegment
   tar operatören över och läser journal och eventuella utkast.

## Uppdragskontrakt och gränser

- Teamkatalogen beskriver verksamhetsteamens uppdrag, profiler, teamledare
  och antal konfigurerade agenter. Den anger projekt 11:s separata demokörning
  för utvecklaragenten. Team utan profiler anges med noll agenter.
- Orkestratören läser katalogen internt med `coordinate_company_work` och väljer
  mottagande team utifrån beställningens mål. Katalogen visar också vilken
  beställningsväg som är ansluten i piloten. Underlagskrav och granskningar
  prövas i respektive beställnings- eller beslutsväg. **Fråga bolaget** visar
  dina beställningar och vilket team som medverkar i varje uppdrag.
- Tabellen `company_missions` ligger i den lokala demofilen. En rad innehåller
  ett versionsstämplat och storleksbegränsat uppdragsdokument. Beställaren är
  den autentiserade operatören. Miljö, dataset, kontrakt, policy, rotbudget,
  preciseringar, anspråk, resultat och beslut binds i betrodd kod.
- Samordningsprofilen tillhör centralen tekniskt. Den har källverktyg och ett
  uppdragsbundet samordningsverktyg. Compliance och aktuarien kör sina
  ordinarie ledarprofiler med avgränsat verktygsurval. Utveckling får en
  U4-beställning via `ChangeRequests`. Parametermandat binds till nyckel,
  värde, giltighetsdag och tio års horisont efter operatörens tolkningsbeslut.
- Segment och specialistkörningar drar från samma kvarvarande harnessbudget.
  Läsvyn summerar känd kostnad per körning. Vid avbrott reserveras kvarvarande
  segmenttak för budgetprövningen och kostnadstäckningen markeras. Varje
  modellförsök har sin ursprungliga journalreferens. U5:s demokvitto läses
  separat. Databasen sparar ingen rå modellkonversation.
- Nästa segment startas med en explicit knapp. Specialistresultat och
  tolkningsbeslut köar fortsatt arbete. En knapp läser tjänstelagrets beslut
  eller projekt 11:s kvitto och köar syntes efter verifierat utfall.
  Pilotens nya uppdrag är sekventiellt anspråkstagna med villkorlig
  versionsuppdatering. Samma beställningsnyckel med ändrat underlag ger konflikt.
- Vid möjligt avbrott efter skrivning söker betrodd kod först efter det
  specifika kvittot. Godkännandekön har ett deterministiskt förslags-id för
  exakt regelbeslut. Projekt 11 använder sin stabila ursprungsreferens. Ett
  operatörsbeslut binder version och resultathash, inklusive analysens hash
  där den ingår. Ändrade eller saknade källor och utkast kräver ny granskning.
- Piloten hanterar en parameter i taget med stöd av den befintliga
  aggregattjänsten. Blandade ändringar, kodberoende förhandsberäkning och
  områden utanför katalogen kan utredas och lämnas för mänsklig bedömning.
  Pilotkatalogen har ännu ingen beståndsrapportadapter. Demodata och
  skriptade modeller bevisar körvägar och kontroller. Verksamhetsbedömning av
  nya tolkningar och verkligt modellval ingår i nästa granskning.

## Tidigare uppdrag

De fasta beställningarna och deras fördefinierade steg är avvecklade.
Fråga bolaget tar en beställning i fritext. De fasta blanketterna för
beståndsstatistik, produktrapport och regeländring har tagits bort.

Sparade uppdrag, även avbrutna eller väntande, går att läsa i
`/central/uppdragsarkiv`. Äldre länkar med FLOW-id öppnar samma arkiv.
Arkivet visar sparade beslut, underlag, körspår och rapportfiler.
Rapportfiler verifieras mot lagrade kontrollsummor. Historiken förblir
i de befintliga arkivtabellerna, som nya databaser inte skapar.
Påbörjade domänärenden och godkännanden hanteras i sina respektive ytor.

Aktuariens dialog, värdering, aggregattjänster och månadsgranskning har
egna verksamhetskontrakt. Parameterbeslut och kodändringsärenden
använder fortfarande sina separata godkännande- och leveransvägar.

## Baslinje och parallellt arbete

Piloten utgår från `7119cd0`, där B-047 är mergat. Paket B steg 1 finns
separat på `claude/paket-b-steg1-193c87` (`ebe2772` under pilotarbetet).
Båda grenarna kompletterar `tests/suites.toml` i olika avsnitt. Kör om
bestånds-, premieeffekt-, rapport- och månadsproven på det kombinerade
kodläget före integration. När B-047 steg 2 byter källa ska projekt 6 jämföra
S-04-scenariot med journaladaptern som del av övergången.

## Verifiering före avvecklingen

| Prov | Miljö | Godkända | Bortvalda | Överhoppade | Fel |
|---|---|---:|---:|---:|---:|
| Ändringsstyrt urval, hela lokala sviten | `a742ceb`, SQLite och skriptade modeller | 1 834 | 104 | 0 | 0 |
| Ändringsstyrt Postgres-urval, markör `postgres` | Isolerade scheman i `svc_test`, kodläget `0764ed1` | 104 | 1 834 | 0 | 0 |
| Premieeffekt, bestånds- och produktrapporter, månadsgranskning, uttagsdelar och pilot | Isolerad kombination av pilotens kod och B-047 steg 1 (`ebe2772`), SQLite | 118 | 1 221 | 0 | 0 |

Pilotens SQLite-lagring och modellval provades lokalt. Kodfallet
verifierade projekt 11:s demokvitto med en syntetisk kandidat.
