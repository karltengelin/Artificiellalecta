# Första BI-steget: premieeffekt av hypotetiskt IBB

## Syfte och gräns

Ge operatören ett granskningsbart svar på hur en annan nivå på inkomstbasbeloppet påverkar
månadspremierna i ett urval. Detta bygger analysdelen i projektets flöde från regeländring
till konsekvens för beståndet. Ett scenario är inte ett godkännande av nya produktregler.

Detta steg ändrar inga produktregler, rättigheter, försäkringar, premier eller databastabeller.
Det skapar ingen agent eller dashboard. Tjänster, godkännanden och kapitalförvaltning ligger
utanför uppgiften. Ingen årsprognos, garanti eller pensionskapital beräknas.

## Delar som finns

- `src/analytics/premium_impact.py`: ren beräkning och aggregerad Markdownrapport.
- `src/analytics/snapshot.py`: läsning av den befintliga JSONL-backupens relevanta tabeller.
- `scripts/analyze_premium_impact.py`: operatörens kommandoradsverktyg med syntetiskt demo
  eller explicit vald offline-backup.
- `tests/test_analytics_premium_impact.py`: handräknade resultat, gruppindelning,
  åldersgräns, felaktiga underlag, rapportinnehåll och backupkontroller.

Beräkningen återanvänder den befintliga rena ITP1-premiemotorn. Den jämför samma löner,
personer och månad med två IBB. Den inför inga nya premiesatser eller regelversioner.

## Underlag och antaganden

Urvalet omfattar ordinarie `premium`-transaktioner för `retirement_dc` i vald månad.
Lönen kommer från transaktionens `pensionable_salary_sek`, aldrig från personens aktuella lön.
Födelsedatum används internt för premiefönstret och åldersgrupper; det exporteras inte.
Åldersgrupperna avser uppnådd ålder vid månadens början. Premiefönstret följer motorns
regel om födelsemånad och kan därför ge noll premie trots en yngre åldersetikett.

Premietrappan räknas en gång per person, arbetsgivare och månad. Vid flera förmåner
förutsätter analysen att varje rad innehåller samma fulla månadslön; radernas premier
summeras och jämförs med en beräkning. Olika löner i samma grupp blockeras.
Om en framtida datakälla lagrar fördelade löneandelar måste adaptern och kontraktet ändras.
Samma person hos två arbetsgivare ger två separata beräkningar.

Nuvarande datamodell saknar historisk arbetsgivare på premietransaktionen. Offline-adaptern
kräver därför `--assume-current-employer`: operatören accepterar personens arbetsgivarkoppling
i backupen som ett scenarioantagande. Rapporten anger detta uttryckligen. Antagandet verifierar
inte historisk anställning och kan påverka både gruppering och segment. Det måste lösas före
produktionsmässig historisk analys.

Backupens årsparameter ger IBB i basen. Scenariots IBB väljs uttryckligen och gäller samma
analysår; det är inte en uppgift om nästa års officiella IBB. Referensexemplet använder
2026 och ett hypotetiskt IBB på 85 000 kr.

## Datakvalitet och avstämning

Lagrade belopp redovisas separat per status. `paid` betyder markerat som betalt;
`invoiced` och `pending` är inte inbetalningar. Makulerade rader redovisas men jämförs inte.
Rättelser, avgifter och andra transaktionstyper ingår inte.

Jämförelsen utesluter en hel grupp om identitet, lön eller födelsedatum saknas, om lönen
är negativ/icke ändlig, om gruppens födelsedatum eller löner skiljer sig, om ordinarie
premier är negativa eller om transaktions-ID/förmån förekommer dubbelt. Första blockerande
skäl räknas per grupp. Okända statusvärden och icke ändliga lagrade belopp avbryter analysen.
Backupfiler måste finnas, referenser måste gå att följa och radantal måste matcha manifestet.
Detta är strukturkontroller, inte en verifiering av alla affärsregler eller backupens samtidighet.

Rapporten skiljer mellan lagrad premie, omberäknad bas och scenario. Scenarioeffekten är
scenario minus omberäknad bas. Lagrad premie minus omberäknad bas är en avstämningssignal
som måste utredas; den ändrar inga tidigare belopp. Alla belopp beräknas med Decimal.

Antal personer och försäkringar avser dem som har premierader i urvalet. Analysen kan inte
upptäcka en försäkring som saknar premier helt och ska inte kallas en fullständig beståndsöversikt.
Noll rader eller noll jämförbara grupper ger inget meningsfullt underlag för slutsatser.

## Körning och rapporter

Från repots rot, med projektets Pythonmiljö och beroenden installerade:

```powershell
python scripts/analyze_premium_impact.py --month 2026-06 --scenario-ibb 85000 --output premieanalys-demo.md
python scripts/analyze_premium_impact.py --snapshot backups/<tid> --month 2026-06 --scenario-ibb 85000 --assume-current-employer --output premieanalys.md
```

Utan `--snapshot` används tre helt syntetiska exempel. Utan `--output` skrivs Markdown till
stdout. Verktyget läser inga miljöhemligheter, ansluter inte till Lakebase och uppdaterar
inte backupen. Spara verkliga urvalsrapporter utanför repot. Använd en färdig, oföränderlig
backup; behåll dess manifest och filer tillsammans med rapporten och notera kodens commit
för reproducerbarhet.

Rapporten exporterar inte personnr, namn, födelsedatum eller råa kund-ID. Arbetsgivare får
lokala alias som gäller endast inom rapporten. Små aggregat är inte automatiskt anonyma;
rapporterna är interna analysunderlag och behöver åtkomstbedömning före vidare exponering.

## Fortsatt integration och parallellt arbete

Offline-adaptern är ett operatörsverktyg, inte ett agentverktyg för direkt databasåtkomst.
Efter att Claudes tjänstearbete har integrerats ska en beroende uppgift synka senaste main,
fastställa ett läskontrakt och koppla analysen genom gemensamma tjänster och åtkomstregler.
Den rena beräkningen ska kunna behållas med en annan adapter.

Nästa design behöver särskilt hantera historisk arbetsgivare, löneunderlag vid flera
försäkringar, fullständig population, månadstrender, källa/regelversion och åtkomst till
små segment. Relation till skill-pod `bestand` och Data scientist-agenten i team `aktuarie`
följer projektplanens öppna designfrågor. Ingen separat BI-databas eller agentroll är beslutad här.

Gemensamma översiktsfiler och beslut lämnas till samordnad uppdatering efter integration.
