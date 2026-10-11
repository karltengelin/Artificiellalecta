# PR-ITP1-016 – kompletterande och externa pensionspremier
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Avtalsram; eget erbjudande och verifierad betalare.
**Källor:** K-ITP-AVTAL-2026, K-ITP-KOMPLETTERING i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-006](../../04_regulatoriskt/tolkningar/T-ITP1-006-premie-lon-och-anslutning.md).
**Villkor:** [§3 i v2.0](../försäkringsvillkor.md).

## Regel och avgränsning

ITP 7.2 tillåter kompletteringar. Stöd fast månadsbelopp, engångsbelopp
och procentsats av uttryckligt avtalat underlag med giltighetsintervall.
Flex-/deltidspension och löneväxling använder signerad arbetsgivar-/
branschinstruktion. Ingen universell flexpensionssats eller automatiskt
påslag 5,8 % antas; kompensation måste vara avtalad och identifierad.

Före 66 kan komplettering läggas ovanpå ordinarie premie utan att
7,5-/30-IBB-trappan återanvänds som extra tak. För ålder under 25 accepteras
komplettering endast med uttryckligt verifierat tillämpligt avtal.
Från 2026 kan frivillig fortsatt premie 66–67 registreras med arbetsgivarens
beslut; paketet följer Collectums gren med minst PR-001:s nivå på giltig
lön och avslut senast månaden före 67. Detta är vår administrationsgräns,
inte ett påstående att ITP-avtalet förbjuder pension efter 67.
En annan 67+-lösning ingår inte i produktpaketet.

Extern pensionspremie vid sjukdom/föräldraledighet kan tas emot om
betalare, avtal, period och belopp är verifierade. Den ger samma
nettopremiegaranti som annan mottagen premie. Ingen automatisk
uppskattning från sjukdagar görs och ingen sådan riskpremie faktureras
av bolaget. Arbetsgivarpremie och extern premie behåller skilda ursprung
så att båda kan vara korrekta utan att samma överföring bokas dubbelt.

## Kontrollfall

Löneväxling 5 000 + avtalad extra kompensation 290: komplettering 5 290,
oberoende av ordinarie trappa på reducerad lön.
66 år, frivilligt beslut saknas: ingen fortsatt faktura.
Extern verifierad premiebefrielseinbetalning: ålderspensionspremie,
inte en ny sjukförsäkringsförmån.
