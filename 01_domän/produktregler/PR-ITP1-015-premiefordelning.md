# PR-ITP1-015 – fördelning mellan flera försäkringar
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** B-022; egen allokerings- och öresmetod.
**Källor:** K-ITP-AVTAL-2026 i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-006](../../04_regulatoriskt/tolkningar/T-ITP1-006-premie-lon-och-anslutning.md).
**Villkor:** [§4 i v2.0](../försäkringsvillkor.md).

## Regel

Beräkna ordinarie total en gång på person/arbetsgivare/månad enligt PR-001.
B-022:s flera försäkringar får inte multiplicera trappan.
Anställningar hos andra arbetsgivare har egna underlag och premier.

Det finns en versionshanterad fördelningsinstruktion per betalningsström
med giltighet per premiemånad. Vikter ska vara icke-negativa, summan exakt
1 och mottagande förmåner tillhöra samma person och produkt.
Endast ännu inte startad premiedel är automatisk premiemottagare.

Om ingen instruktion finns väljs en uttryckligt angiven primär mottagare
med vikt 1. Finns varken sådan eller exakt en behörig mottagare: håll
beloppet på identifierat mellan-/avstämningskonto och begär val. Dela
aldrig lika av misstag. Ändrat val styr framtida premiemånader; retroaktiv
ändring är en rättelse, inte omfördelning av all gammal garanti.

Dela varje faktiskt mottagen nettopremie i hela ören med största bråkrest
och stabilt förmåns-ID vid lika rest. Delarna summerar exakt till netto.
Ordinarie och kompletterande premie kan ha olika styrda instruktioner.
En avvikelse i importerat verkligt val måste vara uttrycklig indata.

## Kontrollfall

P=10 708,13, vikter 60/40 %: 6 424,88 och 4 283,25.
Två försäkringar med samma L=80 000 ger tillsammans 10 708,13,
inte två fulla sådana premier. Mottagen delbetalning fördelas efter
samma instruktion och skapar garanti endast för faktiskt mottaget netto.
