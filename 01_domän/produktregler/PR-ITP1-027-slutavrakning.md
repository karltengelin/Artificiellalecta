# PR-ITP1-027 – sista månadsrätt och avslut
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Egen slutavräkning inom verifierad ITP-ram.
**Källor:** K-ITP-AVTAL-2026, K-IL-UTTAG-2026 i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-003](../../04_regulatoriskt/tolkningar/T-ITP1-003-tidsbegransad-utbetalning.md).
**Villkor:** [§11 i v2.0](../försäkringsvillkor.md).

## Regel

Endast tidsbegränsad, verifierad ITP-plan i IL 58 kap. 11 b-grenen
slutavräknas efter dess sista avtalade månadsrätt. Livsvarig pension
slutar inte på grund av ålder, lågt C eller tariffens tabellslut.

På sista rättens månadsstängning, efter avkastning/avgift/skatt och före
pensionsdebit, beslutas sista **ordinarie planbetalning**:
M_sista = max(gällande beslutat månadsbelopp, C_tillgängligt).
Bolagsstöd täcker eventuell brist. Det sista beloppet kan därmed bli högre
än tidigare månad; denna kapitalavräkning är ett uttryckligt bolagsval
inom den tidsbegränsade planen, inte ett återköp eller extra uttag efteråt.
Den ökar aldrig antalet rättigheter. Kunden informeras inför sista året
om slutavräkning och kan i tid välja förlängning i stället.

Efter skuldföring är delens C=0, garantins framtida rättigheter noll
och delen avslutad. Sista månadens kvarvarande kapital omfattar bara
denna del; ny premie till annan ännu inte startad del påverkas inte.
Del med sista förbrukade rätt får ingen ny pooltilldelning samma månad.
Bruttoskulder, bankfel, tvist och skatteposter lever vidare efter avslut.
Avslut raderar inte personens andra försäkringar.

En rättelse som senare visar ytterligare kapital/rätt hanteras som
rättelse av den ursprungliga slutavräkningen med beslut/skatteprövning,
inte en ny kort pension eller en automatisk kontantöverföring.
Dödsfall före sista rätt hanteras i PR-010; då uppkommer ingen levande
kunds framtida slutavräkning.

## Kontrollfall

Sista rätt, beslutat M=100, C efter månadskostnader=140: slutbelopp 140.
M=100, C=80: bolagsstöd 20, skuld 100, C=0.
Banken avvisar sista beloppet: delen avslutas i rättighetshänseende,
men hela den obetalda skulden kvarstår.
