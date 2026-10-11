# PR-ITP1-002 – tidigarelagt första uttag
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Avtalsram; eget månadsutbud och pensioneringsvillkor.
**Källor:** K-ITP-AVTAL-2026, K-IL-UTTAG-2026, K-ALECTA-UTTAG-2026 i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
**Villkor:** [§8 i v2.0](../försäkringsvillkor.md).

## Grund och indata

ITP 7.5 ger 55-årsramen. Vår exakta månad och pensioneringskontroll är
bolagsval med jämförelseunderlag i [T-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
Pröva varje ännu inte startad uttagsdel, födelsedatum, begäransfrist,
arbetsomfattning, tillgänglighet för arbete och externa ersättningsandelar.

## Regel

1. Första rätt tidigast månaden **efter** 55-årsmånaden och före
   66-årsmånaden i denna gren. Den valda månadskonventionen är försiktigare
   än en rätt som börjar mitt i 55-årsmånaden.
2. Helt uttag före 66 förutsätter pensioneringsintyg: arbete och avsikt
   att arbeta mindre än 8 timmar/vecka vardera, samt tillgänglighet för
   arbete mindre än 8 timmar/vecka. Exakt 8 uppfyller inte villkoret.
   Sökta eller mottagna sjuk-/aktivitets-/arbetsskadeersättningar och
   motsvarande ITP-sjukpension ska inte samtidigt ge helt tidigt uttag.
3. Deluttag följer PR-024:s proportionella prövning. Diagnos behövs inte;
   det är ersättningsandel och arbete som prövas, inte en sjukförsäkring.
4. Intyg gäller planerad start. Ändrat arbete före start kräver ny
   prövning. Efter giltig första start införs inget eget återkrav enbart
   för att kunden senare återgår till arbete; en ny ytterligare uttagsdel
   före 66 prövas på nytt.
5. Välj livsvarigt eller minst 60 betalningsmånader. G/B omräknas enligt
   PR-008/009. Saknad finansiering hanteras enligt PR-028.

## Utfall och kontrollfall

Född 1971-10-15: november 2026 är första möjliga månad; oktober avslås.
7 timmar arbete/tillgänglighet och inga konkurrerande ersättningar kan
ge helt uttag; 8 timmar ger deluttag/prövning, inte automatiskt helt.
Saknat intyg ger komplettering utan att tidigare intjänad pension ändras.
