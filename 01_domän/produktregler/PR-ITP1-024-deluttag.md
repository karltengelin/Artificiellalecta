# PR-ITP1-024 – deluttag och separata uttagsdelar
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Eget delutbud och pensioneringsprövning.
**Källor:** K-ITP-AVTAL-2026, K-ALECTA-UTTAG-2026 i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md).
**Villkor:** [§8 i v2.0](../försäkringsvillkor.md).

## Regel

Kunden kan dela en ursprunglig försäkrings ålderspension i högst tre
uttagsdelar. Varje ny del är minst 10 % av kapitalet som delas vid detta
beslut och kvarvarande del minst 10 %, om den inte tas helt. Detta är
vårt produktutbud, inte universella ITP-gränser. Alla delar tillsammans
bevarar exakt kapital, garantidelar och ursprungsrelation.

Minimiandelen prövas som vald proportion även om C=0 men intjänad
G finns kvar. Saknas både kapital och pensionsrätt finns inget att dela.
Spara varje dels andel av ursprunglig rätt vid delningen; senare
marknadsutveckling får inte ändra denna andel i pensioneringskontrollen.

Dela C i ören med största bråkrest och G_j i hög precision proportionellt.
Varje del får egen start, form, N, paus och beloppsbeslut. En påbörjad del
får inte delas för att förkorta tiden, radera originalstart eller kringgå
skattegolv. En kvarvarande ännu inte startad del kan delas vidare inom
tregränsen. Intern delning skapar inte ny premie, extra arvsvinstvikt
eller nytt kollektivmedlemsdatum.

Före 66 gäller ytterligare prövning: dokumentera arbetstiden h0 före
första tidiga uttaget och nuvarande arbete h. Ackumulerad ursprunglig
uttagsandel får högst vara r = max(0,1−h/h0). Vid sjuk-/aktivitets-/
arbetsskadeersättning med andel s får den dessutom högst vara 1−s.
Även tillgänglighet för arbete ska stödja den uppgivna pensioneringen.
Varje ursprunglig försäkring ska klara gränsen; nya kontrakt får inte
användas för att kringgå helt-uttagsprövningen i PR-002.
Vid flera samtidiga ersättningar används verifierad sammanlagd omfattning,
högst 1, utan dubbelräkning; oklar överlappning är komplettering.
h0=0/okänt eller sökt ersättning utan fastställd andel kräver människoprövning,
inte division med noll eller antagande s=0.

Från 66 behövs ingen minskad arbetstid för deluttag. Återstående sparande
kan fortfarande ta emot premier; om alla tre delar startats går framtida
premie till ny försäkring enligt PR-025, inte en förbjuden fjärde del.

## Kontrollfall

40→20 timmar: högst 50 % tidigt uttag. Extern ersättning 75 %:
högst 25 %. Försök att starta 100 % före 66 medan arbete är 20 timmar:
avslag som helt uttag. C=100 000 delat 30/70 % bevarar 100 000 och G.
