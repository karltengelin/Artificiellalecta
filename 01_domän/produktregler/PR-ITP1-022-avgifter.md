# PR-ITP1-022 – kapitalavgift och övriga avgifter
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** B-021; egen öppningsbas och debiteringsordning.
**Källor:** K-LTF i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-004](../../04_regulatoriskt/tolkningar/T-ITP1-004-garanti-och-aktuariell-grund.md).
**Villkor:** [§5 i v2.0](../försäkringsvillkor.md).

## Regel

B-021: kapitalavgift 0,20 % nominellt per år, månadsvis.
F_i = round_half_up(C_i_öppning × 0,002/12, 2).
Avgiften gäller sparande, fribrev, uppskov, paus och utbetalning.
Nya premier vid månadsslut belastas första gången nästa månad.
Ett deluttag delar öppningsbasen, så samma kapital inte avgiftsbelastas dubbelt.

Avgiften tas efter avkastning före skatt/pensionsskuld enligt PR-020.
Om tillgängligt C då understiger beräknad avgift tas endast tillgängligt
belopp; resten avstås av bolaget, blir inte en kundskuld.
Bolagets avgiftsintäkt och kundens kapitalminskning avstäms mot varandra.

Fast avgift, premieavgift, in-/utbetalningsavgift, särskild pausavgift,
förlängningsavgift och riskpremie är 0. Direkta placeringskostnader ingår
i PR-021:s levererade avkastning och får inte debiteras igen.
Avgift får inte sänka redan intjänad garanti.
Ändring av avgift kräver PR-030:s ändrings-/informationsprövning,
inte bara ett nytt tal i parameterregistret.

## Kontrollfall

C0=100 000: F=16,67 kr. C0=0: F=0.
C0=100 000, r=−100 %: tillgängligt C=0; avgift avstås, ingen negativ C.
