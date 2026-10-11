# Arbetsutkast – produktregler och regelverkstolkningar

> **Status:** Förslag för granskning, inte ett nytt beslut eller antagna villkor.
> **Datum:** 2026-10-11 | **Ägare:** Operatören
> **Grund:** B-005, B-010, B-012, B-015, B-021, B-022 och B-024.

## 1. Syfte och placering

Produktreglerna ska beskriva vad försäkringssystemet ska göra och varför. De ska
kunna granskas av en människa och användas av utvecklare, handläggare och agenter.
De skrivs som Markdown. Reglerna är en precisering av bolagets tillämpning i B-010:s
fyrlagermodell; de inför inget nytt rättsligt lager.

| Innehåll | Placering | Ansvar i dokumentkedjan |
|---|---|---|
| Källregister och externa bestämmelser | `04_regulatoriskt/` | Identifiera källa, version och exakt bestämmelse |
| Tolkningar | `04_regulatoriskt/tolkningar/` | Beskriva tillämplighet, resonemang och osäkerheter, lager 2 |
| Produktregler | `01_domän/produktregler/` | Precisa operativa produktkrav, bolagets tillämpning i lager 3 |
| Försäkringsvillkor | `01_domän/försäkringsvillkor.md` | Kundens villkor, lager 3 |
| Interna policies och processer | `05_styrdokument/` | Styrning, ansvar och kontroller, lager 3 |
| Kod och kontroller | `src/` och `tests/` | Implementera och verifiera, lager 4 |
| Planering och öppna frågor | `projekt/04_produktregelverk/` | Samordna arbetet |

Befintliga domändokument ligger kvar enligt B-024. Projektmappen innehåller
arbetsplanen och hänvisningar, inte en andra kopia av produktreglerna.
Mappplaceringen för tolkningar och produktregler är ett arbetsförslag.

## 2. Skriv en regel i taget

Använd stabila ID:n: `K-...` för källor, `T-ITP1-...` för tolkningar och
`PR-ITP1-...` för produktregler. Ändra inte ett ID när rubriken ändras.
En regel kan ha flera källor; en tolkning kan stödja flera regler.

Varje produktregel ska innehålla:

1. ID, version, ägare, granskningsstatus och separat implementationsstatus.
2. Ursprung: externt krav, bolagsval eller uttrycklig simuleringsförenkling.
3. Källa med bestämmelse/avsnitt och eventuell tolkning med länk.
4. Giltighet i sak, berörda produkter/försäkringar och eventuell övergångsregel.
5. Förutsättningar, indata, villkor, utfall och undantag.
6. Räkneexempel eller andra acceptansfall, inklusive gränsfall.
7. Koppling till villkor, implementation och verifiering.
8. Öppna frågor och versionshistorik.

Skriv själva regeln så att utfallet går att avgöra för givna indata. Undvik att
blanda till exempel premiebelopp, åldersbehörighet och löneklassificering i en
enda regel. Gemensamma förutsättningar får hänvisas till, men inte döljas.

## 3. Källor och tolkningar

[Källregistret](../../04_regulatoriskt/kallregister.md) skiljer normgivande
texter från officiella sammanställningar. En verifierad informationssida är
användbar evidens men ersätter inte ett avtal med identifierad utgåva och punkt.
Författningsversioner måste kontrolleras för den period som regeln gäller.
En konsoliderad text kan innehålla både gällande och framtida bestämmelser.

[Tolkningsmallen](../../04_regulatoriskt/tolkningar/MALL.md) används när
tillämplighet, flera källor eller ett operativt vägval behöver förklaras.
Redovisa alternativ, vald slutsats och det som ännu saknar stöd.
Bolagets förenklingar är inte slutsatser om vad externa regler medger.

## 4. Giltighet och godkännande

Skilj mellan extern ikraftträdandetid, regelns föreslagna giltighet i simuleringen,
godkännandedatum och teknisk driftsättning. Ett dokumentdatum är inte automatiskt
ett giltighetsdatum. Dokumentera om ändringen gäller nya avtal, befintliga avtal,
framtida premier eller även historiska beräkningar.

Ett utkast kan beskriva redan implementerat beteende utan att vara godkänt.
Använd granskningsstatus `utkast`, `godkänd` eller `ersatt` och implementationsstatus
`saknas`, `delvis` eller `implementerad`. Anteckna verifiering separat med datum.
Godkännande av dokumentet innebär inte att en regel är rättsligt verifierad,
driftsatt eller tillämplig på alla försäkringar.

När nya beslut behövs formuleras beslutsförslag för operatören. Nya poster i
`BESLUTSLOGG.md` skrivs inte utan godkännande. Produktregeländringar följer det
befintliga [regelförändringsflödet](../../02_system/Agentsystem/regelförändringsflöde.md).
Detta arbete bygger inte om agenternas gränssnitt.

## 5. Första provet: ordinarie premietrappa

- Källa: K-ITP1-2026 och K-IBB-2026 i källregistret.
- [Tolkning T-ITP1-001](../../04_regulatoriskt/tolkningar/T-ITP1-001-premietrappa.md).
- [Produktregel PR-ITP1-001](../../01_domän/produktregler/PR-ITP1-001-premietrappa.md).
- Befintliga villkor §3.2, premiemotor och tester är kedjans övriga delar.

Provet dokumenterar befintligt beteende. Det ändrar inga premier, villkor eller
databastabeller. IBB är en årsparameter; satser och gränser i antal IBB är
regelparametrar. En framtida ändring av satser behöver därför egen giltighet
och regelversion även om IBB redan är lagrat per år.

## 6. Öppna frågor i föreslagen arbetsordning

| ID | Fråga | Nästa utredningssteg |
|---|---|---|
| F-001 | Vilken avtalsutgåva och punkt styr premietrappan? | Hämta ITP-planens avtalsunderlag och fastställ giltighet; webbsammanställningar är kontrollerade men avtalspunkt återstår |
| F-002 | Ska delbeloppen avrundas var för sig? | Kontrollera administratörens beräkningsregler; befintlig kod gör detta, källstödet är ännu inte verifierat |
| F-003 | Uttagsåldrar och bolagsvillkor | Avtalspunkt 7.5 verifierad: 55 år/ordinarie 66-årsmånad, inget stöd för generell maxålder 70. Granska T-ITP1-002 och PR-ITP1-002–005; detaljvillkor, partiella uttag och aktuariell grund återstår |
| F-004 | Vilken garanti erbjuder vår traditionella försäkring? | B-027 beslutar hela mottagna nettopremien och 0 % nettoränta, utan automatisk garantiförstärkning. T-ITP1-004, PR-ITP1-008/009 och aktuariell grund finns som utkast; tariffkalibrering, riskgranskning, finansiering och införande återstår |
| F-005 | Vad händer med kapitalet vid dödsfall utan återbetalningsskydd? | Utred dödsfall, arvsvinster och aktuariell modell inom ålderspensionsprodukten |
| F-006 | Hur fördelas en premie när en person har flera försäkringar? | Precisera beräknings- och fördelningsnivå enligt B-022 så att samma löneunderlag inte används dubbelt |
| F-007 | Vilka regler gäller historiskt? | Kontrollera avtals- och parameterversioner för premiehistoriken 2023–2026 innan dagens regler ges retroaktiv giltighet |
| F-008 | Hur hanteras kompletterande premier och valcentralsavgift? | Fastställ separata produktregler eller uttryckliga förenklingar; ordinarie bruttopremie ska skiljas från tillfört kapital |

Kompletterande premier kan finnas i verkligheten men ingår inte i provregelns
beräkningsformel.

De befintliga uttagsuppgifterna flaggas här för utredning. Detta utkast ändrar
inte den beslutade villkorsversionen utan ett separat granskat ändringsförslag.

## 7. Föreslagen fortsättning

Uttagsutkast finns nu i [gemensamma förutsättningar](../../01_domän/produktregler/UTTAG_GEMENSAMT.md)
med sex separata regler och [T-ITP1-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
Tidsbegränsad utbetalning och förlängning har kompletterats med
[T-ITP1-003](../../04_regulatoriskt/tolkningar/T-ITP1-003-tidsbegransad-utbetalning.md)
och PR-ITP1-006/007.
Nästa steg för uttagsområdet är granskning av bolagsval och
[villkorsändring](VILLKORSANDRING_UTTAG.md), därefter partiella uttag,
slutavräkning, aktuariell grund och modell för uttagsplaner.

Garantiområdet har ett [besluts- och villkorsförslag](GARANTI_BESLUTSFORSLAG.md)
och [modellutkast till aktuariell grund](../../01_domän/aktuariell_grund.md).
Produktinriktningen är beslutad i B-027. Nästa steg där är tariffkalibrering,
riskgranskning och underskottsfinansiering.
F-004 är därför delvis utredd, inte stängd. F-005 om dödsfall/arvsvinster
återstår och är ett beroende för en ekonomiskt sammanhängande modell.

Granska först dokumentkedjan och avrundningsvalet. Skriv därefter separata regler
för premieåldrar, pensionsmedförande lön och anställningsperiod. Utred sedan
uttag och garanti med exakta källhänvisningar. Bygg ut regulatoriska dokument
utifrån de frågor som faktiskt påverkar produkten, med tillämplighetsbedömning
för skatt, försäkringsavtal, information, produktstyrning och hållbarhet.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första arbetsförslag och provregel |
