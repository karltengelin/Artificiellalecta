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
   i isolerade Postgres-scheman. Inför Lakebase-tabellerna efter separat
   operatörsgodkännande, backup och torrkörning enligt driftsättningen nedan.

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

Levererad konfiguration för `salary_report` (`case-work-v2`, B-043):

- `review_required: true`: registreringsförslaget väntar på handläggaren.
- `auto_close: true`: ett överlämnat ärende avslutas efter verifierad åtgärd
  och beslut. Läs-/deluppdrag stänger inte ärendet.
- `schedule.enabled: true` från 07.00 i `Europe/Stockholm`, inklusive
  sommar-/vintertid. Urvalet körs först när arbetaren startas (se nedan).
- `schedule.kinds: [new, correction]` och `schedule.sources: [employer]`:
  arbetsgivarens nya rapporter och rättelser väljs; manuella underlag
  överlämnas för hand i panelen.
- `schedule.max_cases: 5`: schemats andel per dag. Resten av dagens försök
  lämnas till handläggarens egna överlämningar och deluppdrag.
- Högst 20 körförsök och konservativa reservationer om sammanlagt 5 USD
  per verksamhetsdag och ärendetyp. Även manuellt beställda deluppdrag räknas.
  Varje försök reserverar agentens hela körtak (0,50 USD), så taket blir
  i praktiken 10 försök per dag.

Policyn byts bara när inga ärendeuppdrag är aktiva i måldatabasen: köade
och väntande uppdrag binder den tidigare policyns hash och stoppas annars
för handläggare. Beslutsunderlaget finns i
[SJALVSTANDIGA_ARENDEN_BESLUTSFORSLAG.md](../projekt/01_ärendehantering/SJALVSTANDIGA_ARENDEN_BESLUTSFORSLAG.md).

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
Driften enligt B-043 är `--once` från Windows Schemaläggaren vardagar 07.05,
med *kör så snart som möjligt efter missad start*, *starta inte en ny instans*
och utdata till `logs/case_worker.log`. Uppgiften skapas av operatören eller
med operatörens OK, efter Lakebase-verifieringen. Varje varv skriver en
tidsstämplad rad med antal uppdrag som väntar på godkännande, behöver
handläggare eller kräver avstämning; ett fel ger slutkod 1. `/arenden?status=uppfoljning`
(*Att följa upp*) listar samma öppna ärenden. Operatören kontrollerar dagligen
uppgiftens resultat, loggraden, `/godkannanden` och den listan.
Schemat väljer öppna ärenden av den konfigurerade typen och de valda
sorterna som saknar aktivt uppdrag, väntande förslag och tidigare daglig beställning.
Köposter och återstående dagsbudget begränsar urvalet redan före beställningen.
Ärenden med tidigare daglig beställning följs upp av handläggare, även om
underlaget senare ändras; fel leder inte till tysta dagliga omförsök.
Nya ärenden kan därför väljas utan att gamla uppföljningsfall blockerar kön.
Mer detaljerade urvalsregler
läggs till när de återkommande ärendena valts. Sedan B-043 filtrerar policyn
på sort och källa, och `max_cases` hindrar urvalet från att fylla hela dagsbudgeten.

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

### Infört i Lakebase 2026-10-31

Efter operatörens uttryckliga OK till merge och samordnad migration har koden
förts till `main` och `migrate_case_work.py --apply` körts efter granskad
torrkörning. Backup: `C:/Claude/Artificiellalecta/backups/20261031T144609Z`
(16 tabeller, 17 212 rader). Backupfilerna har kontrollerats mot manifestet.
`case_work`, `case_messages` och `case_work_days` skapades tomma med rätt
kolumner, främmande nycklar och index. Samtliga tidigare tabeller/radantal
är oförändrade, bland annat 501 försäkrade och 15 097 premietransaktioner.
Tabellerna ägs av `app_backend`; samtliga tre agentroller saknar direkta
tabellrättigheter. En omkörning ändrar ingenting.

Webbens appfabrik startar mot Lakebase med ansluten ärendeadapter. Arbetarens
`--db lakebase --once` behandlade 0 köposter; inga modelluppdrag skapades och
ingen bakgrundstjänst eller schemaregel har aktiverats. `tzdata` är installerat
i projektets gemensamma Pythonmiljö.
Efter driftanteckningarnas uppdatering gav det ändringsstyrda urvalet
`agents`, `orchestration`, `tooling` och `web` 696 godkända lokala prov;
70 Postgres-prov var bortvalda i den körningen. Programkoden är samma kodläge
som i den tidigare fullständiga lokala verifieringen och Postgres-verifieringen.

**Operatörsinloggning:** operatören valde själv den lokala lösenfrasen via
`scripts/web/set_operator_password.py` 2026-11-02. Inloggningskravet har inte
kringgåtts, och ingen lösenfras har valts åt operatören.

### Hela kedjan verifierad i Lakebase 2026-11-02 (F5-5/6)

Efter backup `C:/Claude/Artificiellalecta/backups/20261102T183441Z` (22 tabeller,
17 244 rader) och operatörens OK provades kedjan skarpt på den märkta
verifieringspersonen från S6 (Vera Verifiering, AL-000499), med
`claude-sonnet-5` och den riktiga rollen `agent_forsakring`:

- **F5-5 via UI:t:** operatören loggade in, CASE-000001 (rättelse av 2026-10
  till 40 000 kr) lämnades över till agenten, förslaget godkändes i
  `/godkannanden` och betrodd kod stängde ärendet som godkänt (0,0445 USD).
- **F5-6 med `scripts/diagnostics/smoke_test_case_flow.py --db lakebase --avslag`:**
  CASE-000002 godkändes och stängdes automatiskt (v3, 40 500 kr), CASE-000003
  avslogs utan registrering och stängdes av handläggaren som avslaget;
  28 av 28 kontroller (0,0958 USD). Samma skript gav 28 av 28 i demo och
  `svc_test` med begränsad testroll.

Tillbakaläst efteråt: bara ärendetabellerna, förslagen, händelseloggen och
Veras två nya löneunderlagsversioner tillkom; övriga tabeller, bland annat
501 försäkrade och 15 097 premietransaktioner, är oförändrade. Dagligt urval
och automatisk slutbehandling är fortfarande avstängda (F5-7).

### Policyändringen verifierad i demo och `svc_test` 2026-11-02 (F5-7 steg 2)

`case-work-v2` med urvalsfilter, schematak, statusrad och listfilter.
`scripts/diagnostics/smoke_test_case_schedule.py --run` kör arbetarens eget varv
med den levererade policyn och riktig modell. Anthropics konto saknade kredit
vid körningen, så rollen standard pekades på `openai:gpt-6.1-sol` (`--provider openai`).
Det misslyckade Anthropic-försöket gick till `needs_human` utan omförsök.

- **Urval:** en ny arbetsgivarrapport valdes, ett manuellt underlag för samma
  person och månad valdes inte. Förslaget godkändes och nästa varv stängde
  ärendet; ett nytt varv valde inget mer. En rättelse valdes, avslogs, visades
  i uppföljningen och stängdes av handläggaren.
- **Stoppvägar utan modellanrop:** schemataket släppte bara ett ärende och höll
  även efter återtagande; dagens försök stoppade handläggarens uppdrag; ett
  policybyte stoppade ett köat uppdrag.
- **Automatik med tillfällig policykopia:** en ny arbetsgivarrapport stängdes av
  `case_automation`; rättelsen stoppades för mänsklig granskning.
- **Avvikelsefall:** i ett tidigare försök gällde den nya rapporten en månad med
  redan fakturerad premie på annan lön. Agenten lade inget förslag och lämnade
  ärendet till handläggare. Röktestet använder därför en annan demoperson utan
  fakturerad premie för den automatiska vägen.

Resultat: demo 33 av 33 (0,040 USD), `svc_test` med begränsad testroll 33 av 33
(0,040 USD). Ändringsstyrt urval med `--postgres`: 1 672 godkända prov.

## Verifiering och kvarstående delar

Lokala förloppsprov omfattar sparad dialog, fria läsuppdrag, kund-/ärendegräns,
förslag och beslut, komplettering, övertagande, felaktigt underlag, policybyte,
idempotens, budget, schema, samtidighet, avbrott och autentisering/CSRF.
Isolerade Postgres-prov verifierar migration, två arbetare och hela kedjan
med mänskligt respektive automatiskt beslut. De ger inga nya agentroller.
Röktest med riktig modell finns i `scripts/diagnostics/smoke_test_case_work.py --run`;
det använder bara tillfällig lokal demodata och ett läsuppdrag. Hela kedjan med
förslag, beslut och avslut prövas med `scripts/diagnostics/smoke_test_case_flow.py`.

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
beståndsverifieringen med mänskligt beslut gjordes i F5-5/6 2026-11-02.
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
- Automatisk slutbehandling är inte aktiverad (B-043 val C). Det dagliga
  urvalet är påslaget i policyn men körs inte i Lakebase förrän verifieringen
  där är gjord och uppgiften i Schemaläggaren skapats.

**Förslag till senare beslutspost, utan nummer:** (driftvalen är beslutade i B-043)
inför ärendebunden dialog
och två arbetsformer ovanpå gemensam harness; tillåt versionsbunden automatisk
slutbehandling för uttryckligen valda interna standardfall med giltiga regler,
exakt underlagsbindning, separat maskinidentitet och atomiskt spår. Behåll
mänsklig granskning och avstängt schema som standard. Inga generella
undantag för externa handlingar eller andra `HUMAN_ONLY`-operationer.
