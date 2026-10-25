# Projekt 10: Operatörscentral på VD-nivå

> Planeringsuppdrag från Karl i chatten 2026-10-25. Ingår i programmet
> AI-native tjänstepensionsbolag. Inget nytt beslutsnummer loggas genom planen.
> **Status:** plan och första interaktiva skiss; ingen driftsatt operatörscentral.

## Syfte och avgränsning

Ge Karl en gemensam arbetsyta som VD: följa bolagets ekonomiska utveckling,
förstå teamens arbete och kostnader, ställa frågor mot data och fatta
inriktningsbeslut om prioriteringar, agentbudget och modellpolicy.

Operatörscentralens arbetsenhet är ett bolagsmått, ett team, ett analysuppdrag
eller ett ledningsbeslut. Enskilda handläggarärenden och deras godkännanden
hanteras i specialiserade gränssnitt. Här visas sammanlagda volymer, trender,
flaskhalsar och systematiska avvikelser. Länkar öppnar rätt specialistvy när
Karl vill arbeta vidare. Befintliga domängodkännanden gäller även fortsättningsvis.

Karl är högsta beslutsfattare. Den gemensamma frågeingången samordnar uppdrag
via teamens ledande agenter och sammanställer underlag; den får inget eget
VD-mandat och inga utökade data- eller skrivrättigheter.

## Produktens sex delar

| Del | Fråga som ska besvaras | Första avgränsning |
|---|---|---|
| Bolagsläge | Hur mår bolaget och vad har ändrats? | Bestånd/premier från verifierade mått; konsolidering, kapital, FTA och likviditet när beräkningsunderlagen finns |
| Team och leveranser | Vad gör teamen, vad levererar de och vad hindrar dem? | Körstatus, avslutade uppdrag, fel/stopp och sammanfattade hinder; skilj konfigurerat team från körande team |
| Agentekonomi | Vad kostar agentarbetet och vilken nytta ger det? | Uppskattad kostnad per period, team, modell och uppdrag; resultat och kvalitet bredvid kostnad |
| Ledningsfrågor | Vad behöver Karl bestämma om riktningen? | Underlag för modellpolicy, budget, prioriteringar och väsentliga avvikelser; inget generellt inflöde av handläggarärenden |
| Fråga bolaget | Varför ändrades ett mått, och vad bör vi undersöka? | En fråga med vald period och datakälla till rätt team; svar med källor, antaganden och begränsningar |
| Styrning | Hur ska agenterna arbeta framåt? | Förhandsgranska global modellpolicy och undantag, därefter kontrollerad aktivering; koppling till harnessens körgränser |

## Första skissen

[SKISS.md](SKISS.md) beskriver sidornas innehåll, interaktioner och exempeldata.
Den visuella skissen följer Digital klarhet (B-034) och visar föreslagen
användning. Alla kostnadsserier, uppdrag och ledningsunderlag i skissen är
syntetiska. Den gör inga modellanrop och ändrar inga riktiga inställningar.

## Leveranser och byggordning

Detta är arbetspaket inom projekt 10, inte nya programfaser. B-028:s byggordning
och B-035:s flaggskeppsarbete består. Läsbar överblick kan byggas innan alla
ekonomiska motorer finns; saknade mått visas som **ej beräknat**.

| Paket | Leverans och klart-kriterium | Beroenden |
|---|---|---|
| OC-0: Avgränsning och kontrakt | Mått- och händelsekontrakt, ledningseskaleringar, frågerouting, autentisering och auktoritativ lagring för styrinställningar preciserade. Denna plan och skissen är första underlag | Projekt 2, 6 och harness; designavstämning med Karl |
| OC-1: Läsbar ledningsöversikt | Navigerbar vy för bolagsläge, team, kostnader och fördjupning. Visar datakälla, period, färskhet, underlag och verklig implementeringsstatus. Ingen person- eller ärendelista | Befintlig FastAPI/Jinja2/HTMX-grund och granskade läsadaptrar; B-029 för BI |
| OC-2: Agentekonomi och uppföljning | Summeringar kan stämmas av mot anropslogg och körjournal. Testfall för reservanrop, fel, okänd kostnad och föräldra-/barnkörningar; inga dubblerade kostnader | AI-logg, harnessjournal och stabila körreferenser; delegeringsdata när 3c-1 finns |
| OC-3: Gemensam frågeingång | Fråga routas till rätt teamledare med avgränsat mandat och budget. Svaret visar underlag, datum och ansvarigt team. Saknat underlag blir ett tydligt svar | Befintliga agentprofiler och behöriga analysverktyg; samordnade barnuppdrag kräver 3c-1 |
| OC-4: Ledningsunderlag | Prioriterade, sammanfattade frågor med alternativ, konsekvenser, ägare och beslutsspår. Rutinärenden stannar i specialistvyer. Eskaleringsvillkor granskas före aktivering | OC-1/2; definierade domängränser och rapportkontrakt |
| OC-5: Modellpolicy och budget | Autentiserad Karl kan förhandsgranska och aktivera versionssatt policy för nya körningar: globalt val, rollmappning, teamundantag, reservpolicy och körbudget. Granskning visar berörda team och faktisk effekt | OC-0, AI-lagret och 3b-9; inga styrskrivningar före autentisering och ändringslogg |
| OC-6: Ekonomisk fördjupning och acceptans | Konsolidering, FTA, kapital och likviditet ansluts när respektive modell är verifierad; period- och grundversioner går att följa. Sammanhängande VD-scenario godkänt | Projekt 2, 5 och 6; definierad konsoliderings-/fördelningsmodell |

**Rekommenderad första byggleverans:** OC-0 följt av OC-1 och en smal OC-2:
bolagsöversikt med ärligt markerade dataluckor, teamstatus samt agentkostnader ur
befintliga loggar. Därefter frågor till ett team åt gången. Automatisk
samordning över flera team och skrivande styrning öppnas först med sina beroenden.
Inga kalendertider eller generell omprioritering av pågående arbete är beslutade.

## Ansvar och samordning

| Område | Äger |
|---|---|
| Projekt 10 | VD-upplevelse, navigation, ledningsunderlag och samlad operatörscentral |
| Projekt 2: BI & insikter | Gemensamma mått, historik, analys-/Genie-underlag och Databricks-dashboard enligt B-029 |
| Harness och AI-lagret | Teamrouting, körpolicy, budgetverkställighet, körspår, modellroller och leverantörsval |
| Projekt 1 och övriga specialistytor | Enskilda ärenden, domänhandlingar och deras godkännanden |
| Projekt 5 och 6 | Kapitalvärdering, ekonomi, aktuariella motorer och underlag för konsolidering/risk |
| Projekt 8 och 9 | Projektkarta respektive processkartor som förklarar hur bolaget hänger ihop |

Projekt 10 bygger inga parallella kapital-, reserv-, bokförings- eller
försäkringsmotorer. Tekniska gränser och planerade kontrakt finns i
[operatörscentralens arkitektur](../../02_system/operatörscentral.md).

## Acceptans ur Karls perspektiv

1. På startsidan kan Karl se bolagets läge och viktigaste förändringar utan att
   läsa personuppgifter eller enskilda handläggarärenden.
2. Ett mått kan följas till definition, datakälla, datum och beräkningsversion.
   Saknad eller gammal data har en egen status och blir aldrig noll eller grönt.
3. Kostnadsförändring kan förklaras per team, modell och uppdrag, inklusive
   fel/reservanrop och vad arbetet levererat. Okänd kostnad framgår.
4. Frågan ”Varför har agentkostnaden ökat?” ger källbundet underlag; ”Varför
   sjönk konsolideringen?” anger tydligt om beräkningsunderlag ännu saknas.
5. ”Använd OpenAI för nya körningar” visar berörda roller, teamundantag och
   reservval före aktivering. Ett exklusivt leverantörsval får ingen dold reserv
   hos den andra leverantören. Pågående rotkörningar behåller sin policyversion.
6. Ett inriktningsbeslut kan följas från underlag till beslutad ändring och
   uppföljning. Det ersätter inte en domäns separata genomförandegodkännande.
7. Alla sidor fungerar med tangentbord och smal skärm. Skissen har inga
   livekopplingar; framtida driftsatt styrning kräver autentiserad operatör.

## Återstående designval

- Hur och när Databricks-dashboarden bäddas in; en gemensam måttdefinition
  ska ligga bakom både översikten och BI-fördjupningen.
- Hur loggar indexeras och hur teamens uppdrag/leveranser får gemensamma referenser.
- Vilka trösklar och sammanfattningar som motiverar en VD-eskalering.
- Hur styrinställningar lagras och versionssätts tillsammans med befintlig
  YAML-konfiguration; en auktoritativ källa per inställning.
- Vilka teamundantag och reservpolicyer som ska vara standard vid leverantörsbyte.

Beslut som behöver loggas formuleras som förslag till Karl. Denna plan för inte
in nya poster i BESLUTSLOGG och aktiverar inga befogenheter.
