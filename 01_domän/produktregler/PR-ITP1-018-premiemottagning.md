# PR-ITP1-018 – premiemottagning, netto och värdedatum
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** B-021/B-027; egna mottagnings- och värderingsval.
**Källor:** K-ITP-NETTO i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-006](../../04_regulatoriskt/tolkningar/T-ITP1-006-premie-lon-och-anslutning.md).
**Villkor:** [§4/7 i v2.0](../försäkringsvillkor.md).

## Regel

Matcha varje bank-/simuleringsöverföring med unik betalningsreferens,
betalare, faktura/premieperiod och belopp. Fel person/okänt avtal eller
överskott utan godkänd premie ligger på avstämningskonto, ger ingen
kundgaranti och återbetalas endast till verifierad ursprunglig betalare
efter operatörsbeslut. Samma referens får inte dubbelbokas.

B-021:s interna simulering har ingen valcentral: ordinarie mottagen
bruttopremie = nettopremie; ingen schablonmässig Collectumavgift.
Vid dokumenterad verklig import används faktiskt förmedlat netto och
identifierat externt avdrag separat, inte ett andra internt avdrag.
Netto ska vara minst noll och avdrag förklarade.

Delbetalning till identifierad faktura fördelas proportionellt mellan
dess positiva öppna premierader med största bråkrest, sedan enligt
PR-015. Krediter avräknas separat. Endast mottaget netto kapitaliseras.
Betalningsdag sparas; i vår månadsmodell är värdering mottagningsmånadens
slut och avkastning börjar nästa månad. Sen betalning ger ingen
retroaktiv simulerad marknadsavkastning.

Ny garanti skapas i mottagningsmånadens tariff, med hänvisning även till
ursprunglig premieperiod. Källans period styr trappan; mottagning styr
tariffen. Under pågående uttag tillförs separat ännu inte startad del.
Om sådan saknas skapas ny försäkring enligt B-022 och PR-025; en ändlig
pågående plan med få månader kvar får inte svälja nytt intjänande.

## Kontrollfall

2025-premie mottagen november 2026: IBB 2025, tariff SIM-G-2026-01.
Förklarad import 1 000 brutto/994,50 netto: garanti på 994,50.
Intern 1 000-inbetalning: garanti på 1 000, ingen extern avgift.
