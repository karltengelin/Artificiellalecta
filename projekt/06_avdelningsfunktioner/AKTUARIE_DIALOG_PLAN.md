# Aktuarien som verksamhetskollega – dialog och analys

Beställt av Karl 2026-11-02. Utgår från företagsvisionen i MASTER_CONTEXT,
B-028, B-034, B-037 och B-042. Detta är en byggplan, ingen ny beslutsloggspost.

## Resultat och arbetsform

Operatören samtalar med aktuarien, preciserar uppdrag och följer upp resultaten.
Agenten väljer själv bland registrerade data- och analysoperationer. Inga
uppgiftsspecifika knappar behövs för erfarenhetsanalys eller osäkerhetsbedömning.
Befintliga register och mänskliga beslutsvägar behålls som underlag och kontroll.

1. Varaktig dialog och körstatus i databasen; samma harness, AI-klient och budget.
2. Verktygskatalog med maskinläsbara kontrakt. Befintliga aggregat läses med
   aktuariens begränsade roll. En uttrycklig systemarbetare gör tunga analyser
   på servern genom tjänstelagret; endast skyddade aggregat lämnar arbetaren.
   Agenten får aldrig individutdrag, SQL, Python-exekvering eller databasnycklar.
3. Analys av låsta/sparade värderingsunderlag: känsligheter, kassaflöden,
   jämförelser och uttrycklig oförklarad förändring. Basen ändras aldrig.
4. Versionerade erfarenhets- och referensdata med källa och innehållskontroll.
   Dödlighet (exponering och dödsfall), kostnader och beteende prövas i betrodd
   statistik. Modeller valideras på annan period än skattningen.
5. Diagram hämtar tal ur sparade analysresultat. Gemensamma designvärden styr
   färger och typografi; rapporter binder data, metod, scenario och begränsningar.
6. Agenten skriver förslag. Befintliga HUMAN_ONLY-gränser för antagande och
   fastställande består. Granskning av en annan modell är stöd för människan.

## Förhållande till byggordningen

Detta samlar de relevanta delarna av A7–A9 kring ett faktiskt arbetsförlopp,
och ansluter dem till A3/OC-8. Ingen separat körmiljö eller ny agent behövs.
ALM kräver en tillgångssida; ekonomi och FI-inlämning har egna beroenden.
Obyggda motorer och saknad data ska vara synliga i katalog och leveranser.
Modellernas omfång och valideringsstatus redovisas; ett fungerande anrop är
inte bevis för professionell lämplighet i verklig verksamhet.

## Data och införande

Samma SQLAlchemy-modeller och tjänsteoperationer används lokalt och mot Lakebase.
Migrationen skapar endast nya tabeller, med torrkörning och kontroll av befintliga
radantal. Ingen verklig erfarenhet skapas automatiskt från mockpremier. Import
kräver mänsklig/systemstyrd källa och tydlig märkning av syntetiska data.
Historiska garantigrunder påverkas aldrig av erfarenhetsanalys.

## Acceptans

- Samtal och följdfrågor återfinns efter omstart. Samtidiga beställningar,
  dubbelklick och avbrutna körningar hanteras utan dold omkörning.
- Öppet uppdrag kan upptäcka data, läsa källa, välja analys, framställa diagram
  och rapport och förklara begränsningar utan att välja ett uppdragsspecifikt formulär.
- Oberoende kontrollfall för statistik, scenarier och kassaflöden; småcellsskydd,
  manipulationsprov, behörigheter, PostgreSQL och den faktiska webbvägen verifieras.
- Saknat utfall ger databehov. Ett scenario eller en syntetisk observation
  presenteras aldrig som fastställd grund eller verifierad verklig erfarenhet.

## Leveransläge 2026-11-02

Byggt och verifierat på arbetsbranchen: dialog, instruktioner, analysgateway,
datakontrakt och import, beräkningsmotorer, diagram, rapporter och grundförslag.
Detaljer om provresultat och kvarstående visuell kontroll finns i
[driftbeskrivningen](../../02_system/aktuarie_dialog.md#verifiering-och-införandestatus-2026-11-02).
Riktig modell och skrivskyddad Lakebase-analys är provade. Merge till `main`,
de nya tabellerna i Lakebase och driftsättning återstår. Saknade verksamhetsmotorer
och observationsleveranser enligt ovan kvarstår som egna beroenden.
