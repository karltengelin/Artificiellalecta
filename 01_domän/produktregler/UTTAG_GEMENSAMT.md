# Gemensamma förutsättningar för uttagsreglerna

> **Version:** 0.1 | **Status:** Utkast, ej godkänt | **Implementation:** Saknas
> **Ägare:** Operatören | **Upprättad:** 2026-10-11
> **Gäller för:** PR-ITP1-002–005, endast ITP1 ålderspension.

| Regel | Fråga |
|---|---|
| [PR-ITP1-002](PR-ITP1-002-tidigarelagt-uttag.md) | Första start före ordinarie pensionsålder |
| [PR-ITP1-003](PR-ITP1-003-uppskjutet-uttag.md) | Första start efter ordinarie pensionsålder |
| [PR-ITP1-004](PR-ITP1-004-paus.md) | Pausa redan påbörjad utbetalning |
| [PR-ITP1-005](PR-ITP1-005-aterupptagande.md) | Återuppta efter paus |

## Externa krav och egna val

[T-ITP1-002](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md)
redovisar källor och tillämplighet. Enligt ITP-avtalet avdelning 1 punkt 7.5
är ordinarie start 66-årsmånaden, tidigaste ålder 55 år och standardformen
livsvarig; tidsbegränsat uttag är minst fem år. Här föreslås hela
utbetalningsmånader, minst 60 vid tidsbegränsat uttag. Dödsfall och eventuell
tidigare avslutning har företräde framför ett planerat uttag; efter dödsfall
ska ingen framtida ålderspension planeras. Slutavräkning för dödsmånaden
hanteras separat. Produkten har inget efterlevandeskydd.

ITP-parternas flexibilitetsöverenskommelse innebär paus och förlängning utan
särskild ändringsavgift eller hälsoprövning, även för tidigare påbörjade uttag
och vid upprepade ändringar. Den löpande kapitalavgiften enligt B-021 är en
annan avgift och föreslås fortsätta som vanligt under paus.

**Föreslagen gemensam frist:** En komplett, behörig begäran ska vara mottagen
senast sista kalenderdagen i månaden före ändringsmånaden, enligt
Europe/Stockholm. Sena begäranden ger utredning och förslag på nästa möjliga
månad, inte retroaktiv ändring eller tyst flytt av kundens val. Bekräftelse
krävs om den önskade månaden ändras. Begäran, prövning och verkställighet
är olika händelser; en godkänd framtida ändring ändrar inte dagens tillstånd.

Flera begäranden för samma försäkring måste ordnas och en tidigare plan
uttryckligen ersättas. Upprepad leverans av samma begäran får inte skapa
dubbla tillståndsperioder eller betalningar. En försäkring kan ha flera
pauser i historiken men en aktiv pausplan åt gången.

## Gemensam indata och utfall

Indata: försäkrings-ID, förmånstyp, födelsedatum, livs-/avslutsstatus,
aktuellt tillstånd och historik, faktisk första utbetalningsmånad,
begärans-ID/behörig avsändare, mottagningstid, önskad start/paus/återstart,
utbetalningsform och redan förbrukade utbetalningsmånader.
Beloppsbeslut behöver dessutom kapitalunderlag och godkänd aktuariell grund.

Utfall: godkänd framtida plan, begäran om komplettering, manuell prövning
eller motiverat avslag. Spara regel-ID/version, underlag, beslutsfattare,
beslutstid, giltighetsmånad och ersatt plan. Saknad beräkningsgrund eller
oklar tillämplighet får inte döljas med ett uppskattat belopp.

## Tillstånd och dataförslag

| Händelse | Föreslagen hantering |
|---|---|
| Tidigt/ordinarie/uppskjutet första uttag verkställs | Övergång till `in_payout` |
| Uppskjuten start registreras | Ändra framtida uttagsplan; ingen automatisk ändring till `paid_up` |
| Paus verkställs | `in_payout` → `payout_paused` |
| Återstart verkställs | `payout_paused` → `in_payout` |
| Dödsfall/avslut under paus | Ingen återstart; avslutshanteringen har företräde |

Tillstånden finns i [policy_state.py](../../src/models/policy_state.py).
De implementerar inte reglerna i sig. `paid_up` beskriver upphörd premie,
inte uppskjuten start eller paus. Paus får inte automatiskt stoppa premie.
Samtidig premie och uttag samt partiellt uttag kräver en modell som kan
skilja premie- och utbetalningsförlopp; dagens enda tillstånd per försäkring
räcker inte för alla sådana kombinationer.

**Dataförslag, ingen migration:** Separat versionshanterad uttagsplan med
första faktiska start, planerad start/återstart, pausperioder, utbetalningsform,
avtalad total/återstående utbetalningstid och beslutskoppling. Betalningsjournalen
måste skilja en rätt till månadsbelopp från banköverföring: ett misslyckat
betalningsförsök är inte en avtalad paus och ska inte förbruka två månader
vid ett nytt försök.

## Godkännande, giltighet och villkor

Reglerna är inte kundvillkor eller tekniskt driftsatta. Förslaget gäller
framtida händelser på nya och befintliga simulerade försäkringar efter ett
ännu inte bestämt ikraftträdandedatum. Ingen historisk utbetalning räknas om
genom dokumentändringen. [Villkorsversion 1.0](../försäkringsvillkor.md) §7
innehåller äldre, felaktiga åldersantaganden och får inte användas som
verifierat implementationsunderlag; ersättning föreslås separat.

Aktuariell grund, garanti, skatterättslig gren och tillståndsmodell behöver
granskas före kodarbete. Förlängning av utbetalningstid behöver en egen regel.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Gemensamma förutsättningar och dataförslag |
