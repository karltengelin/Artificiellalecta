# Samordning vid integration – delade programdokument

> **Datum:** 2026-10-11 | Förberedda följdändringar, inga nya sakbeslut.
> Produktpaketet är färdigt i sin hemvist. Detta underlag undviker samtidig redigering av delade dokument.

## Varför separat

AGENTS §4.3 säger: ”Om en annan agent samtidigt har ett öppet uppdrag som
rör samma område: redigera inte filen direkt – lägg föreslagna ändringar
i din slutrapport till operatören istället.”

Aktiva worktrees och senare main innehåller parallellt arbete i
MASTER_CONTEXT/ATT_GORA/BESLUTSLOGG. Den lokala produktbranchen har därför
inte skrivit i dem. Vid integration läggs enbart nedanstående produktstatus
in på senaste main; ingen agents tjänstelager-/AI-planering ersätts.
Kända gamla ”modellutkast/kalibrering återstår”-formuleringar är därmed
flaggade och rättelsen färdigformulerad i samma leveransgrupp.

## Föreslagen uppdatering i MASTER_CONTEXT

Garantistyckets sista del:

> Produktinriktningen är beslutad i B-027. Dokumentpaket PR-ITP1 v1.0
> med försäkringsvillkor v2.0 och valda SIM-grunder är färdigställt.
> Samlat införande och kodbygge återstår separat; professionell
> tariff-/bestånds- och solvensvalidering krävs före verklig verksamhet.
> Se `01_domän/produktregler/README.md` och `01_domän/aktuariell_grund.md`.

Status för delprojekt 4: **Dokumentunderlag klart; införande/bygge separat**.
Mappöversikten preciseras med produktregler/ och parametrar/ under 01_domän
samt källregister/tolkningar under 04_regulatoriskt. ”Modellutkast” vid
aktuariell grund ersätts med ”specificerad SIM-modell; verklig validering separat”.

## Föreslagen uppdatering i ATT_GORA

Ersätt den relevanta regulatoriska raden med:

- [x] **2026-10-11 Bygga ut produktnära 04_regulatoriskt** – källregister,
  tolkningar och underlag per regelverk för ITP, LTF, FFFS, FAL, skatt,
  GDPR, DORA, distribution, SFDR, AI och AML; företagets fullständiga
  policies/rapportering följer egna verksamhetsprojekt.

Ersätt aktuell aktuariell dokumentationsrad med:

- [x] **2026-10-11 Dokumentera aktuariell SIM-grund** – låst SCB-tabell 2025,
  unisex, förbättring/marginal, oändlig svans, garantidelar, annuiteter,
  arvsvinst och bolagsfinansiering. Valda antaganden och räkneexempel finns.
  Professionell verklig tariffvalidering och införande är separata aktiviteter.

Lägg till färdig dokumentleverans:

- [x] **2026-10-11 Delprojekt 4: sammanhängande produktpaket** –
  PR-ITP1 v1.0 (34 regler), villkor v2.0, tio tolkningar och leveranskontroll.
  Regelkod, migrationer och automatiserade regeltester flyttas enligt
  operatörens uppdrag till en annan session.

Historiska slutförda Fas 1-rader ska behålla sitt dåtida innehåll, men vid
behov få länk till den nya preciseringen. Gamla arbeten är inte omskrivna
som om de redan implementerade alla 34 reglerna.

## Beslutslogg och integration

[Paketförslaget](PAKET_BESLUTSFORSLAG.md) är färdig text för ett eventuellt
nytt beslut efter operatörens godkännande. Inget B-nummer är reserverat,
ingen loggpost har lagts till. B-027 ändras inte i efterhand.

Före merge ska produktbranchen synkas med senaste main och relevanta
dokumentkontroller köras igen. Merge kräver uttryckligt OK för just denna
leverans; ett äldre godkännande gäller inte automatiskt det nya paketet.
