# Aktuariens värderingssidor

**Byggt 2026-10-31** på `codex/aktuarie-varderingar`, ovanpå A3 och A5/A6.
Uppdraget omfattar människans värderingsarbete enligt B-042 och
[värderingskontraktet](../projekt/06_avdelningsfunktioner/VARDERINGSKONTRAKT.md).

## Arbetsväg

| Adress | Innehåll och handling |
|---|---|
| `/team/aktuarie` | Senaste fastställda bas med FTA, senaste körningar med typ, version, status och kontrollutfall samt länkar till värderingsarbetet |
| `/team/aktuarie/varderingar` | Sparade körningar och formulär för ny värdering |
| `/team/aktuarie/varderingar/<id>` | Belopp, datum, grund/kurva, kontroller, begränsningar, ej beräknade fall, läge × födelsekohort, källhashar, versioner och granskningsformulär |

1. Logga in som operatör och öppna **Värderingar** i teammenyn.
2. Ange månadsslut och motivering. Bas använder kvartalsslut och automatiskt de
   grunder som gäller datumet. För scenario kan antagen SIM-V och FI-SIM väljas
   uttryckligen, även om de inte gäller datumet.
3. Beräkna och spara utkast. Motorn gör beräkningen i betrodd kod och resultatet
   visas efter avslutat tjänsteanrop. Verksamhetsstopp visas med skäl; inget sparas.
4. Granska belopp, kontroller, begränsningar och underlag. Bekräfta granskningen
   och ange beslutsmotivering för att fastställa en bas. En tidigare bas för samma
   datum ersätts och bevaras. Scenario har ingen fastställandeknapp och nekas även
   av tjänsteoperationen och databasen.

## Användning och kvarstående underlag

Värderingssidorna använder webbens redan valda tjänst och databas och kräver
ingen AI-klient, modellnyckel eller rapportadapter. De finns även utan
`--actuary-workspace`; den flaggan ansluter A3:s rapport-/frågeadaptrar.

```powershell
python scripts/web/start_ui.py --db lakebase
```

Operatörslösenfras konfigureras vid behov interaktivt med
`scripts/web/set_operator_password.py`. Starta om webbprocessen efter konfigurering
och efter installation av denna kod. Den befintliga lokala autentiseringens
loopback-/HTTPS-gräns består. Det här bygget kräver ingen migration, ny roll eller
ändrad behörighet.

**Verifierat i aktuellt Lakebase-register 2026-10-31**, genom tjänstelagrets
`get_valuation_basis` i en skrivskyddad transaktion:

- SIM-V-2026-01 är antagen från **2026-12-31**.
- FI-SIM-2026-10 är antagen från **2026-10-31**.
- AVK-SIM-2026-01 är antagen och har avkastning till och med **2026-10**.
- Alla tre innehållskontrollerna är godkända.

En första bas per 2026-12-31 behöver därför komplett avkastning även för november
och december. Befintlig verksamhetslogik stoppar körningen tills underlaget finns.
Ett scenario för ett tidigare månadsslut kan ange SIM-V och kurvan uttryckligen;
det är fortsatt scenario. Inga giltighetsdagar eller underlag har ändrats för
att möjliggöra användning eller demonstration. Inga värderingar sparades eller
fastställdes mot Lakebase-beståndet under verifieringen.

## Tjänster, granskning och säkerhet

- Routerna använder `run_valuation`, `list_valuation_runs`, `get_valuation_run`
  och `lock_valuation`, samt antagandebibliotekets läsoperation för formulärvalen.
  Ingen SQL eller beräkningslogik finns i webben. Ingen modell utför beräkningen.
- Fastställandets kontrakt är nu `{run_id, reviewed_checksum}`. Läs
  `get_valuation_run` och använd dess `review_checksum` efter mänsklig granskning.
  Summan binder hela den tillåtna läsprojektionen och `current_locked_run_id`.
  Vid förändrat underlag eller annan fastställd bas krävs en ny granskning.
- Postgres låser beslut per datum i transaktionen, även första låsningen, och
  behåller radlåsen. Beslut, ersättning av tidigare bas och händelselogg sparas
  tillsammans. Systemaktörer och agenter får inte fastställa.
- Alla webbskrivningar kräver verifierad operatörssession, exakt ursprung och
  sessionsbunden CSRF. Identitet hämtas från sessionen. Okända och dubbla
  formulärfält nekas. Engångstoken binder session och handling; fastställande
  binder också körning och granskningssumma. Dubbelklick och återanvändning
  stoppas på servern. Knappen inaktiveras och väntetext visas under anropet.
- Engångstoken är processlokal, liksom befintliga operatörssessioner. Omstart
  ogiltigförklarar tidigare formulär. Körningarna finns i databasen och kan läsas
  igen. Vid okänt utfall hänvisas operatören till listan/körningen; inget nytt
  försök görs automatiskt. Flera webbarbetare med delad inloggning stöds inte.
- Bara tjänstens undertryckta aggregat visas. Dolda värden visas aldrig som noll.
  Kontrolltexter döljs också när totalsumman är skyddad. Läsoperationerna läser
  inte individutdraget och agentens databasrättigheter består.

## Avgränsningar

Detta är en synkron arbetsväg för värdering och mänskligt fastställande.
`valuation_close`, förändringsanalys, avancerade scenarier, bokföringsunderlag
och rapporteringsflödet återstår. Teamöversikten visar senast fastställd bas;
operatörscentralens måttadapter ansluts separat. Motorns ej beräknade fall och
S-04-märkning följer tjänstens resultat. Tillgångssida och konsolidering saknas.

Datautdragets kontrollsumma binder dess historiska garanti-, avkastnings- och
parameterunderlag. Den befintliga läsprojektionen exponerar utdragets hash,
värderingsgrundens och kurvans hash samt skatteparameterns referens; den lämnar
inte ut individutdrag eller dess fullständiga kapitaljournal i webbgränssnittet.

## Verifiering

**Journaladapter 2026-11-03:** A6 kan nu ta ett fullständigt, innehållskontrollerat
journalutdrag för scenario genom betrodd kod. Samma FTA-motor, basregler och
baslås består. [Den avgränsade syntetiska månadsanalysen](avstamd_fta_manad.md)
har eget analysgodkännande; den fastställer ingen basvärdering. A6:s versionsnummer
vid sparande serialiseras nu per datum även mellan journal och webb i Postgres.

Testverktyget är `scripts/testing/run_tests.py`. Webbproven använder verkliga
operationer och isolerad SQLite med uttryckliga testgrunder från 2026-03-31
för lyckade baskörningar. Separata prov behåller startregistrets riktiga
giltighetsdagar och visar stopp för bas och framgång för uttryckligt scenario.
Postgres-proven använder bara egna scheman i `svc_test`, efter operatörens
samordningsbesked i chatten.

Visuell kontroll sker i webbläsaren med faktisk inloggning i en separat lokal
testdatabas och samma mallar/tjänster. Inga externa modeller används. Den tidigare
grundgiltigheten finns enbart i testdatabasen, med uttrycklig testmotivering.
Vid 375 px har listan och formulären inget horisontellt dokumentöverflöde.
Den breda aggregattabellen har avgränsad, tangentbordsnåbar sidledsrullning.

**Testresultat:**

- Ändringsstyrt urval valde hela sviten, bland annat genom testkatalogändringen.
  Efter uppdatering av A3:s förväntan på den tidigare inaktiva menylänken gav
  `--all --run` **1 556 godkända**, **98 Postgres-prov bortvalda**, inga överhoppade.
- `--changed --base origin/main --run --postgres`, avgränsat med pytest-urvalet
  `postgres_aktuarie or TestLockPostgres or migrationen_mot_postgres`, gav
  **36 godkända**, **1 618 bortvalda**, inga överhoppade. Det omfattar aktuariens
  roll, berörda värderingsmigrationer och två samtidighetsfall: samma utkast
  respektive olika utkast med samma granskade bas. Exakt ett beslut lyckas.
  En varning gällde skrivning till pytest:s cache; proven var godkända.
- Kodstil, testkatalog, diffkontroll och de nya dokumentlänkarna är kontrollerade.
  Efter den sista justeringen av mobilens tabellkolumner gav
  `--suite web --dependents --run` **371 godkända**, inga bortvalda eller överhoppade.
  Sandboxens tillfälliga testkatalog sattes med `--basetemp` via `PYTEST_ADDOPTS` under
  repots ignorerade `tmp/`; slutliga lokalkörningen använde `-p no:cacheprovider`.

I webbläsaren verifierades också faktisk inloggning med testlösenfras, ett
verksamhetsstopp för avkastning 2026-11/12 och en sparad scenariokörning.
Webbläsarens konsollogg innehöll inga JavaScript-fel.

- [Lista och formulär på dator](bilder/aktuarie_varderingar_dator.jpg)
- [Lista och formulär vid 375 px](bilder/aktuarie_varderingar_mobil.jpg)
- [Detaljsida vid 375 px](bilder/aktuarie_vardering_detalj_mobil.jpg)
- [Granskningsfält vid 375 px](bilder/aktuarie_vardering_granskning_mobil.jpg)
- [Läsbar aggregattabell vid 375 px](bilder/aktuarie_vardering_aggregat_mobil.jpg)
- [Saknad avkastning stoppar körningen](bilder/aktuarie_vardering_stopp_mobil.jpg)
- [Sparat scenario på dator](bilder/aktuarie_vardering_scenario_dator.jpg)
