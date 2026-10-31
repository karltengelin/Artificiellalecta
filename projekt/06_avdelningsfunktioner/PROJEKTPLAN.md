# Projekt 6: Avdelningsfunktioner

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

Bygga gemensamma ekonomi-, värderings-, risk- och rapportunderlag för bolagets
verksamhet. Människor och agentteam ska kunna använda samma verifierade
beräkningar och underlag genom behöriga tjänster och teamytor.

Aktuariella funktioner omfattar garanti, pension, reserv/FTA och ALM inom
respektive beslutad grund. Ekonomifunktioner omfattar bokföring, avstämning,
likviditet och bokslut. Rapportunderlagen samordnas med projekt 2 och den
planerade rapporteringsfunktionen. Produktregler och tillämplighetsbedömningar
från projekt 4 återanvänds; nya värderingsgrunder måste fastställas separat.

## Status

🟡 Behov kartlagda; första kontraktsarbetet preciserat genom operatörens
godkända dokument- och prioriteringsuppdrag 2026-10-27.
Ekonomi-/FTA-motorer och körbara ekonomi-/rapporteringsfunktioner är inte byggda.
Aktuarieagentens befintliga profil och premieanalys hör till den tidigare
byggda grunden och innebär inte att dessa bredare funktioner är implementerade.

## Beroenden

- Delar av tolkningsarbetet överlappar projekt 4 (produktregelverk) – avstäm innan parallellt
  arbete påbörjas (jfr AGENTS.md §4.2)
- Projekt 1 äger berörda försäkringsoperationer och projekt 5 kassaflödes-/
  värderingsgränsen mot förvaltningen. Projekt 2 äger gemensamma analysmått;
  projekt 10 använder underlagen i central och teamytor.

## Befintlig grund i repot

- "Bolagets funktionsområden"-tabellen, `MASTER_CONTEXT.md` §4.
- [Aktuariell SIM-grund](../../01_domän/aktuariell_grund.md) och parameterregister.
- [Agentkarta](../../02_system/agentkarta.md), aktuarieprofil och avgränsad
  premieeffektanalys; ekonomi- och rapporteringsagenter är fortfarande planerade.
- [Processöversikt](../../01_domän/processer_översikt.md), V-10–12 och paket A/B.
- [Aktuarieteamet – utredning och planförslag](AKTUARIETEAM_PLAN.md) (2026-10-31, ej beslutat):
  arbetsår, FI-rapportering, FTA-analys, harness, arbetsyta och produktrapport, med
  [klickbar skiss](aktuarie-arbetsyta.html) och [beslutsförslag A0](AKTUARIETEAM_BESLUTSFORSLAG.md)
  (Alecta-modellen för FTA, godkänt som **B-042**).
- [Värderings- och förklaringskontrakt A1](VARDERINGSKONTRAKT.md) (fastställt 2026-10-31).

## Nästa kontraktsarbete att förbereda

### Första aktuariella värderingen och förklaringen av FTA

**Planeringsprioritet godkänd 2026-10-27. Metoden är beslutad i B-042 (Alecta-modellen);
kontraktet [VARDERINGSKONTRAKT.md](VARDERINGSKONTRAKT.md) är fastställt 2026-10-31. Motorn är inte byggd.** Ta fram ett värderings- och förklaringskontrakt som
kan ligga till grund för ett separat avgränsat bygguppdrag.

| Del av kontraktet | Vad som ska fastställas före motorbygget |
|---|---|
| Ändamål och ansvar | Vilken värdering rapporten avser, mottagare, aktuariellt ansvar, granskning och relation till ekonomi och rapportering |
| Omfattning | Värderingsdatum, försäkringspopulation, åtaganden/kassaflöden och vilka fall som ingår eller ännu saknas |
| Grund och metod | Beslutade antaganden, källor och versioner samt värderingsmetod. Produktens garantivärde `V_g`, kundkapital och FTA hålls isär |
| Data | Underlag om bestånd, pensionsplaner, historiska garantidelar och kassaflöden samt datakvalitet, källidentitet och beroenden till paket A/B |
| Kontroll | Oberoende kontrollfall, avstämning av ingående/utgående värden och hantering av saknade eller underkända data |
| Förklaring | Hur förändring mellan värderingstillfällen delas upp i identifierbara orsaker, vilka känsligheter som kan beräknas och vilka osäkerheter som kvarstår |
| Leverans | Versionerat beräkningsunderlag och granskad rapport med referenser som projekt 2 och centralen kan använda utan parallell värderingsmotor |

Aktuarie samordnar värderingskontraktet med ekonomi, kapital och rapportering
där deras underlag behövs. Det är klart som kontraktsleverans när omfattning,
metodval, datakrav, beroenden och acceptansfall är uttryckliga och kvarstående
ställningstaganden är utpekade. Först därefter kan motorbygget avgränsas.
Den dokumenterade SIM-grunden får inte automatiskt behandlas som FTA-grund.

### Ekonomins del av premie-/betalningsflödet

Nästa samordnade verksamhetsuppdrag är paket A tillsammans med projekt 1/4
och gränssnittet mot projekt 5. Projekt 6 preciserar ekonomiskt underlag och
avstämningspunkter: premie/faktura, fordran, mottagen betalning, rättelse,
delbetalning, okänd betalning och underlag till kapital/garanti.

Kontraktet ska ange ägare för varje steg, referenser mellan ekonomiska och
försäkringsmässiga händelser, vilka belopp/datum som ska stämma och hur
dubbletter eller okänt utfall hanteras. En betalstatus i premietabellen är
inte en bokförings- eller bankavstämningsfunktion. Första kodleveransen
avgränsas gemensamt före start; detta dokument startar ingen implementation.

## Öppna designfrågor

### Konkretisering för månadssimulering

Behoven är samlade i [processöversikten](../../01_domän/processer_översikt.md).
De här delarna ska avgränsas till bygguppdrag innan en full pensionsmånad kan verifieras:

- **V-10, ekonomi:** bokföring och avstämningsunderlag för premier, placeringar, pension,
  avgifter, skatt och eget kapital; ingående balans och månadsbokslut.
- **V-11, aktuarie/risk:** garanti-/reserv-/FTA-/ALM- och finansieringskontroller med
  verifierade motorer. Den dokumenterade SIM-grunden är metodunderlag, inte färdig beräkningskod.
- **V-12, rapportering:** välj tillsammans med projekt 2 första interna månadsrapporten,
  därefter tillämpliga skatte-/tillsyns-/partsrapporter med bestämd mottagare och period.
- **Paket B och S-04:** föreslagen samordning med projekt 1 och 5 för pensions-/månadsavräkning
  och ett ekonomiskt avstämt startbestånd. Byggansvaret behöver fastställas vid designstart.

Målbilden ovan innebär inga nya agentmandat, rapporteringskrav eller flytt av beslutat projektscope.

**Leverans till VD-överblicken (2026-10-25):** projekt 6:s verifierade ekonomi-,
värderings- och riskunderlag ska genom projekt 2:s gemensamma mått försörja
[operatörscentralen](../10_operatörscentral/PROJEKTPLAN.md). Konsolidering kräver
en definierad fördelnings-/återbäringsmodell och rätt värderingsunderlag. Projekt 10
visar saknade mått som ej beräknade och bygger inga parallella domänmotorer.

### Organisation

- Använd B-026:s befintliga sju team och avgränsa bygguppdrag inom nuvarande
  projektstruktur. Granskningen innebär inget nytt delprojekt per avdelning.
- Precisera arbetsdelning, granskning och kontrollansvar i de valda kontrakten,
  inklusive gränsen mellan aktuariellt arbete, ekonomi, rapportering och internrevision.
