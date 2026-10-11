# PR-ITP1-006 – tidsbegränsad utbetalning
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Avtalets minimitid; eget tidsutbud.
**Källor:** K-ITP-AVTAL-2026, K-IL-UTTAG-2026 i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-003](../../04_regulatoriskt/tolkningar/T-ITP1-003-tidsbegransad-utbetalning.md).
**Villkor:** [§9 i v2.0](../försäkringsvillkor.md).

## Regel och grund

ITP 7.5 ger minst fem års utbetalning. I produkten väljs ett helt antal
betalningsmånader N ≥ 60 före första start. Ingen egen övre gräns eller
lista av femårsintervall. N avser rättigheter, inte antalet lyckade
banköverföringar. Dödsfall kan avsluta tidigare.

Delen klassificeras som tidsbegränsad ålderspension enligt allmän
pensionsplan, IL 58 kap. 11 b/20 §§, efter verifierad ITP-anslutning.
Denna gren kan ha rörligt omräknat belopp inom ITP-planen enligt PR-009.
En avtalad ny kortare period kan väljas före första start om den fortsatt
är minst 60; efter start är endast förlängning tillåten i vårt utbud.

Skapa plan med originalstart, N, förbrukade/kvarvarande rättigheter,
pausperioder och härledd slutmånad. Varje månad med rätt förbrukas en gång
även om betalning senare misslyckas. Efter sista rätt sker PR-027:s
slutavräkning; tidigare obetalda anspråk bevaras. Ingen extra utbetalning
utanför planen skapas för att kapital råkar finnas kvar.

## Kontrollfall

Start november 2026, N=60: sista månad oktober 2031.
Paus november 2027–januari 2028 efter 12 rättigheter: återstart februari
2028 och sista månad januari 2032. N=59 avslås före start. N=61 tillåts.
