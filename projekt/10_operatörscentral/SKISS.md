# Första skissen – operatörscentral

**Version:** 0.1 | **Datum:** 2026-10-25 | **Designgrund:** Digital klarhet v1.0 (B-034)

Skissen visar en möjlig VD-arbetsyta. Den är en fristående, interaktiv
designreferens utan backend, modellanrop eller sparade styrinställningar.
Kostnader, trender, uppdrag och ledningsfrågor är syntetiska exempel.
Konsolidering visas som ej beräknad eftersom dess modellunderlag ännu saknas.

## Navigation och innehåll

- **Överblick:** bolagsläge, agentekonomi, viktigaste teamleveranser och frågor
  om inriktningen. Inga enskilda försäkrade eller handläggarärenden.
- **Team & kostnader:** teamens samlade arbete och en kostnadsfördelning med
  länkbar uppdragsnivå i kommande implementation.
- **Fråga bolaget:** fråga med period/underlag, föreslagen routing via teamledare
  samt källbundet svar. Skissen visar endast ett märkt exempelsvar.
- **Styrning:** global leverantörspolicy med synlig reservpolicy och
  förhandsgranskning av berörda roller. Knappar påverkar bara skissen.

Den interaktiva referensen finns i [operator-central.html](operator-central.html).
Öppna fragmentet via Codex visualiseringsvy; filen är redigerbar skisskälla,
inte en produktionssida. Den har inga externa datakällor. På smala skärmar
flödar navigation och kolumner om. Tangentbord kan användas till alla val.

## Designavstämning

Nästa avstämning gäller informationshierarkin: om överblicken lyfter rätt
VD-frågor, om team/kostnader har rätt tyngd och om frågeingången är tillräckligt
framträdande. Färdiga måttdefinitioner, eskaleringströsklar och operatörens
styrmandat fastställs i OC-0; skissen avgör dem inte.

[Beslutsförslag A–X](../../02_system/operatörscentral_beslutsforslag.md)
godkändes 2026-10-26 genom B-038. Skissen förblir en visuell referens;
exempelvärden och interaktioner innebär inga implementerade funktioner.

Se [projektplanen](PROJEKTPLAN.md) och [arkitekturunderlaget](../../02_system/operatörscentral.md).

## Leveranskontroll 2026-10-25

- Fyra vyer kontrollerade vid 1100, 768, 390 och 320 pixlars webbläsarbredd:
  inget horisontellt överflöde. Desktop, mobil och mörkt tema granskade visuellt.
- Frågeexempel, beslutsunderlag, tangentbordsnavigation, leverantörsval,
  reservpolicy och teamundantag provade i webbläsaren. Ändrat val kräver ny
  förhandsgranskning. Återställning av visningsläge stänger inte en giltig förhandsgranskning.
- Inga JavaScript-körfel i den avslutande kontrollen; lokala dokumentlänkar
  och fragmentets format kontrollerade. Skissen har inga data-/modell-API-anrop.
- Skissen använder DM Sans när tillgängligt, annars systemets reservtypsnitt.
  Kontrollen gjordes med lokalt tillgängligt typsnitt och utan externa resursanrop.
- Ingen affärslogik, databas, modellkonfiguration eller körpolicy har ändrats.
