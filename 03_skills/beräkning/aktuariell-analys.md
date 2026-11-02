# Aktuariell analys och antagandeprövning

Byggt på operatörens uppdrag 2026-11-02. Verktyg: `actuarial_workbench` i podden
`analys`. Implementation: `agents/actuarial_workbench.py`, tjänsteoperationen
`perform_actuarial_analysis` och `analytics/actuarial_experience.py`.

## Arbetsmetod

1. Förstå frågan, värderingsdatumet, åtagandet och beslutet som ska stödjas.
   Be om precisering i samtalet när det behövs. Välj själv arbetsgång.
2. Läs verktygskatalogen (`catalog`), befintliga grunder, värderingar och
   datareferenser (`read`). Tidigare leveranser finns via `recall`/`delivery`.
3. Pröva om data, metod och omfång räcker. Skilj historiskt utfall från scenario,
   syntetiska data, bokförda värden och rekonstruerat S-04-bestånd.
4. Kör analys (`analyze`) med parametrar enligt katalogens JSON-kontrakt.
   Beräkningens kod, inte språkmodellen, producerar skattningar och belopp.
5. Jämför utfall mot förväntan och undersök alternativ: datakvalitet, beståndets
   sammansättning, rapporteringsfördröjning, slump och systematiska avvikelser.
6. Redovisa osäkerhet och ekonomisk betydelse. En statistisk skillnad är inte
   ensam ett beslut om ny grund. Prognosvalidering använder en senare period.
7. Begär diagram (`chart`) och rapport (`report`) från sparade analysreferenser.
   Varje kvantitativ slutsats hänvisar till underlag. Diagrammens värden fylls
   aldrig i av modellen. Dolda värden blir aldrig noll.
8. Vid motiverad grundändring: `propose_basis` med analysreferenser och ny
   grundversion. Det skapar ett förslag i godkännandekön. Registrering av ett
   förslag och antagande av grunden är separata mänskliga steg.

## Tillgängliga analysfamiljer

- Skrivskyddad FTA-provberäkning av dagens bestånd.
- Scenarier på ett sparat eller nytt, kontrollsummerat utdrag: räntekurva, dödsintensitet, framtida
  dödlighetsförbättring, driftkostnad och kostnadsindexering.
- Garantins och driftkostnadernas årliga kassaflöden, avstämda mot FTA.
- Kohortens dödsrisk och överlevnad på en versionerad grund.
- Dödlighet: central exponering, Poisson A/E, Garwood-intervall, uttrycklig
  priorvikt och skydd för få dödsfall.
- Modelljämförelse: extern tabell, skattad intensitetsnivå och förbättring
  i begränsad modellfamilj, sista kalenderåret undanhållet från skattningen.
- Kostnadsutfall och beteendeutfall, med binomiala Wilson-intervall där tillämpligt.
- Värderingsjämförelse med isolerad grundeffekt. Resterande förändring är
  uttryckligen ej separerad; full förändringsanalys per verksamhetshändelse
  kräver premie-, utbetalnings-, dödsfalls- och planjournalerna.

## Databehov och gränser

Verktygskatalogen visar tillgängliga underlag och importkontrakt. Data ligger
i databasen, samma modeller används mot Lakebase. Observerat utfall registreras
av människa eller betrodd dataproducent via `register_actuarial_dataset`.
Agenten kan aldrig fabricera eller ändra observationsdata.

Modellfamiljen är inte Lee–Carter/CBD och har ingen professionell validering
för verklig drift. Livslång trendextrapolation, urvalseffekter, höga åldrar och
modellrisk behöver bedömas särskilt. Små egna bestånd behöver externa referenser.
För syntetiska data verifieras arbetsgången, inte antagandenas verkliga lämplighet.
Tillgångssida, ALM, full solvensmotor och full rapportinlämning har egna beroenden.

## Diagram och rapport

`reporting/analysis_chart.py` är gemensam kod för dataförankrade vektordiagram.
Den använder `digital_clarity.tokens.json`. Linjer, staplar och
osäkerhetsintervall bygger på numeriska kolumner i sparat analysresultat.
SVG hämtas från dialogens leveranser. Rapporten finns som Markdown och PDF
genom den befintliga rapportmotorn. PDF kräver registrerade DM Sans-filer.

En skattad intensitetsmultiplikator och grundens `risk_factor` har olika betydelse:
intensiteten skalar `-log(1-q)`, medan `risk_factor` skalar tabellens dödsrisk.
Överför inte den skattade multiplikatorn direkt till grundens `risk_factor`.
Använd scenariot för konsekvensanalys och pröva föreslagna grundparametrar separat.
