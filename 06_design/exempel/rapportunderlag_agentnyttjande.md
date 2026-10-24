<!-- page: cover | EXEMPELRAPPORT | Agentnyttjande -->
# När agenterna blir en del av arbetet.

Ledningsrapport om användning, kostnad, kvalitet och samverkan.

**Simulerad rapportmånad: september 2026. Upprättad 24 oktober 2026.**

Helt påhittade data för ett tänkt moget driftläge i Artificiellalecta. Rapporten visar hur en framtida uppföljning kan se ut. Den beskriver varken verklig septemberdrift eller vilka funktioner som är byggda i dag.

Design: Digital klarhet v1.0 / B-034. Rapportversion: 1.0.

<!-- page: executive | 01 / LEDNINGENS ÖVERBLICK | Hög användning. Lägre autonomi. -->
<!-- kpis: executive -->

## Slutsats
Agenter berör {{ai_share}} av månadens {{cases}} stängda ärenden, men endast {{internal_share}} avslutas som agentutförda interna flöden. Den avgörande skillnaden är hur mycket mänsklig handläggning som återstår, inte hur ofta en modell anropas.

Den modellerade bruttotidsvinsten är {{gross_hours}} timmar. Efter {{extra_hours}} timmar för tillkommande kontroll och plattformsarbete återstår {{net_hours}} timmar i kapacitetspotential. Samtidigt kräver scenariot fortfarande {{human_hours}} mänskliga timmar. Visionen om enpersonsdrift är därför inte uppnådd vid denna volym.

## Tre saker att agera på
- **Flytta fokus från täckning till avslut.** Öka andelen väl avgränsade interna flöden som kan slutföras av agenter. Bevara godkännande av externa handlingar.
- **Granska överlämningarna.** Handläggning och kommunikation står tillsammans för {{pair_share}} av alla delegerade uppdrag. Undersök hur ofta samma underlag måste förklaras igen.
- **Styr efter uppgiftens svårighet.** Rollen deep använder {{deep_token_share}} av tokens men står för {{deep_cost_share}} av modellkostnaden. Prova enklare modellroller där samma kvalitet kan visas.

## Tolkning
Samtliga observationer, jämförelser och slutsatser gäller exempeldata. Tidsvinsterna är modellerade, kvalitetsurvalet är litet och modellpriserna är konstruerade. Ingen effekt är verifierad i verklig drift.

<!-- page: cases | 02 / OPERATIV ANVÄNDNING | Vad görs med agenter - och utan? -->
![Stängda ärenden per delperiod och arbetssätt](figures/cases_weekly.svg)

{{table_modes}}

## Analys
Agentberöringen stiger från 64 procent i den första delperioden till 80 procent i de två sista. Förskjutningen är tydlig, men delperioderna har olika längd. Staplarna visar därför totalvolym, inte produktivitet per arbetsdag.

Jämfört med det fiktiva augustiscenariot ökar agentberöringen från 65 till 74 procent, samtidigt som totalvolymen ökar från 2 200 till 2 400 ärenden. Agentutförda interna flöden ökar från 20 till 30 procent. Ändrad ärendemix och bemanning kan bidra; utvecklingen visar inte i sig en kausal AI-effekt.

**Definition:** Agentstöd innebär att en människa fortfarande driver huvuddelen av handläggningen. Agentutförda interna flöden saknar rutinmässig manuell ärendehantering, men belastas med viss tillsynstid. Externa handlingar får inte utföras utan föreskrivet godkännande.

<!-- page: processes | 03 / PROCESSER | Automationen är ojämnt fördelad. -->
![Ärendevolym per process och arbetssätt](figures/cases_process.svg)

{{table_process}}

## Analys
Löner och premier är den största processen och har 85 procents agentberöring. Regelverk och rapportering har bara 50 procents beröring, men varje avlastad handläggning kan vara tidsmässigt betydelsefull. Enbart antal ärenden skulle undervärdera det arbetet.

Övriga kundärenden har låg agentberöring och varierande innehåll. Prioritera återkommande delmoment och tydliga överlämningar innan bred automatisering. Procentsatserna mäter användning i scenariot, inte hur stor andel av alla uppgifter som säkert kan automatiseras.

<!-- page: tokens | 04 / TOKENANVÄNDNING | Tre agenter står för mer än halva volymen. -->
![Input, cachelagrad input och output per agent i miljoner tokens](figures/tokens_agent.svg)

## Analys
Handläggaragenten använder 48 miljoner tokens, motsvarande 28,6 procent av totalen. Handläggning, Data scientist och Aktuarie står tillsammans för {{top3_token_share}}. Fördjupa därför arbetet med kontextstorlek, verktygssvar och återanvändbara underlag hos dessa tre.

Totalen {{tokens_m}} miljoner tokens består av 140 miljoner input och 28 miljoner output. Av inputvolymen är 70 miljoner cachelagrade. Cachelagrad input ingår redan i input och får inte adderas en gång till. Cacheandelen är 50 procent av input, inte av total tokenvolym.

{{table_token_scope}}

**Avgränsning:** 85 procent av tokens och kostnad är ärendehänförda, 15 procent avser fristående uppdrag. Fördelningen är samma inom varje modellroll. Diagrammet visar all användning; måttet per ärende utesluter fristående uppdrag.

<!-- page: agents | 05 / AGENTÖVERSIKT | Volym och kostnad berättar olika historier. -->
{{table_agents}}

## Analys
Compliance och Aktuarie står tillsammans för {{specialist_cost_share}} av modellkostnaden. Det beror främst på att de använder deep-rollen oftare, inte på att de har flest körningar. Handläggning är störst i tokens men har en betydligt billigare rollmix.

En körning är ett agentsegment med eget run_id. En rotkörning kan delegera till flera nya körningar. Månadens {{runs}} körningar kommer från 2 000 rotkörningar och {{delegations}} delegerade körningar. Antalet körningar är därför varken antalet ärenden eller antalet unika användaruppdrag.

## Rekommenderad uppföljning
Jämför varje agent med dess egna uppgifter och svårighetsgrad över tid. Följ kostnad per accepterat resultat och andel utfall som kräver omarbete. En enkel rangordning efter kronor eller tokens missgynnar specialistuppdrag och kan uppmuntra sämre kvalitet.

**Läs tabellen:** Cache avser cachelagrad input. Kostnad är beräknad med rapportens fiktiva rollpriser. Avrundade radbelopp kan avvika från summerad total; totalen beräknas före avrundning.

<!-- page: costs | 06 / MODELLROLLER | Deep driver kostnaden, inte volymen. -->
![Andel tokenvolym och andel kostnad per modellroll](figures/role_share.svg)

{{table_prices}}

## Analys
Deep svarar för {{deep_token_share}} av tokenvolymen men {{deep_cost_share}} av modellkostnaden. Att korta ett deep-anrop kan därför vara mer ekonomiskt relevant än att ta bort flera korta fast-anrop. Modellvalet ska dock följa uppgift och verifierad kvalitet.

{{table_role_totals}}

**Prisgrund:** Alla priser ovan är uttryckligen påhittade SEK per miljon tokens, utan moms. De är inte aktuella priser från OpenAI, Anthropic eller någon annan leverantör. Kostnaden är okachelagrad input gånger dess pris, plus cachelagrad input gånger cachepriset, plus output gånger outputpriset. Inget separat debiterat cache-skrivpåslag ingår i modellen.

<!-- page: network | 07 / AGENTSAMVERKAN | Vem beställer arbete av vem? -->
![Riktad matris över delegerade agentuppdrag](figures/delegation_matrix.svg)

## Så läses bilden
Raden är avsändande agent och kolumnen mottagare. Talen är nya delegerade uppdrag som startat en barnkörning. Ett vanligt svar i samma konversation räknas inte som ett nytt uppdrag. Nollor lämnas tomma och diagonalen används inte för självanrop.

Totalt finns {{delegations}} delegeringar. {{cross_team}} går mellan team och {{within_team}} inom team. Uppdrag till specialister passerar deras teamledare när de kommer från ett annat team, i linje med målarkitekturen. Matrisen är en fiktiv målbild, inte en export från dagens harness.

**Förkortningar:** HAND handläggning; KOM kommunikation; KAP portfölj; AKT aktuarie; DATA Data scientist; COMP compliance; RAPP rapportering; EKO ekonomi; INK inköp; UTV utveckling.

<!-- page: handoffs | 08 / ÖVERLÄMNINGAR | Den största relationen går åt båda håll. -->
![De åtta största riktade uppdragsflödena](figures/top_delegations.svg)

## Analys
Handläggning skickar 1 400 uppdrag till Kommunikation och får 1 200 nya uppdrag tillbaka. Tillsammans motsvarar relationen 2 600 uppdrag, eller {{pair_share}} av all delegering. Det kan vara en legitim uppdelning av ärendelogik och kanalansvar, men också ett tecken på upprepade kompletteringar.

Volymen ensam visar inte att ett samarbete är ineffektivt. Följ därför andel kompletta beställningar, antal kompletteringsvarv och ledtid från första beställning till godkänt underlag. Svarstexter ska inte misstas för nya delegeringar i mätningen.

## Förbättring att pröva
Inför ett gemensamt uppdragskontrakt med ärendereferens, mottagare, syfte, källor, beslut och förväntat format. Återanvänd underlag via behörighetsstyrda referenser. Att kopiera hela historiken mellan team ökar både kontextkostnad och risken för felaktig spridning av uppgifter.

<!-- page: reliability | 09 / DRIFT OCH KONTROLL | Ett stopp kan vara ett korrekt resultat. -->
![Avslutstillstånd för agentkörningar](figures/run_outcomes.svg)

{{table_approvals}}

## Analys
92 procent av körsegmenten slutar som completed. Ytterligare 5 procent väntar på godkännande. Det är ett kontrollerat stopp, inte ett tekniskt fel. Av {{runs}} segment slutar 88 som blocked och 22 som failed. Orsakerna måste följas separat; en väl fungerande spärr kan höja säkerheten även om den sänker den råa slutförandeandelen.

820 unika förslag har skapats. 780 är avgjorda och 40 öppna i scenariots periodstängning. 550 väntande körsegment är ett annat mått: ett segment kan skapa flera förslag. Bland avgjorda förslag är medianväntan 42 minuter och p95 210 minuter, båda konstruerade exempelvärden.

**Omtag:** {{retries}} av {{calls}} modellanrop är omtag, motsvarande {{retry_call_share}}. De står för antagna 8 procent av tokens och kostnad, redan inkluderade i månadstotalen. Följ både första-gången-rätt och slutligt utfall; extra försök kan dölja en instabil verktygsintegration.

<!-- page: quality | 10 / KVALITET OCH SERVICE | Snabbare flöden måste också bli rätt. -->
![Avvikelser i stratifierat kvalitetsurval](figures/quality_sample.svg)

{{table_sla}}

## Analys
I ett stratifierat stickprov med 300 granskade ärenden finns 18 avvikelser: 4 större och 14 mindre, inga kritiska. De lägre felfrekvenserna i agentgrupperna kan bero på enklare ärenden och andra urvalsregler. Utan jämförbar svårighetsgrad och större urval kan ingen kausal kvalitetseffekt dras.

SLA i scenariot är 16 arbetstimmar från mottagning till stängning. {{sla_breaches}} av {{cases}} ärenden överskrider gränsen. Median och p95 är konstruerade för respektive kohort; ett totalt p95 kan inte beräknas genom att väga ihop dessa tre p95-värden.

## Föreslagen kvalitetsgrind
Innan automatandelen höjs: granska regelriktighet, källstöd, motivering, spårbarhet och behov av omarbete. Behåll obligatoriska godkännanden även när en agent presterar väl i stickprovet. Tid till stängning och aktiv mänsklig arbetstid är olika mått.

<!-- page: capacity | 11 / MÄNSKLIG KAPACITET | Avlastning räcker inte hela vägen. -->
![Modellerad mänsklig arbetsbelastning i timmar](figures/human_capacity.svg)

{{table_hours}}

## Analys
Direkt handläggning minskar från {{baseline_hours}} till {{direct_hours}} timmar i tidsmodellen. Tillkommande granskning, mandatförvaltning och avvikelsearbete antas kräva 96 timmar, plattformsdrift 40 timmar. Den totala mänskliga belastningen blir {{human_hours}} timmar.

Scenariot antar en tillgänglig mänsklig kapacitet om 800 timmar, ungefär fem heltidsmånader om 160 timmar. Belastningen ligger {{capacity_gap}} timmar över denna nivå. Det är långt från visionens enpersonsram om 160 timmar, även om arbetet kan vara fördelat på anställda, operatör eller externa resurser.

**Begränsning:** Alla tider är antaganden. Baslinjen har samma processmix men ingen justering för svårighetsgrad inom processen. Tillsyn per ärende ingår i direkt arbete; de 136 timmarna avser separata centrala aktiviteter. Frigjord tid är kapacitetspotential, inte realiserad personal- eller kassabesparing.

<!-- page: economics | 12 / EKONOMI | Modellnotan är bara en del av kalkylen. -->
{{table_economics}}

![Illustrativ kostnad för AI, plattform och tillkommande mänskligt arbete](figures/program_cost.svg)

## Analys
Den direkta modellkostnaden är {{model_cost}} kronor. Tillkommande kontroll- och plattformsarbete värderas till {{overhead_value}} kronor med rapportens antagna 600 kronor per timme. I detta scenario är alltså människans arbete en större post än själva modellnotan.

Den teoretiska nettopotentialen är {{net_value}} kronor efter värdering av nettotiden och avdrag för modell och plattform. Detta är en räkneövning, inte redovisad vinst eller realiserad kassabesparing. Befintlig handläggningslön, införandeinvestering, utbildning, förändringsarbete och eventuell kvalitetsförlust ingår inte som fullständiga kostnadsposter.

**Enhetskostnad:** Ärendehänförd modellkostnad är {{case_model_cost}} kronor för {{ai_cases}} agentberörda ärenden, alltså {{cost_per_ai_case}} kronor per sådant ärende. De fristående uppdragens kostnad har uteslutits ur täljaren. Hela programkostnaden ska inte utan vidare divideras med ett enda teams ärendevolym.

<!-- page: optimization | 13 / FÖRBÄTTRINGSSCENARIER | Små förändringar kan testas kontrollerat. -->
{{table_optimization}}

## Ett verksamhetsscenario
Flytta 360 ärenden från agentstöd till agentutförda interna flöden: 240 inom löner och premier, 72 inom stamdata samt 48 inom avstämning. Med antagna handläggningstider frigör det ytterligare {{automation_hours}} timmar. Agentberöringen ligger kvar på 74 procent, medan automatandelen stiger från 30 till 45 procent.

Det illustrerar varför täckning kan stå still samtidigt som nyttan ökar. Efter förändringen skulle scenariots mänskliga belastning fortfarande vara {{automation_human_hours}} timmar, om centralt kontrollarbete och plattformsarbete är oförändrade. Mer automatik ensamt löser alltså inte enpersonsvisionen vid denna volym.

## Så ska scenarierna användas
Kostnadsalternativen ovan är fristående beräkningar med samma grunddata. De får inte summeras: cache, omtag och modellbyte kan beröra samma anrop. Ingen kvalitets- eller faktisk kostnadseffekt är verifierad. Pröva först på jämförbara uppgifter med oförändrade behörigheter och godkännandekrav.

<!-- page: actions | 14 / ÅTGÄRDSPLAN | Mät nyttan där arbetet faktiskt förändras. -->
{{table_actions}}

## Rekommenderad ordning i det fiktiva driftläget
Först behövs sammanhängande mätkedjor från ärende till körning, modell- och verktygsanrop samt mänskligt beslut. Därefter går det att förbättra beställningskvalitet och omtag. Först när jämförbar kvalitet kan visas bör fler flöden eller billigare modellroller provas.

## Ledningens månadsfrågor
- Hur många jämförbara ärenden avslutades med godkänt resultat, och hur mycket mänskligt arbete återstod?
- Vilka agentrelationer skapade mest kompletteringsarbete eller väntan?
- Vilka modellkostnader gav verifierat värde och vilka drevs av omtag eller stor kontext?
- Vilka fel stoppades, vilka passerade kvalitetsgrinden och vilka återkom?

Åtgärdsplanen är ett exempel för det tänkta mogna bolaget. Den innebär inga nya projektbeslut och ersätter inte den faktiska byggordningen i ATT_GORA.md.

<!-- page: method | 15 / METOD OCH AVSTÄMNING | Samma underlag ska gå att följa hela vägen. -->
{{table_reconciliation}}

## Kohorter och definitioner
Ärendekohorten omfattar månadens stängda ärenden. Körningar, anrop och delegeringar avser månadens startade händelser. Populationerna har ingen generell ett-till-ett-relation. Exemplet har 1 776 ärendehänförda och 224 fristående rotuppdrag, totalt 2 000.

Tokenvolym, kostnad, omtag och ärendetillhörighet är överlappande klassificeringar av samma modellanrop. De får inte läggas ihop. Alla timmar är modellerade; kvalitetsutfall, ledtider och godkännandetider är konstruerade scenariodata.

## Hur verklig mätning kan försörja rapporten
Modellanropsloggen kan ge modellroll, tokenvolym, cache och prisgrund. Körjournalen ger run_id, rot och barn, utfall och budget. Ärenden, operation_events och approval_requests ger ärendekohorter och mänskliga beslut. Delegering och aktiva handläggningsminuter behöver egen, entydig instrumentering innan motsvarande effektmått kan användas i verklig drift.

**Källor:** data/examples/agent_usage_2026_09.json (helt fiktivt). Agentnamn och team följer projektets ekosystem. Formgivning: Digital klarhet v1.0, B-034. Inga företagsloggar, kunduppgifter, fakturor eller verkliga modellpriser har använts.

**Reproducerbarhet:** Generatorn bygger PDF, diagram och Markdown och validerar avstämningarna. Beräkning sker före avrundning. Körinstruktion finns i 06_design/exempel/README.md.
