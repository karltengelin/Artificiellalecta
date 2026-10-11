# PR-ITP1-021 – faktisk avkastning och överskott
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Egen direktfördelning av faktisk placeringsavkastning.
**Källor:** K-LTF i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-004](../../04_regulatoriskt/tolkningar/T-ITP1-004-garanti-och-aktuariell-grund.md).
**Villkor:** [§5 i v2.0](../försäkringsvillkor.md).

## Regel

V1.0 väljer direkt månadsfördelning av faktiskt resultat i produktens
kollektiva kapitalförvaltning; ingen återbäringsränta eller dold buffert.
Kapitalförvaltningen levererar verifierad tidsviktad månadsavkastning r
**efter dess direkta placeringskostnader, före vår 0,20 %-avgift och
avkastningsskattebelastning**. Definitionen måste finnas i leveransen.

Tillför C_i_öppning × r till varje exponerad del; inga månadsnya premier
ingår i basen. Resultatet i ören allokeras så att summan motsvarar
kollektivets fastställda resultat. Förluster fördelas med samma metod
på negativa belopps magnitud; C får inte bli negativt, r ≥ −1.
Saknad/oklar r blockerar månadens värdering, inte ersätts med 3 % prognos.
En uttrycklig avkastningsleverans 0 är tillåten.

Bolagets egna tillgångar och kundkollektivet särredovisas. Kundkollektivets
resultat får inte innehålla arvsvinstpoolens internöverföring, premier,
pensionsbetalning, kapitalstöd eller dubbla avgifter. Rörligt överskott
är del av C och blir pension vid PR-009:s omräkning, utan ny garantidel.
Ingen individuell rätt till en viss framtida avkastning utfästs.

## Kontrollfall

Två delar C0=1 000/2 000 och r=−10 %: −100/−200.
Kundprognos 3 %, faktisk leverans 1 %: bokför 1 %.
Pågående uttag och paus får samma avkastningsprincip som sparande.
