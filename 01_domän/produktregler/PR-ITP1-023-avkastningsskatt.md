# PR-ITP1-023 – avkastningsskattens kundbelastning
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Skattens schablonram; egen kundbelastningsmetod.
**Källor:** K-AVPL, K-SKV-SLR i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-007](../../04_regulatoriskt/tolkningar/T-ITP1-007-skatt-och-betalning.md).
**Villkor:** [§5 i v2.0](../försäkringsvillkor.md).

## Grund och regel

AvPL 3 a/3 d/9 §§ skiljer kapitalunderlag, schablonränta och skattesats.
Bolaget är skattebärare. Vi väljer följande kapitalbelastning i villkoren:
s_y = 0,15 × max(genomsnittlig SLR föregående år, 0,005).
T_i = round_half_up(C_i_öppning × s_y/12, 2), med årsparameter från registret.

2026 blir s=0,00354, alltså 0,354 % av kapitalbasen per år.
Det är inte 15 % av faktisk avkastning eller 15 % av kundens kapital.
Avgift och skatt är separata kapitalposter, även under paus/fribrev.
Om tillgängligt kapital efter avgift inte räcker begränsas kundbelastningen
till detta kapital; bolaget bär skillnaden, ingen negativ C eller kundskuld.

Bolagets faktiska skatt beräknas på dess lagliga årsunderlag, som inte
är summan av våra skiftande månadsbaser. Skillnaden mellan verklig skatt
och vald kundbelastning tillhör bolagets resultat, inte en automatisk
retroaktiv kunddebitering. Verklig skattedeklaration hör till ekonomiprojektet.

Ingen avkastningsskatt dras igen från en leverans märkt efter denna skatt;
sådan avkastningsdefinition ska först normaliseras till PR-021.
Kundens preliminära inkomstskatt på pension är en annan skatt, PR-026.

## Kontrollfall

C0=100 000 år 2026: T=29,50 kr/månad.
Faktisk r=−5 %: skattebelastningen kvarstår enligt kapitalbasen.
Saknad SLR/årsparameter: utredning, inte föregående års sats automatiskt.
