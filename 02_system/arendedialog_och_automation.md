# Ärendedialog och självständig handläggning

**Datum:** 2026-10-31. **Uppdrag:** operatören beställde planering och implementation
av handläggning i tandem och självständig handläggning. Återkommande ärenden ska
kunna hämtas dagligen och förberedas för mänsklig kontroll. För utvalda fall ska
mänsklig approval senare kunna väljas bort. Vilka ärendetyper som ska omfattas
av dagligt urval och automatisk slutbehandling väljs separat.

Bygger vidare på B-017, B-026, B-028, B-033, B-036 och dialogförslaget
[öppna frågor](oppna_fragor_beslutsforslag.md). Denna beställning preciserar
B-028/B-033 för en särskild, betrodd automationsväg. Ingen ny beslutspost har
lagts i BESLUTSLOGG. Historiska beslut skrivs inte om.

## Plan och genomförande

1. Återanvänd ärende, resursmandat, tjänstelager, modellager och agentloop.
2. Spara dialog och avgränsade arbetsuppdrag med varaktig status. Skilj
   samtal, uppdrag, modellkörning, verksamhetsförslag och avslutat ärende.
3. Exponera deluppdrag, överlämning, komplettering och övertagande i ärendevyn.
4. Låt webbens bakgrundsuppdrag och en fristående köarbetare använda samma
   anspråk, budgetbok och uppföljning. Inför konfigurerbart dagligt urval.
5. Behåll mänsklig granskning som standard. Bygg en smal automationsväg som
   kan slutföra särskilt tillåtna standardärenden utan mänskligt beslut.
6. Verifiera normalfall, nekanden, samtidighet och återhämtning lokalt och
   i isolerade Postgres-scheman. Migrera inte Lakebase-beståndet i detta uppdrag.

## Arbetsvägar

På `/arenden/<nummer>` finns en öppningsbar sidopanel **Agentstöd i detta ärende**.
Den visar bara det aktuella ärendets dialog, uppdrag, status och kostnadsunderlag.
En verifierad operatörssession krävs för att läsa dialogen och för alla nya
skrivvägar; de gamla v1-handläggarvyerna behåller sin tidigare avgränsning.

- **Skicka deluppdrag:** användaren skriver fritt. Agenten får läsa och beräkna.
  Kryssrutan för åtgärdsförslag kan därutöver tillåta förslag på registrering av
  ärendets löneunderlag. Dialogtext kan inte ge ett nytt mandat.
- **Låt agenten handlägga ärendet:** agenten kontrollerar underlaget och kan
  föreslå registrering. Efter verifierat beslut avslutar betrodd kod ärendet
  om dess sparade policy anger det. Modellen utför aldrig avslutet själv.
- **Komplettera och fortsätt:** ett väntande uppdrag får nytt samtalsunderlag
  och en länkad ny körning. Förbrukningen från tidigare segment ligger kvar.
  Faktiska ändringar av ärendets lön sparas separat med `amend_salary_case`,
  motivering och hashkontroll; de skapar ingen lönerapport eller premie.
- **Pausa agenten och ta över:** uppdraget återtas och varje nytt verktygsanrop
  stoppas. Ett redan pågående modellanrop avbryts inte inne hos leverantören.
  Redan skapade förslag ligger kvar för avstämning/avslag; återtagna uppdrag
  kan inte verkställas genom ett gammalt godkännandeförslag.

`CaseAnswer` skiljer svar från behov av uppgifter eller mänsklig bedömning.
Agenten måste ha läst ärendet i körningen. Ett fritt slutsvar utan en faktisk
registrering klarmarkerar aldrig ett överlämnat ärende. Ett deluppdrag avslutar
inte hela ärendet när dess förslag har genomförts.

## Granskningspolicy och automatisk slutbehandling

`src/agents/case_policy.yaml` är en granskad, versionsbunden källa.
Varje uppdrag binder hela policyn och dess SHA-256. Det finns ingen avstängning
av godkännanden i chatten, inget dolt formulärfält för policyval och ingen
global försvagning av åtkomstregistret.

Levererad konfiguration för `salary_report`:

- `review_required: true`: registreringsförslaget väntar på handläggaren.
- `auto_close: true`: ett överlämnat ärende avslutas efter verifierad åtgärd
  och beslut. Läs-/deluppdrag stänger inte ärendet.
- `schedule.enabled: false`: inget automatiskt dagligt urval är aktiverat.
- Förberett schema: 07.00 i `Europe/Stockholm`, inklusive sommar-/vintertid.
- Högst 20 körförsök och konservativa reservationer om sammanlagt 5 USD
  per verksamhetsdag och ärendetyp. Även manuellt beställda deluppdrag räknas.

`review_required: false` kan senare aktiveras genom granskad konfigurationsändring.
Den betrodda arbetaren använder då `complete_case_automatically` och kontrollerar
i samma transaktion som verkställigheten:

1. Att uppdraget gäller hela ärendet och fortfarande är aktivt.
2. Att samma policy fortfarande gäller och uttryckligen tillåter automatiken.
3. Att ärendet inte är stängt och dess aktuella underlag har samma kontrollsumma.
4. Att förslaget kommer från uppdragets handläggaragent/körning och exakt
   motsvarar person, arbetsgivare, månad, belopp, källreferens och övriga indata.
5. Att operationen är `register_salary_report`, med giltiga produktregler och
   nivån `APPROVAL`. Endast nya arbetsgivarrapporter ingår i den första
   automatiska vägen; rättelser och manuella underlag behöver handläggare.

Ändring, beslut och händelselogg är en transaktion. Maskinbeslutet märks
`case_automation`; ingen mänsklig granskare uppfinns. Agentens identitet och
policyversion finns i spåret. Agentrollen får inga nya affärs-DML-rättigheter.
Om kontrollen inte håller ligger förslaget kvar för mänsklig granskning.

Produktreglernas giltighetsdag kringgås aldrig. Före 2026-11-01 är
registreringsverktyget fortfarande dolt. `HUMAN_ONLY`, externa handlingar och
andra operationer får inget generellt undantag genom ärendepolicyn.

## Kö, schema och återhämtning

Webben sparar uppdraget före bakgrundskörningen. En omstart före anspråket
lämnar en köpost som den fristående arbetaren kan hämta. En unik beställningsnyckel
och ett atomiskt anspråk hindrar dubbelklick och dubbla arbetare från att köra
samma uppdrag. Ärende och arbetsstatus prövas även före varje verktygsanrop.

Inför drift behöver körmiljön ha grenens uppdaterade projektberoenden, inklusive
`tzdata` för verksamhetskalendern på Windows, samt de tre migrerade tabellerna.

```powershell
python scripts/agents/run_case_worker.py --db demo --once
python scripts/agents/run_case_worker.py --db demo --serve
```

`--serve` är en långlivad lokal process, inte en installerad Windows-tjänst.
För daglig obevakad drift behöver processen hållas igång eller `--once` anropas
av operatörens driftlösning. Den aktiverar inget schema när YAML anger avstängt.
När ett schema slås på väljs öppna ärenden av den konfigurerade typen som
saknar aktivt uppdrag, väntande förslag och tidigare daglig beställning.
Köposter och återstående dagsbudget begränsar urvalet redan före beställningen.
Ärenden med tidigare daglig beställning följs upp av handläggare, även om
underlaget senare ändras; fel leder inte till tysta dagliga omförsök.
Nya ärenden kan därför väljas utan att gamla uppföljningsfall blockerar kön.
Mer detaljerade urvalsregler
läggs till när de återkommande ärendena valts.

En körning som stod som `running` efter en processkrasch körs aldrig om
automatiskt. Operatören kontrollerar att föregående arbetare har stoppats,
markerar den för avstämning och kontrollerar förslag/händelser. Ett okänt
utfall förbrukar den reserverade körbudgeten och visas som **kostnad okänd**.
Ett återfunnet förslag kan efter avstämning granskas av en människa; det
automatavgörs inte som en bieffekt av återhämtningen. En redan genomförd
åtgärd spelas inte om vid avslut. Ärendeavslut och uppdragsavslut är atomiska.

## Data, migration och skydd

Tre nya tabeller, ägda av betrodd harness/backend:

| Tabell | Innehåll |
|---|---|
| `case_work` | Ärendereferens, arbetsform, instruktion, beställare, idempotensnyckel, status, revision, underlagshash, policybild, körreferens, resultat och förbrukning |
| `case_messages` | Ärende- och uppdragsreferens, avsändarroll, författare och meddelande |
| `case_work_days` | Låst reservationsbok per verksamhetsdag och ärendetyp; antal försök och reserverad kostnad |

Dialog och resultat kan innehålla personuppgifter och ligger i samma skyddade
databas som ärendet. De kopieras inte till det allmänna dokumentutkastlagret
eller den sanerade JSONL-journalen. Kontextbygget läser högst 30 meddelanden
från de senaste 30 dagarna och högst 20 000 tecken; detta är inte automatisk
gallring av tabellerna. Gallring av rå dialog/resultat behöver ingå i den
gemensamma försäkringsdatapolicyn före bredare drift. Den begränsningen visas
här uttryckligen; tidsfönstret ska inte beskrivas som att all rådata redan raderas.

Demo-/webbtestdatabasen får tabellerna enligt befintligt mönster. Lakebase
ändras aldrig från webbstarten. `scripts/migrations/migrate_case_work.py`
visar torrkörning som standard och kräver `--apply --backup <mapp>` för införande.
Endast de tre tabellerna skapas; befintliga radantal kontrolleras. Migrering
mot beståndet kräver separat samordning enligt AGENTS.md §4.5.

## Verifiering och kvarstående delar

Lokala förloppsprov omfattar sparad dialog, fria läsuppdrag, kund-/ärendegräns,
förslag och beslut, komplettering, övertagande, felaktigt underlag, policybyte,
idempotens, budget, schema, samtidighet, avbrott och autentisering/CSRF.
Isolerade Postgres-prov verifierar migration, två arbetare och hela kedjan
med mänskligt respektive automatiskt beslut. De ger inga nya agentroller.
Röktest med riktig modell finns i `scripts/diagnostics/smoke_test_case_work.py --run`;
det använder bara tillfällig lokal demodata och ett läsuppdrag.

**Kontrollerat 2026-10-31:** arbetsbranchen har synkats med `main` vid
`f66971f`, inklusive produktrapporten och antagandebiblioteket. Den sammanslagna
lokala sviten gav **1 386 godkända prov**, med 89 Postgres-prov bortvalda för
separat körning. Kodstil, testklassificering och genererade kataloger godkändes.
Den breda Postgres-körningen vid synkningen gav **89 godkända prov** i `svc_test`.
Efter den sista samtidighetsrättelsen kördes ärendets fem Postgres-prov om:
**5 godkända**, 161 andra prov bortvalda i det avgränsade urvalet. Inga prov
rapporterades som överhoppade i dessa körningar.
Ett läsuppdrag med riktig modell i lokal demo slutfördes med sparad dialog,
premieförhandsberäkning och utan skrivförslag (0,0574 USD för den godkända
körningen). Ingen framtida regelstatus användes i modellprovet. Ärendevyn har
kontrollerats visuellt i 1 440 och 390 pixlars bredd med syntetiskt underlag.
HTTP-prov verifierar inloggning, formulärskydd och vägen till mänskligt beslut.
Automatisk slutbehandling provas med testmodell och uttryckligt testregeldatum;
detta ersätter inte F5-5/6:s verifiering i beståndet från 2026-11-01.
Ett reproducerat samtidighetsfel har rättats: om en annan arbetare hinner avgöra
maskinbeslutet följs det sparade beslutet upp, utan falskt granskningsstopp eller
ny registrering. Det nya regressionstestet ingår i helkörningen ovan.

Detta är första byggda ärendeförmågan, inte hela den färdiga organisationen:

- Individbunden delegering från handläggare till aktuarie/compliance är ännu
  stängd enligt B-039:s datagräns. Agenten redovisar behovet till handläggaren.
  Det behövs ett mottagarmandat och relevanta domänverktyg innan den kan öppnas.
- Extern komplettering, meddelandeintag och kund-/arbetsgivarkontakt är inte
  byggda. Samtalskomplettering här är handläggarens underlag.
- Flera mänskliga roller/teammedlemskap, centralens generella teamsamtal och
  fler ärendetyper ingår i fortsättningen.
- Ingen schemaregel eller automatisk slutbehandling har aktiverats i den
  levererade standardpolicyn. Inget bestånd har migrerats eller ändrats.

**Förslag till senare beslutspost, utan nummer:** inför ärendebunden dialog
och två arbetsformer ovanpå gemensam harness; tillåt versionsbunden automatisk
slutbehandling för uttryckligen valda interna standardfall med giltiga regler,
exakt underlagsbindning, separat maskinidentitet och atomiskt spår. Behåll
mänsklig granskning och avstängt schema som standard. Inga generella
undantag för externa handlingar eller andra `HUMAN_ONLY`-operationer.
