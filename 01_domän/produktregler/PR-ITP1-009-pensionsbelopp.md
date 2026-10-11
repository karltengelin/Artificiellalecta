# PR-ITP1-009 – pensionsbelopp och rörligt tillägg
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Egen pensionsmodell; verifierad skatteram.
**Källor:** K-IL-UTTAG-2026, K-SCB-LIVSLANGD i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-004](../../04_regulatoriskt/tolkningar/T-ITP1-004-garanti-och-aktuariell-grund.md).
**Villkor:** [§9 i v2.0](../försäkringsvillkor.md).

## Regel

Vid start, varje januari, återstart och planändring räknas:
B = C/A_b, kandidat = max(G,B). Garantin är golv, inte en extra betalning
ovanpå kandidaten. Brutto, preliminär skatt och nettobetalning skiljs åt.

**Tidsbegränsad verifierad ITP-del:** IL 58 kap. 11 b/20 och ITP-planens
betalningsram används. Vårt rörliga tillägg får öka/minska vid de angivna
omräkningarna, aldrig under aktuell garanti. PR-027 styr sista rätt.

**Livsvarig del:** IL 58 kap. 11/11 a. Under de första 60 månadsrätterna
väljer bolaget försiktigt ett brutto som minst motsvarar senaste beslutade
brutto för oförändrad plan. Paus förbrukar inte perioden och får ensam
inte återställa golvet. En verklig förlängning enligt PR-007 kan ge ny
utgångsnivå. Vi använder inte automatiska sänkningsundantag i 11 a,
trots att lagen kan medge dem. Efter 60 rättigheter gäller max(G,B)
vid ordinarie omräkning. Golvet kan kräva bolagsfinansiering enligt PR-028.

Besluta total M i ören med ROUND_HALF_UP, men aldrig lägre än summan G
avrundad **uppåt** till närmaste öre eller tidigare bindande golv.
En positiv pensionsrätt har därmed minst 0,01 kr i månadsbrutto.
Detta är vårt uttryckliga avrundningsskydd, inte en ytterligare premie.
G_j behåller hög precision för framtida planomräkning; garantibeskedet
visar både grundens belopp och utbetalningsbart öresgolv.

Verifierad allmän pensionsplan betyder identifierat ITP-avtal/anslutning,
inte enbart texten ITP i produktnamnet. Oklar anslutning ger utredning,
inte automatisk tillämpning av den friare skattebestämmelsen.
Beloppet ligger fast mellan omräkningar. Ny premie går till en separat
ännu inte startad del och ökar inte automatiskt en pågående tidsbegränsad plans sista
månader. Arvsvinst påverkar kapitalet och nästa ordinarie beloppsbeslut.

## Kontrollfall

G=100, B=130 ger M=130, inte 230. G=100, B=80 ger minst 100.
Livsvarig, tidigare M=130, rätt nr 20, ny B=120: behåll minst 130.
Tidsbegränsad verifierad ITP-del med samma siffror kan ge 120.
Förbrukade rättigheter och livsstatus får inte ändras av omräkningen.
