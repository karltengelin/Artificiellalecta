# Projekt 9: Processkartor och agenternas arbete

> Nytt avgränsat dokumentationsprojekt på Karls begäran 2026-10-11.
> Tillagt i programöversikten (MASTER_CONTEXT §4b) 2026-10-12; inget nytt beslutsnummer loggas.

## Syfte

Göra bolagets processer begripliga för Karl: när en agent arbetar, vilket mandat den har,
vilka skills/verktyg och system den använder, var resultatet sparas och när människan beslutar.

## Scope och relation till projekt 8

Processkartor i Markdown med Mermaid, en översikt följd av mer detaljerade flöden.
Projekt 8 bygger den drillbara företagsöversikten; detta projekt levererar granskade processbilder
som översikten kan konsumera. Det skapar ingen ny agent, flödesmotor eller separat runtime.

Varje karta visar utlösare, ansvarigt team/roll, skill, tjänsteoperation/verktyg, indata,
resultat, läsning/skrivning, godkännandestopp, fel/återgång och slutpunkt. Detaljer kan ligga
i en tabell under bilden för att hålla flödet läsbart. Generiskt "AI gör analys" räcker inte.

## Status och första kartor

🟡 Plan upplagd; första målflödet finns i
[BI:s dashboarddesign](../02_bi_insikter/DASHBOARD_DESIGN.md).
Det är en föreslagen arkitektur, inte en verifierad karta över körande system.

Föreslagen arbetsordning:

1. Dashboard, Genie-fråga och rapportberedning från gemensamt dataunderlag.
2. Regeländring: källa → tolkning → produktregel → kod → konsekvensanalys → eventuell kommunikation.
3. Handläggningsärende: operatör/agent → tjänst → eventuellt godkännande → ändring och händelselogg.
4. Premie till kapital, garanti och pensionsutbetalning, med avstämningspunkter.
5. Aktuariell värdering och riskberäkning → granskning → BI/rapportering.

## Hur kartorna hålls trovärdiga

### Underlag från verksamhetskartläggningen 2026-10-25

[Processöversikten](../../01_domän/processer_översikt.md) finns nu som gemensam ingång:
dagligt arbete, verksamhetsgap V-01–12, simuleringsbehov S-01–06 och föreslagna paket A–C.
Detaljerade kartor och verifierade nulägesflöden återstår. Använd gap-ID:n för att visa
beroenden och byggstatus i de fem kartorna ovan, särskilt premie → kapital → pension och
aktuariellt/ekonomiskt underlag → rapport. Visa även gränssnitt mot simulerade motparter,
månadsordning och godkännandestopp. Projekt 9 dokumenterar dessa behov; en simulator-runtime
eller nya agentmandat ingår inte genom denna dokumentationsuppdatering.

### Granskningsregler

- Märk varje karta som nuläge eller målflöde; märk enskilda steg som byggda, planerade eller öppna.
- Länka till källdokument och exakta operationer där de finns. Föreslagna verktygsnamn får
  inte presenteras som implementerade. Ange granskningsdatum och kodversion för nulägeskartor.
- Rita manuella/deterministiska steg som sådana; tilldela inte en agent arbete som systemet gör självt.
- Beskriv mandat och behörighet enligt agentekosystemet/tjänstelagret, inte genom nya roller.
- Visa externa handlingar med operatörens godkännande enligt MASTER_CONTEXT §3.5.
- Granska berörda kartor när kontrakt eller processer ändras. Kartor beslutar inte nya regler.

## Beroenden och avgränsning vid parallellt arbete

Källor: [agentekosystemet](../../02_system/agentekosystem.md),
[tjänstelagret](../../02_system/tjänstelager.md), respektive projektplan och faktisk kod.
Nulägeskartor för Claudes ändringar görs efter integration/synk. Under tiden kan målflöden
och kartmallar utformas utan att ändra datamodeller, API-kontrakt eller gemensamma styrdokument.

## Klart när

Karl kan följa en process från utlösare till resultat och se vem som gör varje steg, med vilket
verktyg, vilket underlag och vilket godkännande. Bilden och källorna beskriver samma process,
och skillnaden mellan nuläge och avsedd lösning är tydlig.
