# PR-ITP1-013 – premieperioder, anställning och fribrev
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Avtalsram; separat premie-/pensionsstatus.
**Källor:** K-ITP-AVTAL-2026, K-ITP-FIL i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-006](../../04_regulatoriskt/tolkningar/T-ITP1-006-premie-lon-och-anslutning.md).
**Villkor:** [§3/7 i v2.0](../försäkringsvillkor.md).

## Regel

Ordinarie intjänande från 25-årsmånaden till och med månaden före 66 år,
med giltig ITP1-tillhörighet. Lön utbetald under en pågående anställning
eller under dess avslutsmånad ingår utan dagproportionering.
Flera anställningsrader hos samma arbetsgivare sammanförs i månadsunderlaget.

Efter avslut/tjänstledighetsavanmälan kan pensionsmedförande slutlön eller
bonus fortfarande rapporteras för den verkliga utbetalningsmånaden.
Verifiera koppling till den avslutade anställningen och premieåldern.
Collectums filspecifikation har en gräns på tre efterföljande
lönerapporteringar; **det är inte en tre månaders produktmässig bortfallsregel**.
I simuleringen hanteras en fjärde/särskild rapport manuellt med underlag,
inte som noll lön eller upphörd intjänad rätt.

Sjukdom/föräldraledighet ändrar inte automatiskt anställningens slutdatum.
Faktisk lön kan vara noll. Extern premiebefrielsepremie bokas separat
enligt PR-016; bolaget beräknar inget sjuk-/föräldraförsäkringsanspråk.
Vid vanlig tjänstledighet utan lön/intygad extern premie uppkommer ingen
ny premie; redan intjänad garanti och kapital finns kvar.

När ny löpande premie upphör är förmånen premiefri (fribrev). Det kan
samexistera med pågående eller pausad pension. Uppskov och paus är inte
synonymer för fribrev. Återanställning aktiverar ett nytt giltigt
premieintervall; samma lön får inte faktureras två gånger.

## Kontrollfall

Född 1998-08-15: augusti 2023 är första ordinarie premiemånad.
66-årsmånaden: noll ordinarie premie; frivillig fortsättning prövas i PR-016.
Bonus efter avslut: pröva faktisk utbetalningsmånad, inte avslutsmånad.
Dödsfall: rapporten bevaras men ekonomisk avräkning görs i PR-010/019.
