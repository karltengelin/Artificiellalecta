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
