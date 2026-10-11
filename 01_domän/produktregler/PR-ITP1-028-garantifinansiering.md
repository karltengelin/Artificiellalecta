# PR-ITP1-028 – garantifinansiering och kapitalbrist
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Egen simuleringsfinansiering, skild från regulatorisk solvens.
**Källor:** K-LTF, K-FFFS-AKTUARIE i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-004](../../04_regulatoriskt/tolkningar/T-ITP1-004-garanti-och-aktuariell-grund.md).
**Villkor:** [§6/11 i v2.0](../försäkringsvillkor.md).

## Regel

Kundkapital, betalningsskulder, arvsvinstpool och bolagets egna fria
tillgångar är separata. Ett garanterat/låst månadsbelopp får aldrig
betalas genom att skapa pengar eller debitera annan kunds garanti.

Varje simuleringsscenario måste före start ha en dokumenterad faktiskt
bokförd kapitalinsättning från den simulerade ägaren till bolagets konto.
Initialt tillgängligt bolagskapital väljs till minst:
```text
E_min = summa_i max(0,V_stress_i − C_i) + 12 × summa_i M_i_närmaste_månad
```
V_stress värderar respektive låsta garanti på dess grund men med ytterligare
20 % lägre dödsrisk till och med ålder 100. Räkna därefter om svansens
ankare med den lägre q100 och samma intensitetsökning/tak som i den
aktuariella grunden. Använd noll nettoränta och full oändlig svans.
V_stress per del räknas som summan G_j × A_j_stress plus
skillnaden mellan utbetalningsbart öresgolv och summan G_j gånger
den största A_j_stress för delens historiska grunder. Om ett bindande
livsvarigt beloppsgolv är högre används minst detta golv gånger största
A_j_stress. Detta är en medvetet försiktig buffertvärdering.
För ännu inte startad del
värderas framtida garanterad plan; M i likviditetsdelen avser endast nästa
månads faktiskt pågående pension. Detta är vald **simuleringsbuffert**,
inte LTF:s kapitalkrav, solvensberäkning eller bevis på långsiktig bärkraft.

Före varje månad: omvärdera stressgap och 12 månaders likviditetsbuffert.
Bruten buffertgräns stoppar nya produktutfästelser och ger kapitalärende.
Intjänad pension försvinner inte. Faktiskt betalningsstöd per del är
K_i = max(0, uppkommen bruttorätt − tillgängligt C_i efter kostnader).
Överför K från bolagskonto, debitera motsvarande konto och skuldför pension.
Stöd skapar ingen ny garanti eller schablonarvsvinst.

Saknat bolagskapital: bevara rätt som ej finansierat anspråk, markera
simuleringskörning ekonomiskt blockerad och eskalera. Ingen lyckad
bankbetalning rapporteras. Ytterligare kapital kräver dokumenterad
finansieringshändelse, inte tyst nollställning av underskott.
Vid överskott får inget återtas från kundens intjänade garanti i v1.0.

## Kontrollfall

C=80, giltig rätt=100, bolagskonto≥20: stöd 20, pension 100.
Samma C men bolagskonto=0: rätt 100 finns kvar, betalning ej finansierad.
Frigjort V_g vid dödsfall: ingen ny tillgång bokas på bolags-/poolkontot.
