# PR-ITP1-032 – giltighet och övergång
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Historiska källor; egna övergångs-/mockval.
**Källor:** K-ITP-HIST, K-IBB-HIST i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-009](../../04_regulatoriskt/tolkningar/T-ITP1-009-simulering-och-historik.md).
**Villkor:** [§16 i v2.0](../försäkringsvillkor.md).

## Regel

Dokumentpaketet har föreslagen framtida simuleringsdag 2026-11-01.
Dokumentet självt, en git-commit eller en kodrelease inför inte
automatiskt nya villkor. [Paketförslaget](../../projekt/04_produktregelverk/PAKET_BESLUTSFORSLAG.md)
anger det samlade införandebeslutet; ingen ny beslutsloggspost skrivs utan OK.

Nya händelser efter införande använder paketets då giltiga regler.
Historiska premieår 2023–2026 använder rätt års IBB och trappa.
Frivillig 66–67-gren används från 2026. Uttagsflexibilitet/IL:s
2025-/2026-ändringar dateras separat i källregistret.
Inga befintliga utbetalningar räknas om genom filändring.

För redan befintlig mockdata väljs två explicit åtskilda importutfall:
- Full källhistorik: behåll faktiskt beslutad plan, belopp, historisk
  tariff och garantidelar; nya val prövas framåt.
- Rent demonstrationsbestånd utan verkliga beslut/garantihistorik:
  operatören kan besluta att **omgenerera** hela scenariot från 2023
  med SIM-HIST-2023-01, sedan gå över till aktuellt paket 2026-11.
  Märk alla konstruerade garantidelar som syntetiska och bevara ursprung/
  rekonstruktion i körningsunderlaget. Ingen tyst migration.

Saknad garanti-/kapitalhistorik i verklig/importerad försäkring kräver
rekonstruering eller avskild ej automatiserbar post; dagens C är inte
ett bevis på intjänad garanti. Källårets tariff och modellår blandas inte.

## Kontrollfall

2024-lönerättelse 2026: 2024-års trappa, inte dagens gräns.
2026-SIM-statistik i omgenererad 2023-demo: tillåtet markerat modellval,
inte ett påstående om dåtidens regler/tariff. Gamla 63-/70-årsantaganden
får inte styra nya beslut.
