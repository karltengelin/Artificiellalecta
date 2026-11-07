# Projekt 11 – Utveckling och ändringshantering

> Planeringsuppdrag från operatören 2026-11-07. Status **U1–U5 byggda i lokal demo**. Projektet
> omfattar utvecklaragenten, ändringsflödet, utvecklingsytan och GitHub-kopplingen.

## Syfte och första leverans

En människa eller utvecklaragent ska kunna ta ett ändringsärende från beskrivet
behov till verifierat införande. Operatören ska kunna skapa egna ärenden i
bolagets webb och se vad som ligger i kö, vem som arbetar, vad som blockerar
och vilken kod som väntar på godkännande. Arbetsgången ska fungera för både
felrättningar och antagna regler som kräver ny logik.

Första byggleveransen är ett lokalt, varaktigt ändringsärende med autentiserad
manuell registrering, en läsbar utvecklingsvy och en detaljsida i befintlig webb.
Det är grunden för senare tilldelning, agentkörning och GitHub-status på samma kort.

## Prova U1 i demo

Starta den befintliga webben från arbetsytan med `python scripts/web/start_ui.py --db demo`.
Logga in med din [lokala operatörsinloggning](../../02_system/operator_inloggning.md)
och välj **Utveckling** från **Centralen**. Registrera till exempel ett fel vid export
och ett fiktivt regelärende med beslut, version och giltighetsdatum. Båda ärendena
visas under **Nytt**. Öppna respektive titel för att se underlag och ärende-ID.

Ärenden sparas i `data/handlaggare_demo.db` och finns kvar efter omstart. Logga in
igen efter omstart. `--reset-demo` raderar demofilen och därmed även ärendena.
Typ, titel och behov krävs vid registrering. Beställaren hämtas från sessionen
och är den enda som kan öppna ärendet. Samma registrering kan skickas om med
oförändrade uppgifter och ger då samma ID.

## Prova U2 i demo

Öppna ett eget ärende och välj **Pågår** under **Bolagets ärendestatus**.
Klicka på **Flytta ärendet**. Kortet visas nu i motsvarande kolumn på boarden.
Under **Teknisk status från GitHub** kan du spara
en direktlänk till ett issue eller en pull request i det konfigurerade repot.
Töm fältet och spara för att ta bort länken. Ärendehistoriken visar vem som
flyttade ärendet eller ändrade länken, tidpunkten och värdena före och efter.

Läsning av GitHub-status aktiveras med `DEVELOPMENT_GITHUB_TOKEN` i lokal
`.env`. Operatören skapar en token begränsad till valt repo med läsrätt till
*Issues* och *Pull requests*. Ange vid behov repot som `ägare/repo` i
`DEVELOPMENT_GITHUB_REPOSITORY` och starta om webben. Standard är
`karltengelin/Artificiellalecta`. Länkar kan sparas även utan token. Servern
skickar endast repo, typ och nummer i uppslagets sökväg.
[GitHubs issue-API](https://docs.github.com/en/rest/issues/issues#get-an-issue) ·
[GitHubs PR-API](https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request)

Detaljsidan hämtar GitHub-status när den öppnas. Boarden visar senast hämtad
status och tidpunkt. Efter en minut markeras uppgiften som föråldrad tills
detaljsidan hämtat en ny. Vid fel visas ett besked, och en tidigare status
visas som föråldrad. GitHub-statusen lagras i serverns minne och hämtas på
nytt efter omstart. Länk, bolagets status och historik är varaktiga. I äldre
demofiler skapar webbstarten den lokala tabellen `change_request_events`
för flyttar och länkbyten. Tidigare ärenden ligger kvar i `change_requests`.

## Prova U3 i demo

Kör `python scripts/demo/run_development_case.py --operator-id karl` från
arbetskopian. Använd ditt lokala operatörs-ID om det är ett annat än `karl`.
Skriptet registrerar ett fiktivt offertfel i den lokala demofilen och ger
utvecklaragentens körning mandat till just det ärendet. Skriptet provar två
fiktiva kontrollfall. Den första patchen ger ett testfel och teståterkopplingen
leder till en korrigering. Öppna **Utveckling** i den lokala demowebben och
välj ärendet med det ID som skriptet skriver ut.

På kortet ser du agenten som ansvarig under **Väntar på granskning**. Detaljen
visar anspråkets körnings-ID och referenser till diff och testbevis. Välj
**Ta över ärendet** för att bli ansvarig. Historiken behåller agentens
anspråk och underlag. Vid övertagande mitt under arbetet kan en redan startad
kodarförfrågan löpa till sin tidsgräns. Dess svar kan då inte ändra ärendet.
Som människa kan du ta ett nytt ärende genom att flytta det till **Pågår**.
Formuläret **Lämna för granskning** kräver referenser till kodändringen och
testbeviset. Äldre U2-ärenden kan visas med tidigare status utan U3-underlag.

### Körkontrakt och lagring

- Den betrodda startaren utfärdar en körningsnyckel för utvecklaragenten,
  en beställare och en mängd uttryckligen tillåtna ärende-ID:n.
  `ChangeRequests.list_new`, `claim` och `handoff` använder samma mandat.
  Anspråk och status sparas i en demotransaktion. Varje körningsnyckel
  kan ta ett ärende en gång. Operatörens övertagande binder samma nyckel.
- Kodaren får fiktivt underlag och källsnapshot på en egen lokal Git-branch.
  Körningen har högst två kodförsök och 120 sekunder. Kodaren lämnar en plan
  och föreslår en avgränsad textändring. Betrodd kod tillämpar den bara i
  tillåten fil och kör fasta tester. Demon testar SQL-beräkningen i en
  separat minnesdatabas med begränsad frågekörning.
- `logs/development_runs/<körnings-id>/result.json` innehåller bascommit,
  testad commit, plan, diff, testbevis och utfall. Den närliggande JSONL-filen är harnessens
  körjournal. Referenserna på ärendet binder körnings-ID, bascommit, testad commit, diff och
  det godkända testutfallet med SHA-256. Den temporära kodkopian tas bort
  efter försöket. Betrodd kod sparar underlaget före överlämningen och
  kontrollerar ansvaret igen i överlämningstransaktionen.
- Demotabellerna `change_requests` och `change_request_events` används som
  i U2. Nya händelsetyper i den befintliga loggen registrerar ansvar,
  övertagande och granskningsreferenser. Boarden och detaljen läser samma
  projektion.

Demokommandot använder en skriptad kodare. Provet för `CodexCli` ersätter
CLI-processen med en lokal testdubbel som använder samma uppdrags- och
svarskontrakt. Adaptern följer OpenAI Docs för schemavaliderad utdata från
`codex exec` och använder skrivskyddat läge. En körning med riktig modell
kräver operatörens godkännande och en separat miljö med endast syntetiskt
underlag och egna behörigheter. [OpenAI Docs](https://learn.chatgpt.com/docs/non-interactive-mode)

## Prova U4 i demo

Starta webben med `python scripts/web/start_ui.py --db demo --rule-change-flows`.
Startvalet kräver en [lokal operatörsinloggning](../../02_system/operator_inloggning.md)
och ansluter teamens konfigurerade AI-klient med simulerade databasroller.
Logga in och öppna **Försäkringsteamets arbetsyta → Flöden**. Välj
**Starta kodändringsflöde** med det bevakningsunderlag som ska tolkas.
För en ändring av en befintlig parameter använder du **Starta flöde**
och den vanliga parametervägen.

Kör compliance-tolkningen. Granska källan och tolkningen under **Anta regeln
för utveckling**. Välj berörd regel och ange ny regelversion, giltighetsdag,
berört system, varför ny kod behövs och vilken effekt som ska kunna prövas.
Grinden binder tolkningen och dess verifierade källreferens. Ett förslag
som innehåller en parameterändring hanteras i parameterflödet.

Välj **Lämna till utveckling**. Flödet visar kvittot med ärendets ID och en
länk till detaljen. Ärendet ligger under **Nytt** på utvecklingsboarden
för samma operatör och länkar tillbaka till överlämningssteget. En
utvecklarkörning kan ta ärendet med U3:s uttryckliga ärendemandat.

Betrodd kod skickar `ChangeRequestOrder` med ett stabilt ursprung
(`rule_change_code` och flödes-ID/stegnyckel) till `ChangeRequests.submit_order`.
Ursprunget och ärendet sparas i samma demotransaktion i U1–U3:s befintliga
tabeller. Om kvittot uteblir efter att ärendet sparats kan operatören välja
**Kör om steget** vid avstämningen. Samma underlag ger samma ärende och bevarar
dess ansvar och status. Andra behöriga ingångar kan använda samma kontrakt
med en egen kanal och referens efter sin egen kontroll av mandat och underlag.

Webbproven använder en fiktiv källa och en testmodell och provar hela vägen
från inloggning till agentens anspråk. De provar också omstart efter att
ärendet sparats, fel beställare, ändrat eller saknat underlag och den befintliga
parametervägen. Kör dem via `python scripts/testing/run_tests.py --suite web --run`.

## Prova U5 i demo

1. Kör `python scripts/demo/run_development_case.py --operator-id karl --prepare-release`
   från arbetskopian. Byt operatörs-ID om ditt lokala konto har ett annat namn.
   Skriptet sparar den testade committen och förbereder en pull request i GitHub-dubbeln.
2. Starta demowebben med `python scripts/web/start_ui.py --db demo` och logga in.
   Öppna det utskrivna ärendet via **Utveckling**. Läs diffen och provresultaten under
   **Granskad merge och införande i demo**. Välj **Godkänn kodversion och testbevis för merge**.
3. Kör `python scripts/demo/run_development_case.py --operator-id karl --request-merge ÄRENDE-ID`.
   Startaren använder mandatet från den aktiva utvecklarkörningen för ärendet.
   Operatören kan också begära merge på ärendet, till exempel efter övertagande.
4. När ärendet är **Mergat**, välj **Inför den mergade versionen i demo**.
   När det är **Infört**, välj **Verifiera införandet i målmiljön**.
   Ett godkänt hälsoprov med rätt observerad version ger **Verifierat**.
   Ett länkat U4-flöde visar status och kvitton från samma ärende.

Godkännandet binds till granskningsinlämningen, pull request, repo, målbranch,
bascommit, granskad commit, diff och provbevis. Betrodd kod prövar samma underlag
och det obligatoriska kodprovet vid merge. Kodaren har bara källsnapshot och
testdata i sin arbetsyta. Merge- och införandevägen finns hos den betrodda startaren
och demowebben. GitHubs skrivskyddade statusläsning i U2 är en separat väg.

Beslut, försök och kvitton sparas i demotabellen `change_release_events`, som
skapas vid start även för äldre demofiler. De två testdubblarnas kvitton och
observerade versioner finns i `data/handlaggare_demo.delivery.db`. Om ett
svar uteblir markeras ärendet för avstämning. Betrodd kod söker efter kvittot
med samma försöksnyckel före ett nytt anrop. Om källan bekräftar att ingen
merge utförts och underlaget har ändrats krävs ett nytt beslut.
`--reset-demo` återställer båda demofilerna.

U5-proven täcker ändrad kod och ändrade testbevis, nekade mandat, samtidiga
anrop, avbrott före eller efter effekt samt kontroll av fel målversion.
Ett prov går hela vägen från en fiktiv U4-regel till verifierat införande.
Verkliga skrivanslutningar, mergepolicy och autonomt godkännande kräver
separata beslut.

## En ingång till ändringsarbetet från flera håll

Ett **ändringsärende** är arbetsenheten oavsett var behovet upptäcks.

| Källa | Hur ärendet börjar |
|---|---|
| Operatören eller en behörig utvecklare | Skapar ett ärende i utvecklingsytan, exempelvis om ett fel, ett önskat arbetssätt eller en teknisk förbättring. |
| Ett team, ett driftflöde eller Fråga bolaget | Lämnar ett ändringsförslag med underlag. Vid senare anslutning prövar betrodd kod om avsändaren får skapa eller lämna ärendet vidare. |
| Regeländringsflödet | Skapar ett ärende när en antagen regel kräver ny kod. Länkar beslut, regelversion, giltighet och förväntad effekt. Ändringar av befintliga parametrar går via den beslutade parametervägen. |

Minsta underlag är titel, behov och motiv, beställare, berört system och hur det
förväntade resultatet ska kunna prövas. Källreferenser, beslutsreferens och datum
följer med när de är relevanta. Ärendet får ett stabilt ID. Ett ofullständigt
ärende kan sparas som nytt och kompletteras före tilldelning.

## Så går ett ändringsärende genom bolaget

1. **Tilldela arbetet.** En människa eller en godkänd agentkörning tar ärendet.
   Ägarskap och försök registreras. Samtidiga anspråk på samma ärende avgörs
   atomiskt. Ett omförsök av samma flödessteg återanvänder det skapade ärendet.
2. **Undersök och planera.** Utvecklaragenten söker från beslut, regel eller
   felbeskrivning till berörd kod och dess beroenden. Den dokumenterar berörda
   beräkningar, kontrakt, datamodeller, tester och dokument, samt risker,
   motåtgärder och möjlig återställning. Vid oklar förväntad effekt begär den
   ett avgränsat besked från operatören eller en domänspecialist. Beskedet sparas
   med ärendet. Compliance och aktuarie kan bidra med oberoende sakunderlag.
3. **Ändra, testa och rätta.** Kodaren arbetar från en dokumenterad bascommit i
   isolerad arbetsyta med egen branch och testdata. Agenten får använda en
   kodloop som läser kod, gör ändringar över berörda filer, kör testverktyget,
   analyserar fel och rättar inom fastställda tids- och försöksgränser.
   Avvikelser från uppdragets mandat eller oklarheter i domänkraven går tillbaka
   för besked. För ny produktlogik prövas både avsedd effekt och äldre fall.
4. **Lämna granskningsunderlag.** Agenten kan committa, begära push till sin
   arbetsbranch och öppna en pull request genom godkända Git-verktyg. Ärendet
   knyts till exakt commit, testresultat, diff, riskbedömning och införandeplan.
5. **Godkänn och integrera.** Utsedd granskare prövar den exakta versionen som
   standard. Agenten kan utföra mergen efter att gällande beslut och kontroller
   har verifierats. En ändring av det granskade innehållet kräver ny prövning.
   För `main` gäller operatörens uttryckliga godkännande enligt AGENTS.md §4.6.
6. **Inför och verifiera.** Spara vilken kodversion som faktiskt togs i bruk,
   miljö, tidpunkt, resultatkontroll och eventuell återställning. Ett lyckat
   mergekvitto markerar *mergat*. *Verifierat* kräver bevis från målmiljön.

Boarden ska kunna visa **Nytt → Pågår → Väntar på granskning → Mergat → Infört →
Verifierat**, med tydlig status för avbrott och väntan på besked. Vid okänt
utfall efter exempelvis push, merge eller införande stäms GitHub eller målmiljön
av innan en åtgärd görs igen. Spara identitet, tid, övergång och relevanta
referenser per händelse så att operatören kan följa hela kedjan.

## Mandat, godkännande och avgränsningar

- **Granskat läge är standard.** Operatören eller utsedd granskare godkänner
  kodversionen före införande. Om en merge aktiverar koden ligger grinden före
  mergen. Källbeslut, godkänd kodversion och verifierat införande är separata
  spår. Ändringar av styrpolicy och produktionsanslutningar kräver egna mandat.
- **Autonomt läge är ett senare, uttryckligt val.** Pröva först utan manuellt
  godkännande per ändring i en isolerad testmiljö för i förväg godkända
  ändringstyper. Betrodd policy prövar den faktiska diffen, miljön och
  obligatoriska testresultat. Kodaren kan begära åtgärden, men styr inte policyn
  som avgör om den tillåts. Ny pensionslogik omfattas av oberoende godkännande
  före införande. En ändring av repots mergepolicy är ett separat beslut.
- **Isolerat kodarbete.** Arbetsytan får relevant källkod och testdata med
  avgränsad Git-åtkomst. Produktionsdata, produktionsbehörigheter och nycklar
  för merge eller release hör hemma utanför kodmiljön. Betrodd kod verkställer
  de Git- och releaseåtgärder agenten har mandat att begära.

Detta konkretiserar DORA-inriktningen för åtskilda roller, kontrollerad testning
och återställning. Se [artikel 17 i den delegerade förordningen](https://eur-lex.europa.eu/eli/reg_del/2024/1774/oj/eng#art_17)
och [bolagets DORA-underlag](../../04_regulatoriskt/02_tvärgående/dora.md).

## Utvecklingsyta och GitHub

Bygg en Azure DevOps-liknande board i befintlig webb och länka den från
operatörscentralen. Operatören ska kunna skapa ett ärende där och öppna dess
detalj för historik, beslutsunderlag och länkar. Börja med lista och detalj,
gruppera senare efter arbetsstatus. Bolagets ändringsärende äger
verksamhetsstatus och införandebevis. GitHub äger sina issues, pull requests,
commits och tekniska kontroller. Koppla med stabila referenser och visa källan
till status. Personuppgifter och skyddade underlag stannar i behörig bolagsyta.

Anslut först [GitHub Issues](https://docs.github.com/en/rest/issues/issues#list-repository-issues)
och relevanta PR-uppgifter via en skrivskyddad serveradapter för valt repo.
Visa fel eller föråldrad GitHub-information tydligt. Lägg till
[Projects-fält](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-api-to-manage-projects)
om boardens egna fält behövs. Använd GitHub för kodgranskning och teststatus.
Skrivande GitHub-koppling för att skapa länkade issues eller begära merge är
ett senare paket med egen behörighetsprövning. Operatören sätter upp eventuella
externa integrationer och behörigheter enligt AGENTS.md.

## Backlog och byggordning

- [x] **U1 – Skapa och följ egna ändringsärenden.** Lokalt ärendekontrakt,
  lagring och autentiserad manuell registrering med lista och detalj i demo.
  Webbproven täcker vanligt fel och regelärende i samma kontrakt, validering,
  nekad åtkomst, omförsök och återöppning efter omstart.
- [x] **U2 – Board och GitHub i utvecklingsytan.** Board med tre statuskolumner,
  manuella flyttar och skrivskyddad status för länkat issue eller pull request.
  Verifierat i lokal demo med testdubblar. Skarp läsanslutning provas efter
  operatörens konfiguration.
- [x] **U3 – Utvecklaragent och mänskligt övertagande.** Verifierat i lokal demo
  med en första Codex CLI-adapter och testdubbel. Mandatstyrt urval, samtidiga
  anspråk, rättning efter testfel, granskningsbevis på boarden och mänskligt
  övertagande är provade. Modellkörning med externa behörigheter återstår.
- [x] **U4 – Första överlämningen från bolaget.** En antagen regel som kräver ny
  kod kan lämnas till utveckling som ett ordinarie ärende i demo. Omförsök
  återfinner samma ärende. Andra ingångar, exempelvis Fråga bolaget, ansluts
  när de kan lämna behöriga beställningar.
- [x] **U5 – Granskad merge och verifierat införande.** Lokalt provad kedja
  med mänskligt beslut, mandatstyrd mergebegäran och skilda kvitton för merge,
  införande och verifiering. Bevisen visas på ärendet och från länkat U4-flöde.
- [ ] **U6 – Avgränsad autonomi.** Prova förhandsgodkända ändringstyper i
  sandlådan efter verifiering av U5. Testa nekat mandat, ändrad diff efter
  granskning, dubbla anrop och okänt resultat efter avbrott.

Bygg i ordning från U1. Projekt 4 äger regel och förväntad verksamhetseffekt,
berört domänteam äger fackgranskningen och projekt 10 ger åtkomst från centralen.
Utvecklingsmandatet finns i [agentens rollbeskrivning](../../02_system/agenter/utvecklaragent.md)
och [harness](../../02_system/harness.md). Följ [teststrategin](../../02_system/teststrategi.md)
för relevanta prov och integration.
