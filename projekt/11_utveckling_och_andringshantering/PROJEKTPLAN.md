# Projekt 11 – Utveckling och ändringshantering

> Planeringsuppdrag från operatören 2026-11-07. Status **U1 byggd i lokal demo**. Projektet
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
visas i samma lista. Öppna respektive titel för att se underlag och ärende-ID.

Ärenden sparas i `data/handlaggare_demo.db` och finns kvar efter omstart. Logga in
igen efter omstart. `--reset-demo` raderar demofilen och därmed även ärendena.
Typ, titel och behov krävs vid registrering. Beställaren hämtas från sessionen
och är den enda som kan öppna ärendet. Samma registrering kan skickas om med
oförändrade uppgifter och ger då samma ID. Den enda statusen i U1 är **Nytt**.
Redigering, tilldelning, GitHub och överlämning från andra flöden hör till senare steg.

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
- [ ] **U2 – Board och GitHub i utvecklingsytan.** Gruppera kort efter bolagets
  arbetsstatus och visa länkade issues och PR-status med skrivskyddad adapter.
  Prova med lokala testdubblar före skarp läsanslutning.
- [ ] **U3 – Utvecklaragent och mänskligt övertagande.** Kör ett ärende i en
  isolerad kodmiljö med en första adapter till [Codex](https://learn.chatgpt.com/docs/non-interactive-mode)
  eller [Claude Code](https://code.claude.com/docs/en/headless). Använd ett gemensamt
  kontrakt för plan, diff, testbevis och utfall. Verifiera att agenten kan rätta ett
  testfel och att en människa kan ta över. Återanvänd principerna i harness och
  befintliga köer för identitet, budget, anspråk och körspår.
- [ ] **U4 – Överlämning från bolaget.** Anslut ett uttryckligt steg för en regel
  som kräver kod. Lägg till andra beställarvägar som Fråga bolaget när respektive
  ingång kan lämna behöriga uppdrag. Vid omförsök skapas samma ändringsärende.
- [ ] **U5 – Granskad merge och verifierat införande.** Bind godkännande till
  rätt commit och testbevis. Låt agenten genomföra tillåten merge, stäm av dess
  utfall och återför införande- och verifieringskvittot till ärendet och flödet.
- [ ] **U6 – Avgränsad autonomi.** Prova förhandsgodkända ändringstyper i
  sandlådan efter verifiering av U5. Testa nekat mandat, ändrad diff efter
  granskning, dubbla anrop och okänt resultat efter avbrott.

Bygg i ordning från U1. Projekt 4 äger regel och förväntad verksamhetseffekt,
berört domänteam äger fackgranskningen och projekt 10 ger åtkomst från centralen.
Utvecklingsmandatet finns i [agentens rollbeskrivning](../../02_system/agenter/utvecklaragent.md)
och [harness](../../02_system/harness.md). Följ [teststrategin](../../02_system/teststrategi.md)
för relevanta prov och integration.
