# Samtal med aktuarien – arbetsväg och drift

Beställt 2026-11-02. Plan: [Aktuarien som verksamhetskollega](../projekt/06_avdelningsfunktioner/AKTUARIE_DIALOG_PLAN.md).
Metod: [aktuariell analys](../03_skills/beräkning/aktuariell-analys.md).

## Människans arbetsväg

Öppna `/team/aktuarie/dialog`, logga in som operatör och skriv uppdraget.
Följdfrågor återanvänder samma samtal. Agenten väljer själv data och analys ur
sin katalog. Det finns inga separata knappar för exempelvis osäkerhetsbedömning.
Registervyer och mänskligt fastställande finns kvar på teamytan.

Samtalet, körstatus och leveranser sparas i vald databas. Varje användarmeddelande
är en körning med teamets ordinarie tak i `ecosystem.yaml`. Idempotensnyckel och
unik aktiv beställning skyddar mot dubbelklick och samtidiga uppdrag. Avbryt
stoppar kommande verktygsanrop och publicering; ett redan påbörjat modellanrop
kan fortfarande kosta pengar. Ett avbrutet arbete körs aldrig om automatiskt.

## Arkitektur och data

`ActuarialDialogue` återanvänder harness, körjournal, resultatschema och AI-klient.
`actuarial_workbench` är teamets domängateway, med en katalog av typade kontrakt.
JSON-argument valideras per operation. Ett litet yttre verktygsschema undviker
den tidigare begränsningen i Anthropics samlade strikta verktygsgrammatik.

- Befintliga bestånds-, premie-, parameter- och värderingsläsningar görs med
  aktuariens begränsade databasroll. Ingen privilegierad reservanslutning används.
- Tunga analyser utförs av en uttrycklig systemarbetare med den befintliga
  serveranslutningen, via `perform_actuarial_analysis`. Detta är ett avgränsat
  domänkontrakt, inte SQL/Python-exekvering eller rollbyte i agentanslutningen.
  Individutdrag läses endast i serverns beräkningskod. Skyddade aggregat går ut.
- Nya tabeller: `actuarial_datasets`, `actuarial_conversations`,
  `actuarial_turns`, `actuarial_analyses`. Agentrollen ges inga nya tabellrättigheter.
- Erfarenhetsdata registreras genom `register_actuarial_dataset`, HUMAN_ONLY.
  Källreferens, definition, syntetisk märkning och kontrollsumma är obligatoriska.
  En rättelse får ett nytt id. Importskriptet validerar utan DB-anslutning som standard.
- Grundförslag går genom befintliga `propose_valuation_basis` som agentförslag
  med APPROVAL. Därefter kan människan registrera och anta grunden i separata steg.
- SVG-diagram och Markdown-rapporter lagras med kontrollsummor i databasen.
  Diagrammens tal kommer bara ur sparad analys. PDF använder befintlig rapportmotor
  och registrerade DM Sans-filer. Underlagen kan hämtas som JSON.

## Start och införande

Installera projektberoendena, inklusive SciPy, i den Pythonmiljö som startar webben.
Ingen ny extern tjänst eller konto behövs.

```powershell
python scripts/web/start_ui.py --db demo --actuary-workspace --report-font-dir <mapp-med-DM-Sans>
```

Demo lägger till saknade tabeller. Mot Lakebase gör webben ingen migration.
Samordna enligt AGENTS.md §4.5 och ta backup före skarp migration:

```powershell
python scripts/migrations/migrate_actuarial_workspace.py
python scripts/migrations/migrate_actuarial_workspace.py --apply --backup <backupmapp>
python scripts/web/start_ui.py --db lakebase --actuary-workspace --report-font-dir <mapp-med-DM-Sans>
```

Migrationen skapar de fyra tabellerna tomma, kontrollerar befintliga radantal
och stoppar vid ett delvis infört schema. Historik, grunder och bestånd ändras inte.
`scripts/analysis/import_actuarial_dataset.py` validerar levererat utfall;
`--apply --operator <id> --reason <motivering>` importerar genom tjänstelagret.

## Aktuella gränser

Detta ger generella aktuariella analysverktyg kring befintliga verksamhetsmotorer.
Värderingens produktomfång är fortsatt A6:s referensplan och avgränsningar.
Kassaflödet avser intjänad garanti och driftkostnader, inte framtida nyteckning
eller återbäringsutbetalningar. Framtida betalnings- och planmotorer ansluts via
samma tjänstelager. En jämförelse av värderingar redovisar grundeffekt men
övriga rörelser är ännu inte uppdelade per verksamhetshändelse.

Dödlighetsmodelleringen är en externförankrad nivå-/förbättringsmodell med ett
senare valideringsår, inte en generell Lee–Carter/CBD-motor. Eget litet bestånd
räcker inte för att bevisa långsiktiga förbättringstrender. Syntetiskt utfall
används bara för arbetsgång och kontroller. Kostnadsanalysen har inga statistiska
intervall utan information om kostnadsvarians. ALM och solvens behöver egna motorer.

Webbprocessen är en lokal arbetare. Processavbrott kan lämna ett uppdrag som
pågående; operatören avbryter det i dialogen och beställer ett nytt meddelande
efter kontroll av leveranserna. Automatisk återstart eller schemalagd drift ingår inte.

## Verifiering och införandestatus 2026-11-02

Implementationen levereras från `codex/aktuarie-dialog-analys`. Operatören har
godkänt integration till `main`. Den 2026-11-02 var ingen skarp schemamigration
genomförd; se införandet 2026-11-03 nedan.

- Helkörning genom `run_tests.py --all --run --postgres`: **1 677 godkända,
  ett fel**. Felet var en gammal förväntan på menytexten ”Kommande arbetsvägar”.
  Förväntan rättades till ”Kommande registervyer”; efter synk med senaste
  `origin/main` passerade det provet tillsammans med aktuariens lokala prov,
  katalogkontroller och skriptens CLI-kontroller: **59 godkända, 716 bortvalda**.
- Efter slutlig instruktionstext och rättad PostgreSQL-testuppsättning kördes
  dialog-, profil-, skill-, katalog- och menyproven igen: **86 godkända,
  689 bortvalda**. Inga överhoppade prov i dessa urval. Ruff passerade för
  ändrade Pythonfiler; befintliga lintfel utanför ändringen har inte rättats.
- Inför den godkända integrationen kördes hela lokala sviten på slutligt
  kodläge: **1 581 godkända, 99 PostgreSQL-prov bortvalda, inga fel**
  (`run_tests.py --all --run`). PostgreSQL-verifieringen redovisas separat här.
- Ett utökat isolerat PostgreSQL-prov kördes därefter: **1 godkänt,
  395 bortvalda**. Det verifierar tom migration och omkörning, samtidiga
  beställningar, verklig begränsad databasroll, tillåtna läsningar och en
  serverberäknad FTA. Rollen nekas individutdrag och nya interna tabeller.
- Statistiken kontrolleras mot kända oberoende Poisson-intervall; scenarier
  mot riktning och PV-avstämning; dödlighetsmodellens skattning mot ett
  undanhållet år. Även källmanipulation, småcellsskydd, avbrott, idempotens,
  dialogägarskap, inloggning/CSRF och godkännandekön har prov.
- Riktig modell via ordinarie harness (`openai:gpt-6.1-sol`): katalog och grund,
  överlevnadsanalys, diagram, rapport och validerat slutsvar **godkända**,
  0,059077 USD. Modellvalet överstyrdes enbart för detta prov; bolagets
  modellpolicy ändrades inte. Anthropic-försöket stoppades av otillräckligt
  kontosaldo efter delresultat och räknas inte som godkänt.
- Den riktiga modellens PDF renderades och alla tre sidor granskades med
  DM Sans och vektordiagram. Ingen tom slutsida. Webbens dialog och leveranser
  granskades visuellt med separat skriptad testmodell; sista inskickningen av
  en följdfråga kunde inte utföras när datorverktygets automatiska granskning
  stoppade anropet på grund av användningsgränsen. HTTP- och harnessprov för
  följdfrågor passerade; det sista visuella momentet räknas inte som utfört.
- Lakebase kontrollerades i en uttryckligen **skrivskyddad transaktion**:
  torrkörd migration och scenario på befintliga 501 försäkrade, med känt
  värderingsdatum, grund, kurva och utdragskontrollsumma. Analysen fungerade
  utan nya tabeller. Ingen migration, observation eller värdering sparades.

En separat lokal granskningsserver kan startas med kommandot ovan. Den använder
demodata. Verkliga erfarenhetsanalyser kräver avstämda observationsleveranser via
importkontraktet; sådana skapas inte av agenten.

**Tillägg 2026-11-03:** arbetsbänken kan också välja `monthly_fta_change` för
en stängd, avstämd syntetisk månadsjournal. [Kontrakt, lokal körning och gränser](avstamd_fta_manad.md).
Den är skild från `compare_valuations`, som fortsatt är en delanalys. Inga
Lakebase-tabeller, grunder, data eller agenträttigheter har införts genom tillägget.

## Införande i Lakebase 2026-11-03

Operatören godkände införandet och bekräftade att ingen annan agent körde mot
Lakebase (AGENTS.md §4.5). Backup togs först till `backups/20261103T203424Z`.
`migrate_actuarial_workspace.py --apply --backup …` skapade de fyra tabellerna
tomma. Alla 22 befintliga tabellers radantal var oförändrade, bland annat 501
försäkrade, 499 försäkringar och 15 097 premietransaktioner. En efterföljande
torrkörning rapporterade att tabellerna finns.

Webben startas mot Lakebase med `--actuary-workspace`. Skrivbordsgenvägen gör inte
det; den startar grundläget utan aktuariedialog. `--report-font-dir` behövs bara
om DM Sans inte ligger i `tmp/pdfs/fonts`. Dialogsidan efter migrationen och en
första riktig dialogkörning mot Lakebase är inte verifierade i detta steg.
Lakebase har ännu inga sparade värderingar (`valuation_runs` och
`valuation_extracts` är tomma).
