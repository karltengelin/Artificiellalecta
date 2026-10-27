# Teststrategi – grupper, beroenden och ändringsstyrt urval

> **Infört:** 2026-10-25 på operatörens begäran.
> **Postgres-prov:** aktivt val och ändringsstyrt urval enligt B-040 (2026-10-27).
> **Omfattning:** teststruktur och körverktyg; produktregler och agentmandat ändras inte.

## Syfte

Under utveckling körs relevanta tester för ändringen och dess användare. Hela den befintliga
sviten används som bred integrationskontroll. En helkörning behöver inte upprepas på samma
oförändrade, redan verifierade kodläge utan nya fel eller annan olöst osäkerhet.

Verksamhetsindelningen följer det framtida bolaget: försäkring, premier, pension, betalning,
kapital, ekonomi, risk, regelefterlevnad, kommunikation, insikter, rapportering och simulering. Tekniska grupper följer dagens
implementation: tjänstelager, AI, agenter, webb, data, design och körverktyg. Flödesmotor och
teamsamverkan har ett eget målområde. Ingen testfil behöver flyttas för denna indelning.

## En gemensam katalog

[`tests/suites.toml`](../tests/suites.toml) är källan till:

- Gruppernas testfiler, beskrivningar och status. En fil kan tillhöra flera grupper.
- `dependents`: de grupper som använder gruppens kod. Sambandet följs transitivt vid kodändring.
- Ändringsregler för kod, konfiguration, dokument och genererade underlag. Alla matchande regler förenas.
- Egenskaperna `security`, `integration` och `postgres`, oberoende av verksamhetsområde.
- Postgres-regler: vilka Postgres-prov en ändring berör (se Miljöer nedan). De väljer inga grupper.

Status `active` betyder att gruppen används för befintlig kod; det är inget mått på fullständig
kodtäckning. `partial` betyder att endast en del av målområdet är byggd/testad, exempelvis
rapportformat eller portföljmodeller. `planned` betyder **ännu utan tester**. Verktyget vägrar
köra en sådan uttryckligt vald eller ändringsberörd grupp; en tom grupp ger inget grönt resultat.
Att köra `--all` verifierar bara befintliga tester och redovisar de otestade målområdena separat.

Katalogen kontrolleras även när vanlig pytest startar. Nya eller borttagna testfiler måste
uppdateras i katalogen. Ett namnbyte på ett funktionsspecifikt Postgres-prov måste också
uppdatera markörselektorn; annars stoppas körningen i stället för att tappa klassificeringen.

## Välja och köra

Från reporoten, med projektets Pythonmiljö:

```powershell
# Inventering och kontroll av katalogen – inga tester körs
python scripts/testing/run_tests.py --list
python scripts/testing/run_tests.py --check

# Snävt urval under utveckling; utan --run visas bara planen
python scripts/testing/run_tests.py --suite reporting
python scripts/testing/run_tests.py --suite reporting --run

# Ett område med dess kända användare
python scripts/testing/run_tests.py --suite premiums --dependents --run

# Ändringsstyrt urval, med beroenden
python scripts/testing/run_tests.py --changed --base origin/main
python scripts/testing/run_tests.py --changed --base origin/main --run

# Hela den befintliga lokala sviten
python scripts/testing/run_tests.py --all --run

# Ändringen med de Postgres-prov den berör, mot den isolerade testdatabasen
python scripts/testing/run_tests.py --changed --base origin/main --run --postgres
```

`--suite` kan upprepas; testfiler dedupliceras. Utan `--dependents` är det ett avsiktligt
snävt utvecklingsurval, inte hela ändringens regressionskontroll. Verktyget skriver ut
berörda sökvägar, orsaker, grupper efter beroenden, testfiler och vald miljö.
Felkod från pytest förs vidare. Fel i katalog, Git-bas eller ett otestat valt målområde ger kod 2.
Ingen ändring eller enbart känd förklarande dokumentation kan ge noll valda tester:
det redovisas som **inget testresultat**, inte som en godkänd svit.

### Hur Git-urvalet fungerar

`--changed` förenar committade ändringar sedan förgreningspunkten mot basen med stageade,
ostageade och otrackade filer i arbetskopian. Både gammal och ny sökväg vid namnbyte tas med.
Ingen fetch görs automatiskt; synka referensen till main enligt projektets arbetsregler.
Efter att en branch mergats kan dess diff mot `origin/main` vara tom. Välj då `--all`,
en uttrycklig grupp eller en bas före integrationsändringen för den kontroll som ska göras.

| Typ av ändring | Urval |
|---|---|
| Rapportmall | Rapportgruppen |
| Premiemotor/produktparametrar | Premier och kända beroenden, bland annat tjänster, agenter, webb och insikter |
| Beståndsanalys | Insikter och tjänstelagrets operation som använder beräkningen, vidare till dess användare |
| Tjänstelager/åtkomst | Brett urval av tjänster och deras användare |
| Gemensamma modeller, conftest, testkatalog, testverktyg eller projektberoenden | Hela befintliga sviten |
| Ändrad testfil | Den filen direkt; delade testhjälpare ger hela sviten och kodändringar i samma diff kan utvidga urvalet |
| Produktregler, regelverkskällor eller agentinstruktioner i Markdown | Berörda systemtester; filerna behandlas som systemindata |
| Känd förklarande dokumentation | Ingen Python-testkörning om ingen annan regel också matchar; granska innehåll och länkar |
| Okänd sökväg/påverkan | Hela befintliga sviten |

Detta är en uttrycklig, konservativ beroendekarta, inte automatisk kodtäckningsanalys.
Importberoenden, dynamiska register och lästa filer behöver granskas när koden växer.
Importer mellan testmoduler kontrolleras särskilt: en testfil som också återanvänds som
hjälpare måste ha en regel för hela sviten. Den får inte behandlas som en isolerad teständring.
Ett grönt resultat bevisar inte att ny kod utan relevanta tester fungerar.

## Miljöer och direkt pytest

Körverktygets standard är **lokala tester**: det väljer bort markören `postgres` och
tömmer alla fyra testanslutningsvariablerna i underprocessen så att `.env` inte återaktiverar dem.
Det gör inga riktiga modellanrop. Röktest med verkliga modeller är separata diagnosskript.

Postgres-proven körs bara efter ett **aktivt val**. Adresserna i `.env` räcker inte: proven
med markören `postgres` hoppas över med ett skäl om inte `RUN_POSTGRES_TESTS=1` är satt i
skalet. Värdet får inte ligga i `.env` – pytest vägrar starta då – så att proven inte blir
standard igen. Mot den isolerade databasen tar de omkring åtta av sviten tio minuter
(mätt 2026-10-27), medan resten av sviten tar ungefär två.

`--postgres` sätter det aktiva valet för underprocessen och kräver `SERVICES_TEST_POSTGRES_URL`.
Rollproven kräver också sin roll: `SERVICES_TEST_AGENT_POSTGRES_URL`, eller för aktuarie och
compliance teamets egen adress med den gemensamma rollen som reserv. Adresserna ska peka på
en isolerad testdatabas. Befintliga skydd och projektets databaskoordinering enligt
AGENTS.md §4.5 gäller.

**När Postgres-proven ska köras.** Katalogens Postgres-regler pekar ut vilka prov en ändring
berör. `--changed` listar dem och varnar – före och efter en lokal körning – att de inte
körts; med `--postgres` tas de med även om deras fil inte ingår i de valda grupperna.

| Ändring i | Postgres-prov |
|---|---|
| `src/models/**`, `src/utils/migration*.py`, `scripts/migrations/**` | `test_services_postgres` och migreringsproven |
| Tjänstelagrets transaktion, godkännandekö, tjänst och anslutning | `test_services_postgres`, agentrollens prov |
| Låsande skrivoperationer och händelseloggen | `test_services_postgres` |
| `src/utils/agent_roles.py`, `grant_agent_role.py`, åtkomstregistret | de tre rollproven |
| `src/utils/demo_data.py` | aktuariens och compliance rollprov (de seedar demobeståndet) |
| En testfil med Postgres-prov | dess egna Postgres-prov |

Utöver det körs `--all --postgres` före migrering eller seed mot Lakebase och som regelbunden
kontroll. En fil som skapar scheman i testdatabasen (`isolated_schema`) måste ha markören
`postgres`; katalogkontrollen stoppar annars. Lokal SQLite verifierar inte Postgres radlås
eller rättigheter.

Vanlig pytest finns kvar. Grupperna blir markörer med prefixet `suite_`:

```powershell
python -m pytest -m "suite_reporting and not postgres" -q
python -m pytest -m "security and not postgres" -q
```

Direkt pytest följer samma aktiva val: Postgres-proven hoppas över om inte
`RUN_POSTGRES_TESTS=1` är satt i skalet. `integration` beskriver samspel mellan komponenter
och betyder inte automatiskt extern anslutning. Markörer som anges för en hel fil omfattar
alla dess testfall, även när filen också innehåller mindre komponenttester.

## Arbetsgång för människor och byggagenter

1. Under utveckling: kör ändrade funktioners tester eller en uttrycklig grupp.
2. Före leverans: granska ändringsplanen och kör berörda grupper med beroenden.
3. Inför integration: synka senaste main och kör hela lokala sviten för kodändringar,
   samt de Postgres-prov som `--changed` pekar ut (`--postgres`). Ren förklarande dokumentation
   kräver normalt innehålls-/länkkontroll, inte en ny helkörning av Python-sviten.
4. Verifiera det sammanslagna resultatet enligt AGENTS.md §4.4/4.6/4.7. Om samma trädtillstånd
   redan testats behövs ingen identisk helkörning; nytt otrövat kombinerat kodläge testas på nytt.
5. Redovisa kodläge, testurval, skäl och resultat. Skilj överhoppade/bortvalda prov från godkända.

När ett område byggs ut: lägg till testfilen i rätt verksamhets- och teknikgrupper, ändra
`planned` till `partial`/`active` först när tester finns, och granska ändringsregler och
beroenden. Lägg inte in tänkta framtida beroenden till tomma grupper i dagens aktiva kedja.
För nya kodområden gäller brett reservurval tills en granskad regel finns.

Behov för verksamhetsmotorer och hela månadssimuleringen finns i
[processöversikten](../01_domän/processer_översikt.md). Teststrukturen gör de luckorna synliga;
den implementerar inte de saknade motorerna eller deras verksamhetsfall.
