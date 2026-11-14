# Bolagsorkestratör i lokal demo

Piloten ligger i projekt 10 och öppnas från **Operatörscentral → Fråga bolaget
· lokal pilot**. Använd en lokal demodatabas och konfigurerad
operatörsinloggning enligt [frågekedjans drift](fragekedja_webb.md).
`python scripts/web/start_ui.py --db demo --company-orchestrator` använder
den konfigurerade modellklienten. För parallell provning av ordinarie vägar
lägg till `--company-questions --actuary-workspace --rule-change-flows` och
ange DM Sans-katalog enligt driftbeskrivningen. För skriptad modell och
isolerad demo kör `python scripts/testing/run_tests.py --suite orchestration --run`.
Testet `test_company_missions.py` kör samma webbformulär som operatören.

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
- Den nya lagringen använder mönstret från ärendekön och aktuariedialogen,
  jämte flödesmotorns kanoniska hash. Den generella ordningen och stegtabellen
  i flödesmotorn är avsedda för fasta definitioner. Äldre rader behåller sina
  ursprungliga identiteter och kan läsas av nuvarande adaptrar.
- Piloten hanterar en parameter i taget med stöd av den befintliga
  aggregattjänsten. Blandade ändringar, kodberoende förhandsberäkning och
  områden utanför katalogen kan utredas och lämnas för mänsklig bedömning.
  Pilotkatalogen har ännu ingen beståndsrapportadapter. Demodata och
  skriptade modeller bevisar körvägar och kontroller. Verksamhetsbedömning av
  nya tolkningar och verkligt modellval ingår i nästa granskning.

## Konsumenter och övergångsvillkor

| Konsument och normal ingång | Tillstånd, befogenhet och verifiering | Nästa ändring, ägare och återgång |
|---|---|---|
| Bolagspilot `/central/bolagsuppdrag`, `--company-orchestrator` | Demo med inloggning. Beställningar och beslut i `company_missions`, specialistutkast och körjournaler i befintliga gatewayformat, stabila domänlänkar. Lokala webbprov av beslut, återstart och kvitton. | Projekt 10 och harness. Verifiera riktig modell i isolerad demo, lås lagrings- och driftskontrakt och lägg till granskad rapportförmåga före ordinarie start. Stäng flaggan för att pausa. |
| `company_question` via `QuestionConsole`, `/central/fragor` och `/team/aktuarie/uppdrag` | `answer → render → review → deliver`. B-041. Registrerat bestånd och betalmarkerade premier. Ses i båda ytorna. Operatören granskar versionsbunden PDF/Markdown. Spår, avslag och ersättningslänkar i webbsuiten. | Projekt 10, 2 och aktuarien. Anslut adaptern som en hel rapportförmåga med stabilt beställnings-id och återläst status. Prova gamla adresser, beslut och filhashar. Flytta bara nybeställning först. Återställ formulärlänk vid behov. |
| `product_report` via `ProductReportConsole`, `/team/aktuarie/rapporter` | `summary → render → review → deliver`. Årsperiod och bestånds-/premieaggregat under teamets åtkomst. Versionsbunden rapport, utkast, spår och avslag. Provas i produktsrapport- och webbsuiten. | Projekt 6 och 10. Samordna med B-047 steg 1 om beståndsläsningen och verifiera rapporten med gammal och ny datamodell. Bevara teamytans direktstart tills ny väg finns. |
| `rule_change_parameter` v2, `/floden`, `/parametrar`, `/godkannanden` | `tolkning/g1/insikt/g2/regeltext/aktivering/verifiering`. Tolkning och analys under respektive team, mänskliga grindar och separat tjänstelagerbeslut. Äldre versioner och grindhashar läses. Motorn kräver matchande definition vid avancering. Prov i orkestrerings- och webbsuiten. | Compliance, aktuarie och projekt 10. Kör beräkningen efter B-047 steg 1 eftersom den läser `policy_states`. Jämför mandat, granskning och kvitton. Stäng ny start först när motsvarande dynamisk väg är godkänd. Driv pågående ärenden till säkert avslut i originaladaptern. |
| `rule_change_code` v1, `/floden` med `--rule-change-flows` och projekt 11 | `tolkning/g2/bestall_utveckling`. Äldre ändringsärenden länkar ursprung och kvarstående status via FLOW-id. U1–U6 har eget leveranstillstånd; U4/U5 prov i webbsuiten. | Projekt 11 och Compliance. Stäm av ursprung, antagen version, testbevis och installerad kodversion. Behåll båda ursprungsläsarna. Återställ startflaggan vid behov. |
| `premium_month_review` v1 och aktuariens arbetsbänk | Definitionen `prepare/review/accept` monteras i P6-MANAD-001:s verifieringsprov. Aktuariens dialog och månadsanalys använder separata tjänster. Fast avstämning och hashbundet mänskligt beslut. | Projekt 6 och paket B. B-047 steg 2/3 ändrar källan från S-04 till journalen för operativ stängning. Behåll testvägen och verifiera scenario och operativ signering när journaladaptern finns. |
| Motor, migreringar, rapportarkiv och agentekonomi | `flows`, `flow_steps` och `flow_gate_decisions`. Sparad versions- och revisionsidentitet, aktör och beslutshash. Leveranser i `logs/deliveries/<flow_id>/v<version>/`; `trace` läser journalen. Telemetrin deduplicerar försök inom miljö och dataset. | Harness, projekt 10 och drift. Bevara motorn så länge en anropare eller historikläsare kräver den. Före eventuell städning inventeras startskript, reservvägar, läsare och testdata på nytt. Exportera och verifiera isolerad kopia innan en eventuell migrering. |
| Ärendearbetare och aktuariedialog | Domänägda köer, mandat, källor och resultat. Fortsätter via respektive yta. | Projekt 1 och 6. Koppla endast uttryckligt beställda domänförmågor med testad leverans och väntan. |

## Beslutsförslag inför ordinarie införande

Precisera B-016 och B-026 så att öppna bolagsuppdrag kan välja
specialistuppdrag under arbetets gång i centralen. Behåll fasta
verksamhetskontroller, uppdrags- och beslutsversioner och behöriga
domängrindar enligt B-036, B-038–039 och B-041. B-037:s krav på lokalt
avgränsade scenarier och verksamhetsstyrda förmågor gäller även piloten.

Efter operatörens granskning uppdaterar projekt 10 sin projektplan och
startmatris. Harness beskriver den tekniska samordningsprofilen, det
varaktiga uppdragskontraktet, budgetförbrukningen och körspåren.
Driftbeskrivningen lägger till start, stopp, backup och
återöppning. Backloggen följer upp riktig modell, rapportadapter,
miljöverifiering och övergång per gammal startväg.

## Baslinje och parallellt arbete

Piloten utgår från `7119cd0`, där B-047 är mergat. Paket B steg 1 finns
separat på `claude/paket-b-steg1-193c87` (`ebe2772` under pilotarbetet).
Båda grenarna kompletterar `tests/suites.toml` i olika avsnitt. Kör om
bestånds-, premieeffekt-, rapport- och månadsproven på det kombinerade
kodläget före integration. När B-047 steg 2 byter källa ska projekt 6 jämföra
S-04-scenariot med journaladaptern som del av övergången.

## Verifiering 2026-11-14

| Prov | Miljö | Godkända | Bortvalda | Överhoppade | Fel |
|---|---|---:|---:|---:|---:|
| Ändringsstyrt urval, hela lokala sviten | `a742ceb`, SQLite och skriptade modeller | 1 834 | 104 | 0 | 0 |
| Ändringsstyrt Postgres-urval, markör `postgres` | Isolerade scheman i `svc_test`, kodläget `0764ed1` | 104 | 1 834 | 0 | 0 |
| Premieeffekt, bestånds- och produktrapporter, månadsgranskning, uttagsdelar och pilot | Isolerad kombination av pilotens kod och B-047 steg 1 (`ebe2772`), SQLite | 118 | 1 221 | 0 | 0 |

Ändringen efter Postgres-provet gäller det fiktiva källunderlaget och
lokala prov. Pilotens SQLite-lagring och modellval har endast provats
lokalt. Demowebben svarade på pilotens ingång och de äldre ingångarna.
Kodfallet verifierade projekt 11:s demokvitto med en syntetisk kandidat.
Före ordinarie införande återstår modellprov, en adapter för den befintliga
beståndsrapporten och operatörens ställningstagande till övergången.
