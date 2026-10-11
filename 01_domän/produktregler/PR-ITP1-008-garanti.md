# PR-ITP1-008 – intjänad garanti
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** B-027; egen specificerad SIM-tariff.
**Källor:** K-LTF, K-FFFS-AKTUARIE, K-SCB-LIVSLANGD i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-004](../../04_regulatoriskt/tolkningar/T-ITP1-004-garanti-och-aktuariell-grund.md).
**Villkor:** [§6 i v2.0](../försäkringsvillkor.md).

## Regel och grund

B-027: 100 % av mottagen nettopremie, 0 % effektiv nettoränta och ingen
automatisk garantiförstärkning. [Aktuariell grund](../aktuariell_grund.md)
specificerar vald SIM-tariff. Den är vår modell, inte en allmän ITP-tariff.

Varje nettopremie skapar en identifierad garantidel med P_j, värdedatum,
referensplan, grundversion och G_j = P_j/A_gj. Premiefordran före mottagning
skapar ingen garantidel. Mottagen extern premiebefrielsepremie behandlas
som pensionspremie utan att bolaget meddelar en premiebefrielseförsäkring.

Aktuell garanti är summan av delarnas belopp för samma uttagsplan.
En ändrad grund gäller framtida premie, inte redan intjänade delar.
Deluttag delar proportionellt varje garantidel. Annan planändring
använder V_j = G_j × A_gj(gammal kvarvarande plan), sedan
G_j_ny = V_j/A_gj(ny kvarvarande plan) på **samma** historiska grund.

Paus/uppskov/förlängning kan ändra månadsbelopp genom planen. Marknadsfall,
avgift, skatt eller utebliven senare arbetsgivarpremie får inte radera
garantin för mottagen premie. En garanti är ett livsberoende pensionslöfte,
inte återbetalning av premie till kunden eller dödsboet.
Rättelse av felaktig premie följer PR-019; dödsfall PR-010.

## Kontrollfall

Syntetiskt A=60, P=1 000: G=16,666666…; det är inte den verkliga SIM-faktorn.
Ny tariff påverkar inte detta intjänande. Arvsvinst/avkastning skapar
rörligt kapital men ingen ytterligare garanti. Saknad historisk grund
ger rekonstrueringsärende, aldrig tyst ersättning med aktuell grund.
