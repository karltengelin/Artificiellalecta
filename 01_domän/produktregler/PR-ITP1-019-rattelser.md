# PR-ITP1-019 – rättelser, premieåtertag och återkrav
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Egen rättelseprocess med rättslig prövning av negativ ändring.
**Källor:** K-FAL i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-008](../../04_regulatoriskt/tolkningar/T-ITP1-008-avtal-information-och-rattigheter.md).
**Villkor:** [§13 i v2.0](../försäkringsvillkor.md).

## Regel

All rättelse har ursprungshändelse, nytt underlag, orsak, behörigt beslut
och motposter. Bevara tidigare händelse. Ingen radering eller tyst
omvärdering av hela kundhistoriken.

1. **Lönerättelse:** räkna om just ursprunglig person/arbetsgivare/månad
   med dess IBB, satser och fördelning. Skillnad blir tillägg/kredit.
   En negativ lön som ny rapport accepteras inte.
2. **Ej mottagen premie:** rätta fordran/faktura; inget kundkapital finns
   att återta. Positiv tilläggspremie ger ny garanti först när mottagen.
3. **Återtag av mottagen felaktig premie:** verifiera återbetalningsrätt
   och exakt garantidel. Kvot f = återtagen ursprunglig nettopremie/P_j,
   0 < f ≤ kvarvarande okorrigerad andel. Återta f av den delens nuvarande
   garanti på historisk grund och dess spårade återstående kapital.
   Full kapitalhistorik återskapas med ursprungliga faktiska avkastningar,
   avgifter, skatt, delningar och uttag; historisk kapitalandel får inte
   ersättas med dagens premieandel av hela försäkringen.
4. Till ursprunglig betalare återbetalas högst rättsligt beslutat belopp.
   Skillnaden mellan detta och återtaget kundkapital är bolagets vinst/
   förlust eller separat återkrav; andra kunders garanti får inte finansiera
   felet. Berörd kund får rättelsebesked före negativ rättighetsändring.
   Redan konsumerade pensionsrätter återkrävs inte automatiskt.
5. **Fel pension/dödsdatum:** beräkna giltiga rättigheter och skillnaden.
   Underbetalning blir särskilt bruttoanspråk. Återkrav av överbetalning
   kräver rättslig/skattebedömning och människobeslut; ingen automatisk
   kvittning mot kommande pension eller negativ arvsvinst.
6. **Sen dödsfallsrättelse:** bolaget återställer korrekta anspråk/kapital
   med finansierad motpost. Redan korrekt informerade poolmottagare får
   inte tyst debiteras. Faktiskt återbetalt belopp kan därefter avräknas.

## Kontrollfall

IBB ändrad sedan 2024: 2024-korrigeringen behåller 2024-IBB.
Avkastningsförlust sedan felpremie: den rättade garantidelen får ändras
för premiefel, men ingen annan garantidel skrivs ned för marknadsförlust.
Saknad spårad kapitalandel: rekonstruera före verkställighet, inte gissa.
