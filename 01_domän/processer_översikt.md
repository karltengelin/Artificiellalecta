# Processöversikt – löpande verksamhet och månadssimulering

> **Datum:** 2026-10-25 | **Status:** Dokumenterad behovs- och gapkartläggning på operatörens begäran.
> **Nulägesunderlag:** kod och planer vid `4899b38`, inklusive B-035 och genomfört 3c-P1.
> Föreslagna arbetspaket och samordningsansvar nedan är planeringsunderlag, inte nya
> produktbeslut, ändrad fasordning eller mandat att börja implementera. Uppdatera nuläget vid byggstart.

> **Planeringsuppföljning 2026-10-27:** operatören har godkänt dokument- och
> prioriteringsändringarna efter [riktningsgranskningen](../02_system/riktningsgranskning_2026-10-27.md).
> V-/S-gap och paket A/B återanvänds. Närmast förbereds en avgränsad
> fråge-/rapportkedja i [projekt 10/2](../projekt/10_operatörscentral/PROJEKTPLAN.md);
> paket A får ett samordnat kontraktsuppdrag och [projekt 6](../projekt/06_avdelningsfunktioner/PROJEKTPLAN.md)
> preciserar första värderings-/förklaringskontraktet för FTA. Den ursprungliga
> nulägeskartläggningen nedan är daterad; inga motorer eller simulatorsteg har
> byggts genom denna planeringsuppdatering.

## 1. Syfte och avgränsning

Målet är att kunna följa en sammanhängande månad i ett agentbaserat tjänstepensionsbolag:
anställning/lön → premie/faktura → mottagen betalning → kapital/garanti → förvaltning →
pension/betalning → avstämning och rapportering. Enskilda ärendedemonstrationer är en grund,
men visar ännu inte hela denna ekonomiska kedja.

Endast premiebestämd ITP1 ålderspension med traditionell förvaltning och garanti ingår.
Fondval, flytt och efterlevandeskydd är bortvalda enligt gällande produktpaket.
Kompletterande ålderspensionspremier kan ingå enligt PR-ITP1-016; en verifierad extern
premiebefrielsepremie innebär inte att bolaget erbjuder sjuk- eller premiebefrielseförsäkring.
Arbetsgivaren är försäkringstagare; den försäkrade gör tillåtna pensionsval.

Bolaget har även administratörsrollen i simuleringen. Verklig arbetsfördelning med Collectum
får inte antas vara en redan byggd integration. Bank, arbetsgivare, kunder och rapportmottagare
kan representeras av simulerade motparter. Riktiga externa anslutningar och kundportal behöver
inte finnas för en första intern körning.

Regler och numeriska beräkningar utförs i verifierad kod. Agenter utreder avvikelser,
samordnar arbete och förbereder förslag. Samma försäkringsoperationer används av människa,
agent och simulering genom tjänstelagret (B-028). Befintliga godkännanden gäller även här;
en simuleringsklocka får inte kringgå behörighets- eller regelkontroller.

## 2. Arbete som ska kunna representeras

| Område | Inkommande eller kalenderstyrt arbete | Avvikelser att pröva |
|---|---|---|
| Anställning/försäkring | Nyanställning, anställningsslut, återanställning, arbetsgivarbyte | Fel tillhörighet, saknad historik, flera anställningar |
| Lön/premie | Månatliga löneunderlag även vid oförändrad lön, uttrycklig noll, bonus/slutlön, kompletteringsinstruktion | Saknad rapport, dubblett, fel period, rättat underlag |
| Faktura/inbetalning | Premieberäkning, fakturering, mottagning och fördelning | Sen betalning, delbetalning, fel referens, okänd betalare |
| Kundärenden | Frågor, prognos, uttagsbegäran, deluttag, uppskov, paus, återstart, förlängning | Sen begäran, saknat underlag, klagomål, fullmaktsfråga |
| Pension/dödsfall | Månadsrätt, skatt, betalningsuppdrag, sista pensionsmånad, dödsfallsavräkning | Saknat konto, bankretur, sent dödsfallsbesked, obetalt anspråk |
| Kapitalförvaltning | Kurser, innehavsvärdering, likviditetsprognos, limiter, motiverad affär och avstämning | Inaktuellt pris, marknadsfall, likviditetsbrist, limitbrott |
| Aktuarie/risk/compliance | Garanti, reserv-/FTA-underlag, ALM, kapitalbehov, regelbevakning | Finansieringsbrist, osäkert underlag, ändrad regel eller antagande |
| Ekonomi/rapport/drift | Bokföring, månadsstängning, intern rapport, rapportkalender, driftkontroll | Avstämningsdifferens, missad tidsfrist, system-/leveransfel |

Standardposter bör kunna behandlas samlat; varje korrekt lönerad behöver inte bli ett
separat LLM-uppdrag. Saknad rapport är inte noll lön. Pausad pension, upphörd premie och
misslyckad bankbetalning är skilda förlopp. Dödsfall får inte hanteras som vanlig fribrevssättning.
En placeringskontroll kan ge utfallet att ingen affär behövs.

## 3. Gap i verksamhetsförmågorna

**Byggt** betyder kod inom angivna begränsningar, inte att hela verksamhetsflödet är färdigt.
**Konkret planerat** betyder identifierat byggsteg/backlogpunkt. **Specificerat** betyder
regel-/metodunderlag men ofullständig byggplan. **Målbild** betyder övergripande behov eller
mandat utan avgränsad leverans. Kolumnen *Nästa leverans* beskriver kvarstående arbete.

| ID | Förmåga och nuläge | Planläge före denna kartläggning | Nästa leverans och koppling |
|---|---|---|---|
| V-01 | Nyanställning och begränsat anställningsslut/fribrev är byggda | Konkret planerat i Fas 4 | Anställningshistorik för återanställning, arbetsgivarbyte, samtidiga anställningar och slutlön; projekt 1 |
| V-02 | Löneunderlag och premieförhandsberäkning finns; registrering skapar ingen premie | Konkret backlogpunkt i Fas 1f | Ordinarie premie ur underlag, kompletteringsinstruktioner, fördelning och fakturor; paket A |
| V-03 | Premietabellen har betalstatus, men inget komplett mottagningsflöde | Specificerat, PR-015–019 | Bankhändelser, matchning, delbetalning, oklara belopp och spårbar tilldelning till kapital/garanti; paket A |
| V-04 | Uttags-/pensionsmotorn saknas; lägesfält är inte en motor | Specificerat, PR-002–009 och 024–025; nämnt i projekt 3 | Uttagsdelar, planer, start, uppskov, paus/återstart, förlängning, belopps- och garantiomräkning; paket B |
| V-05 | Kapitalet i översikten är summan av betalda premietransaktioner | Specificerat, PR-008–011 och 020–023/028 | Kapitaljournal, historiska garantidelar, avkastning, avgift, skattebelastning, arvsvinst och separat bolagsstöd; paket B |
| V-06 | Pensionsskuld och bankutbetalningsflöde saknas | Specificerat, PR-010 och 026–028 | Månadsanspråk, skuld, skatt, bankuppdrag/kvitto, retur, nytt försök och slutavräkning; paket B |
| V-07 | Portfölj-/affärsmodeller finns lokalt; ingen aktiverad paper trading-funktion | Konkret planerat i Fas 2 | Marknadsdata, värdering, limiter, affärer och avstämd kassaflödeskoppling; projekt 5 |
| V-08 | Ärenden/UI och handläggaragent finns för `salary_report`; bredare intag saknas | Fortsättning beskriven i B-033 och ärendeförslaget | Fler typer, arbetsgivarfil, systemskapade avvikelser, tidsfrister och uppföljning; projekt 1 |
| V-09 | Rapportmall finns; kundbrev/intag/sändning är inte ett komplett flöde | Arkitektur/målbild, försäkringsbesked i backloggen | Verifierat sakunderlag, mottagare, skyddade utkast, godkännande, outbox och leveranskvitto; kommunikation/projekt 1 |
| V-10 | Premiehistorik är ingen ekonomisk huvudbok | Målbild/lucka i harness §9.6 | Bokförings- och avstämningsmodell för premie, placering, pension, skatt, avgift, eget kapital och månadsbokslut; föreslagen samordning projekt 6 |
| V-11 | Aktuariell SIM-grund finns; garanti-/reserv-/FTA-/ALM-motorer saknas | Metodunderlag och målbild i projekt 6/harness §9.2 | Verifierade beräkningar och finansierings-/riskkontroller med period och grundversion; projekt 6 med projekt 5 |
| V-12 | Premiescenarioanalys och rapportformat finns; samlad verksamhetsrapportering saknas | Målbild i B-029, dashboarddesign och harness §9.3 | Fastställ mottagare, tillämplighet, period, mått, kontroller, granskning och kvitto per rapport; projekt 2 och 6 |

Års-/kvartalsrapporter behöver inte inträffa i varje simulerad månad. Tillsyns-, skatte- och
partsrapportering måste få egna rapportkontrakt. En önskad rapport till kollektivavtalsparterna
är inget fastställt månatligt krav innan mottagare, mandat och innehåll bestämts.
Intern rapport kan införas först; rapportmall eller dashboard ersätter inte dess beräkningsunderlag.

### Vad B-035 tillför och vad det lämnar kvar

3c-P1 har byggt versionerade produktparametrar och uppslag per premiemånad; det ska inte
planeras som ett nytt gap. B-035 planerar även flödestillstånd, granskningsgrindar och
en regeländringsdemo. Första flödet startas stegvis av operatören. Parametrar och flödesmotor
kan återanvändas, men levererar inte i sig daglig schemaläggning, fakturor, bank eller månadsbokslut.
Bakgrundskörning/återupptagning är beskrivet som senare arbete.

## 4. Nya behov för en sammanhängande simulering

Vid kartläggningen saknades följande som egna, sammanhängande leveranser. De fångas nu i
[ATT_GORA](../ATT_GORA.md) under *Månadssimulering – byggluckor och samordning*.
Detaljerad konstruktion och ansvar behöver fastställas innan respektive del byggs.

| ID | Behov | Minsta avgränsade resultat att planera |
|---|---|---|
| S-01 | Simuleringsklocka och verksamhetskalender | Gemensamt affärsdatum för regler/operationer, bankdagar, förfallodatum och månadsskifte; verklig loggtid och aktiva körbudgetar hålls skilda. Dagens testbara datumfunktioner är en grund, inte en gemensam klocka |
| S-02 | Händelsegenerator/scenario | Versionsbundet scenario med seed, ordnade händelser, volymer, beroenden och väntade svar; löner, anställningar och kundval måste vara förenliga med beståndet. Fasta testhändelser för sällsynta fall |
| S-03 | Simulerade motparter | Definierade meddelanden/kvitton från bank, arbetsgivare, kunder och vid behov rapportmottagare, med fördröjning, komplettering, retur och okänt utfall. Återanvänd framtida domänkontrakt |
| S-04 | Avstämt ingående bolag | Ett versionerat startbestånd med pensionsplaner, historiska garantier, kassa/portfölj, fordringar, skulder och eget kapital. B-035:s äldre kohort ersätter inte denna avstämning |
| S-05 | Isolerad körning, paus och återställning | Scenario-/köridentitet genom affärshändelser, kontrollerad körmiljö, återställbar startpunkt och fortsatt körning efter mänskligt beslut. Backup finns; isolering och återställning för hela scenariot behöver utformas |
| S-06 | Facit och utvärdering | Oberoende förväntade utfall, ekonomiska avstämningar, rättighets-/tidsfristkontroller och mått på agentarbete, kvalitet och kostnad. Separera förutsägbara affärsresultat från varierande modellformuleringar |

Generatorn och motparterna får inte skriva facit direkt i affärstabellerna för att få
simuleringen att lyckas. Affärshändelser behandlas genom samma operationer och godkännanden
som motsvarande manuella arbete. Märkta startdata laddas separat och stäms av före körningen.

## 5. Föreslagna arbetspaket och beroenden

Paketen samlar befintliga behov och nya luckor. De är inte nya fasnummer eller beslutade
projektflyttar. Gemensamt ansvar och exakta schema-/API-kontrakt stäms av vid designstart.

### A. Premie- och betalningsflöde

**Samordningsförslag:** projekt 1 för administration, projekt 4:s godkända regler,
projekt 6 för ekonomiskt underlag; gränssnitt mot projekt 5 för kassaflöden.

- V-01–03: underlag → premie/fördelning → faktura → simulerad bankhändelse → matchning
  → mottagen nettopremie med kapital-/garantiunderlag och spårbarhet.
- Hantera minst saknad rapport, uttrycklig noll, rättelse, dubblett, delbetalning,
  försenad betalning och okänd referens. Redan mottagen premie får inte rättas ned utan
  den kapital- och garantispårning PR-019/020 kräver.
- Mottagningsspåret kan provas före paket B, men kapital/garanti är inte färdigt förrän
  V-05:s motor och journal tar emot underlaget. Koppla inte bara om status till `paid`.

### B. Pensions- och månadsavräkning

**Samordningsförslag:** projekt 1 och 6 för försäkringsoperationer och beräkningar,
projekt 5 för avkastning/likviditet. Projekt 3 använder sedan samma tjänsteoperationer.

- V-04–06 och V-11: separera premie-, pensions- och betalningsförlopp; bygg uttagsdelar,
  garanti/kapitaljournal, pensionsbelopp, månadsanspråk, skuld, skatt och betalningskvitton.
- Följ månadsordningen i PR-ITP1-020 och betalningsreglerna i PR-026. Håll pensionsmånad,
  bankdag och skatteredovisning isär. Nytt bankförsök får inte skapa ny rätt eller kapitaldebit.
- Prova start/uppskov/paus/återstart/förlängning, sista månaden, dödsfall/arvsvinst,
  finansieringsbrist och bankretur. Ingen sänkning av garanti för att dölja kapitalbrist.

### C. Månadssimulator och verifiering

**Samordningsförslag:** tvärgående bygguppdrag som först måste avgränsas; projekt 9
dokumenterar processerna men blir inte ägare av en separat runtime genom denna text.

- Samla S-01–06. Återanvänd harness och B-035:s flödesmotor där det passar; bygg inte
  en andra agentloop eller parallella affärsregler i simulatorn.
- Börja med A och en begränsad, tydligt märkt premiemånad. Utöka med B, portfölj och
  ekonomi när motorerna finns. En deldemo ska ange vilka led som ännu är ersatta av testunderlag.
- V-08–12 behöver planeras ihop med paketen: ärenden, kommunikation, bokföring,
  aktuariella kontroller och rapportunderlag får inte lämnas mellan delprojekten.

## 6. När en hel månad kan anses fungerande

Följande är föreslagna acceptanskriterier att konkretisera med testbelopp vid designstart:

1. Startläget är avstämt och har aktiva, fribrev och pensionsfall som behövs för scenariot.
   Ingående obetalda fakturor och pensionsskulder gör att kedjor från tidigare månader kan avslutas.
2. Klockan driver dagliga uppgifter och periodslut i bestämd ordning, med bevarade godkännandestopp.
   Körhorisonten omfattar även nästa bankdag och vid behov senare fakturaförfall.
3. Varje faktura, premie, kapitalrörelse, rättighetsändring, pensionsskuld och betalning kan följas
   till scenariohändelse, regel/parametergrund, beslut och kvitto.
4. Bank/kassa, portfölj, premie-/betalningsunderlag, individuell kapitaljournal och ekonomisk
   bokföring är avstämda mot sina respektive motposter. Kapital, garanti och FTA behandlas som
   skilda begrepp; de får inte antas vara samma belopp.
5. Samma händelse eller kvitto två gånger ger ingen dubbel ekonomisk effekt. Okänt utfall stoppas
   för avstämning. Stängd period rättas spårbart enligt reglerna, inte genom dold omskrivning.
6. Förberedda fel leder till rätt ärende, tidsfrist och mänsklig prövning. Ett avslag eller
   korrekt utebliven åtgärd kan vara ett lyckat utfall.
7. Månadsrapporten har låst period, identifierade underlag, öppna avvikelser, ekonomiska resultat
   och mått på handläggning/agentkostnad. Ej beräknat redovisas uttryckligen.
8. Scenariot kan återställas och köras igen. Affärsutfall jämförs med separat facit;
   modell, instruktioner, data, kod, regler och parametrar har identifierade versioner.

## 7. Källor och underhåll

- [Produktpaket PR-ITP1](produktregler/README.md), särskilt PR-014–020 och PR-024–032;
  [försäkringsvillkor](försäkringsvillkor.md) och [aktuariell grund](aktuariell_grund.md).
- [Operationer](../02_system/tjänstelager_operationer.md),
  [kapitalberäkning i nuläget](../src/services/operations/insured.py),
  [datumhjälpare](../src/services/operations/common.py),
  [regelgiltighet](../src/services/rules.py), [harness](../02_system/harness.md) §9–10.
- [B-035:s flödesplan](../02_system/flaggskeppsflöde.md),
  [backlog](../ATT_GORA.md), [dashboarddesign](../projekt/02_bi_insikter/DASHBOARD_DESIGN.md)
  och berörda projektplaner.

Denna fil är gemensam ingång för verksamhetskedjan och gap-ID:n. Backloggen håller öppna
uppgifter; projektplanerna länkar hit och beskriver sin del. Vid varje byggleverans uppdateras
berörda gap med vad som faktiskt byggts, verifieringsreferens och vad som återstår.
Detaljerade processkartor tas fram i projekt 9. Inga nya beslut skrivs i beslutsloggen genom denna kartläggning.
