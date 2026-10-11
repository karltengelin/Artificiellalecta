# PR-ITP1-031 – personuppgifter, behörighet och beslut
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Dataskyddsram; B-006/B-016 och egna processkrav.
**Källor:** K-GDPR i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-010](../../04_regulatoriskt/tolkningar/T-ITP1-010-tvarregler.md).
**Villkor:** [§14 i v2.0](../försäkringsvillkor.md).

## Regel och grund

GDPR artiklarna 5/6/13–16/22/32 och B-006/B-016.
Behandla endast uppgifter som behövs för angiven pensions-/avtalsuppgift.
Avtal och rättslig förpliktelse väljs per behandling; allmänt samtycke
används inte som universell grund för pensionens administration.

Verifiera rätt person och fullmakt före uttagsval/kontoändring.
Arbetsgivare får se egna löne-/premieuppgifter, inte kundens alla andra
arbetsgivares pension eller bankval. Ett ombud får endast fullmaktens
omfattning. Utbetalning till tredje man tillåts inte utan särskild rättslig
grund. Kön får inte påverka tariffer; använd ingen diagnos när ersättnings-
andel/intyg räcker. Hälsouppgift som ändå behövs kräver artikel 9-grund.

Dokumentera personuppgiftsansvar, ändamål, mottagare/biträden,
lagrings-/gallringsplan och rättigheter i informationsbeskedet.
Bolaget väljer en årlig dokumenterad behovsprövning och gallring av
onödiga råbilagor när ärendet avslutats. Avtal, ekonomiska rättigheter
och nödvändigt rättelseunderlag bevaras medan skyldighet/anspråk kvarstår.
Ingen generell evig lagring eller automatiskt radering efter en enda
påhittad tidsgräns; lagkrav/anspråk anges per uppgiftskategori.

Språkmodell får läsa behörigt minimerat underlag och föreslå beslut.
Aktuariella beräkningar sker deterministiskt enligt låst grund.
Avslag, negativ rättelse, tvist, återkrav, misstänkt dödsfall och
regelavvikelse avgörs av behörig människa som kan ändra förslaget.
Kunden kan begära mänsklig granskning och rättelse. Operatörens
godkännande loggas före materiell verkställighet i simuleringen.

## Kontrollfall

AI bedömer att intyg saknas: kompletteringsförslag, ingen borttagen garanti.
Kontoändring utan verifierad fullmakt: stoppat bankuppdrag, rätten kvarstår.
