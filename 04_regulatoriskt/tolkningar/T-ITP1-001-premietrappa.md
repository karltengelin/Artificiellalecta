# T-ITP1-001 – ordinarie premietrappa och avrundning

> **Status:** Utkast | **Version:** 0.1 | **Ägare:** Operatören
> **Upprättad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Berörd regel:** [PR-ITP1-001](../../01_domän/produktregler/PR-ITP1-001-premietrappa.md)

## Fråga och avgränsning

Hur uttrycks den ordinarie ITP1-premietrappan som en granskningsbar regel för en
kalendermånad, och vilka delar av befintlig kod är externa krav respektive egna
beräkningsval? Provet avser 2026 och ålderspension, inte hela ITP-paketets kostnad.

## Källunderlag

| Källa | Avsnitt/bestämmelse | Stöd och begränsning |
|---|---|---|
| [K-ITP1-2026](../kallregister.md#k-itp1-2026--officiella-sammanställningar-av-premier) | Avtalats premietabell 2026; Collectums premie- och basbeloppstabeller | Stöd för trappan; exakt avtalsutgåva och punkt återstår |
| [K-IBB-2026](../kallregister.md#k-ibb-2026--förordning-om-inkomstbasbelopp) | Förordning (2025:1002), 1 § | Stöd för 2026 års IBB, inte för procentsatser eller avrundning |
| [Befintlig implementation](../../src/skills/calculation/calculate_itp1_premium.py) | `calculate_itp1_premium` | Belägger systemets beteende, inte kollektivavtalets innehåll |

## Resonemang och alternativ

Lönegränserna för 2026 motsvarar 7,5 respektive 30 IBB per år delat med tolv.
Formeln i produktregeln är vår matematiska precisering av tabellens trappa.
Premien beräknas för den inrapporterade månadslönen. Vad som räknas som sådan
lön och vem som är premieberättigad behöver egna regler.

Ett tak i den ordinarie trappan utesluter inte kompletterande premier.
Resultatet ska behandlas som ordinarie bruttopremie, inte automatiskt som
nettoinflöde till kapital efter administratörsavgifter eller andra avdrag.

Befintlig kod avrundar de två premiekomponenterna var för sig med ROUND_HALF_UP
och summerar därefter. Ett annat alternativ är att avrunda den oavrundade
totalsumman. Alternativen kan skilja ett öre. För lön 52 125,05 kronor och IBB
83 400 blir komponentavrundning 2 345,65 kronor och totalavrundning
2 345,64 kronor från 2 345,640.

Komponentavrundning gör att bokförda komponenter summerar till totalen. Detta
förklarar kodens val men bevisar inte att administratören använder samma metod.

## Föreslagen slutsats

Trappan och 2026 års parameter är verifierade mot angivna externa källor på
sammanställningsnivå. Avtalsreferens och historisk giltighet återstår.
Dokumentera komponentavrundning som befintligt implementationsval, under
granskning. Gör den inte till ett påstått avtalskrav utan ytterligare källstöd.

## Operativa konsekvenser

- Ingen ändring av kod, premiehistorik eller villkor i detta prov.
- Provregelns giltighet är avgränsad till premiemånader 2026; äldre år kräver separat källkontroll.
- Fördelning mellan flera försäkringar/förmåner enligt B-022 återstår; trappan ska inte upprepas på samma löneunderlag utan en uttrycklig fördelningsregel.
- `calculation_basis` lagrar beräkningsparametrar men saknar regel-ID och regelversion. Framtida spårbarhet behöver precisera detta utan att skriva om historiken automatiskt.

## Öppna frågor och godkännande

F-001, F-002, F-006, F-007 och F-008 i [arbetsutkastet](../../projekt/04_produktregelverk/ARBETSSATT.md)
berör denna tolkning. Ingen rättslig fullständighet eller produktionsklarhet
hävdas. Operatören granskar dokumentkedjan och beräkningsvalet innan regeln antas.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Första tolkning av befintlig trappa |
