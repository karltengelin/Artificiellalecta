# PR-ITP1-011 – faktisk arvsvinstpool
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Eget kollektiv och faktisk riskfördelning.
**Källor:** K-SCB-LIVSLANGD, K-DODSFALL-ALECTA i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-005](../../04_regulatoriskt/tolkningar/T-ITP1-005-dodsfall-och-arvsvinster.md).
**Villkor:** [§12 i v2.0](../försäkringsvillkor.md).

## Regel

Ett kollektiv: all vår traditionella ITP1 ålderspension utan återbetalnings-
skydd. Ett gemensamt poolkonto får endast faktiskt kapital från PR-010.
Ingen schablon eller frigjord bokförd skuld ökar poolen.

Fördela månadsvis efter dödsfallsavräkning till delar som har ingått hela
månaden, är verifierat levande vid slutet och inte slutavräknade. Sparande,
fribrev, uppskov, paus och pågående pension deltar. Medlemskap följer hela
försäkringen från anslutning; intern delning får inte återställa medlemsdatum.
Vikten använder månadsbörjans kapital, före nya premier/avgifter/uttag:
```text
E_i = C_i_öppning × q_i_månad/(1−q_i_månad)
H_i = R_pool × E_i/summa(E)
```
Använd aktuell SIM-R, samma unisexmodell för alla; historisk garantigrund
styr inte denna aktuella riskfördelning. Efter delning används de
proportionella öppningsbaserna utan dubblering. Avlidna under månaden
får ingen tilldelning. Ny medlem under månaden får först nästa hela månad.

Dela i hela ören med största bråkrest och stabilt del-ID vid lika rest.
Summan ska exakt motsvara poolens fördelade belopp. Pool=0 ger noll;
inga mottagare, E=0 eller okänd risk ger kvarstående pool och ärende,
inte lika-fördelning. H ökar C, inte G. Ingen andra arvsvinst tillförs
för annuitetsfaktorns dödlighet.

Varje körning har unik månad/version och full avräkning. Sena dödsfalls-
rättelser följer PR-019: bolaget återställer giltiga kundrättigheter,
inte negativ oannonserad tilldelning till oskyldiga mottagare.
Återkrav blir poolmedel först när faktiskt betalt.

## Kontrollfall

Pool 90, samma q, kapital 1 000/2 000: 30/60.
Pool 0,02, tre lika vikter: 0,01/0,01/0,00 efter ID-ordning.
Delning av 3 000 till 1 000/2 000 ger samma samlade vikt före öresavrundning.
