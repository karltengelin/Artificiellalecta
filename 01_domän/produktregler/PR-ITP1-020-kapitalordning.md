# PR-ITP1-020 – kapitalvärde och månadsordning
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Egen månatlig kapital-/skuldmodell.
**Källor:** K-LTF, K-AVPL i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-004](../../04_regulatoriskt/tolkningar/T-ITP1-004-garanti-och-aktuariell-grund.md).
**Villkor:** [§4–6/11–12 i v2.0](../försäkringsvillkor.md).

## Regel

C består av bokförda premier, faktisk avkastning, arvsvinst och dokumenterat
bolagsstöd minus kapitalavgift, kundbelastad avkastningsskatt och **en gång**
uppkommen bruttopensionsskuld. Fordringar och prognoser är inte kapital.
En obetald pensionsrätt som redan skuldförts ligger separat, utanför C.

Månaden behandlas i denna ordning med samma värderingsversion:
1. Fastställ öppningskapital, levandestatus, kollektivmedlemskap, planändringar
   och månadens rätt enligt föregående månads värdering.
2. Tillför faktisk månadsavkastning på öppningskapital enligt PR-021.
3. Debitera kapitalavgift och avkastningsskattebelastning på öppningsbas
   enligt PR-022/023; håll dem skilda från kapitalförvaltningens nettokostnad.
4. Tillför månadens matchade nettopremier vid månadsslut och deras nya
   garantidelar på ännu inte startad del. De får ingen månadsavkastning nu.
5. Skuldför månadens pensionsrätt en gång inklusive eventuellt finansierat
   bolagsstöd enligt PR-028. Sista månaden beräknas enligt PR-027.
6. Gör dödsfallsavräkning och för kapital till pool; befintlig betalningsskuld
   dras inte igen. Avliden får ingen ny arvsvinst.
7. Fördela pool till behöriga kvarvarande mottagare enligt PR-011.
   Del som förbrukat sista månadsrätten deltar inte i denna fördelning.
8. Stäng månaden, stäm av tillgångar/skulder/pool och fastställ underlag
   för nästa månads start/återstart/januariomräkning.

Bankuppdrag verkställs första svenska bankdagen efter pensionsmånaden,
sedan månadsjournalen stängts. Därmed är månadens faktiska avkastning,
kostnader och sista månads slutavräkning kända före betalningen.
Återkommande försök ändrar inte skuldföringen.
Rättelse av stängd månad är en ny kontrollerad körning med motposter.
C får aldrig bli negativt. Förlust/otillräcklig finansiering går till
PR-028, inte till en dold ny tillgång eller sänkt garanti.

## Kapitalspår per ursprung

För varje del ska C även kunna härledas som summan av icke-negativa
kapitalandelar per ursprunglig premie-ID och separat bolagsstöds-ID.
Det är en beräknings-/revisionsuppdelning, ingen ytterligare garantidel.
Ny premie tillför sitt eget spår. Delning delar varje spår proportionellt.

Månadens totala avkastningspost fördelas på spårens öppningskapital.
Avgift, skattebelastning och pensionsdebit fördelas på deras tillgängliga
positiva kapital vid respektive debitsteg, proportionellt och i ören med
största bråkrest. Ingen andel kan debiteras mer än sitt kapital.
Arvsvinst fördelas inom delen efter ursprungsspårens öppningsbas;
det ger kapital men ingen ny garanti. Bolagsstöd har egen motpost och
förbrukas med den pension det finansierar. Summan av kapitalspår är alltid C.

Rättelsen i PR-019 kan därför återskapa just den felpremiens återstående
kapital, inklusive fördelade rörelser, utan att gissa dagens premieandel.
Spårens garantibelopp och kapitalandelar är fortfarande olika värden.

## Kontrollfall

C0=100 000, faktisk r=1 %, inga premier: avkastning +1 000; kapitalavgift
16,67 och skattebelastning 29,50 (2026). Ny premie 1 000 vid stängning
får avkastning från nästa månad, inte ytterligare 10 kr nu.
