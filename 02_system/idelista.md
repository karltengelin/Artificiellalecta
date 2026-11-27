# Idélista – eventuellt att göra

Idéer att ta upp när de blir aktuella. Prioritet och utformning avgörs då.

## Chattrum för agenternas samarbete

När agenter behöver samarbeta kan operatören öppna en chattvy för ärendet eller
uppdraget. Där går det att följa vem som skickade en fråga eller lämnade över en
uppgift till vem, vilket underlag som skickades med och vilket svar som kom
tillbaka. Historiken går att öppna även efter att arbetet är klart.

## Visa när en agent arbetar

När någon skickar ett uppdrag till en agent kan gränssnittet visa en liten
aktivitetsikon medan arbetet pågår. I handläggargränssnittet kan den exempelvis
sitta vid agentknappen eller chatten i ärendet. En kort statustext kan visa det
aktuella steget, till exempel ”Hämtar premiehistorik” eller ”Väntar på svar från
aktuariens agent”. Samma idé kan användas i andra gränssnitt där agenter arbetar.
Ikon och placering bestäms när respektive gränssnitt utformas.

## Erfarenhetsminne för agenter och agentteam

När en agent stöter på ett problem skriver den en kort anteckning i sitt eller
teamets beständiga minne. Anteckningen beskriver problemet, vad som prövades,
hur det löstes och hur utfallet kontrollerades. Om problemet fortfarande är öppet
framgår nästa steg. Koppla anteckningen till [körjournalen](harness.md) så att
utfallet går att följa upp. Samla återkommande fall under samma lärdom.

Vid ett liknande uppdrag kan agenten hämta relevanta lärdomar för sitt mandat.
Spara återanvändbara mönster utan kunduppgifter. Förslag från agenten kan granskas
och markeras som verifierade innan de används som rekommenderat arbetssätt.
Gällande regler, behörigheter och godkännanden styr alltid själva åtgärden.

## Separata kodrepon och gemensamma utvecklingsregler

I dag delar produktmotor, tjänstelager, intern webb och UX-material ett Git-repo.
Delprojekten har egna projektplaner. Kod och tester ligger i gemensamma träd.
[Nuvarande projektstruktur](../MASTER_CONTEXT.md)

### Repo per område

Utred vilka delar som vinner på eget ägarskap och egen utgivning. Pröva gränsen
mellan produktmotor och webb eller en framtida kundportal. Kartlägg först dagens
importer och gemensamma datamodeller. Om delar flyttas isär behöver de versionssatta
kontrakt för sina anrop och en plan för hur ändringar samordnas över repogränserna.

### Egna tester och agentinstruktioner

Ge varje repo egna lokala tester och CI-körningar samt en `AGENTS.md` som beskriver
områdets ansvar, hur agenter bygger och testar koden och hur ändringar granskas.
Behåll gemensamma kontrakts- och integrationstester för flöden som går genom flera
repon. Utgå från dagens testgrupper och deras dokumenterade beroenden.
[Teststrategin](teststrategi.md)

### Centrala arkitekturbeslut och kodstandarder

Versionssätt bolagets gemensamma arkitekturbeslut, kodstandarder och testkrav i en
central källa. Låt varje repo ange vilken version det följer och länka till den
från sin `AGENTS.md`. Pröva att automatiskt föreslå uppdateringar via pull requests
och använda gemensamma CI-kontroller där reglerna går att testa. Ange vem som äger
reglerna och hur lokala undantag dokumenteras och godkänns.

## Certa som möjligt namn för bolaget och projektet

Vilande namnförslag. Om operatören aktiverar namnbytet används **Certa** för
både bolaget och projektet, med **Tjänstepension** som underrad i logotypen.

Använd bilden nedan som förlaga för logotypfilerna vid ett namnbyte. Den valda
versionen vidareutvecklar Geminis idé med ett öppet C. Diagonalen växer fram ur
C:ets nedre kurva och en andra indigoton markerar svängen. Ordmärket sätts i
DM Sans Bold (700). [Digital klarhet](../06_design/designsprak.md)

- **Ljus grundversion (vänster).** För webb och dokument. Indigo (`#6951CF`)
  och mörkt ordmärke (`#252440`) på den ljusa bakgrunden (`#EEEDF6`).
- **Mörk version (höger).** För exempelvis titelbilder. Ljus indigo (`#D2C5FF`)
  och ljust ordmärke (`#F4F2FF`) på mörk indigo (`#252440`).

![Den valda Certa-logotypen i ljus grundversion och mörk presentationsversion](../06_design/koncept/certa-digital-klarhet.png)
