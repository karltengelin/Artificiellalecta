# PR-ITP1-014 – pensionsmedförande månadslön
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Avtal och verifierad administrativ löneslagslista.
**Källor:** K-ITP-AVTAL-2026, K-ITP-LON i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-006](../../04_regulatoriskt/tolkningar/T-ITP1-006-premie-lon-och-anslutning.md).
**Villkor:** [§3 i v2.0](../försäkringsvillkor.md).

## Grund och regel

ITP 6 samt Collectums aktuella ITP1-kolumn i löneslagslistan (T-006).
Utgå från faktiskt utbetald kontant bruttolön **efter löneväxling**.
Avtalad lön, årsgenomsnitt och ITP2:s lönedefinition får inte ersätta den.

| Hantering | Löneslag som uttryckligen prövas |
|---|---|
| Ingår | Kontant grundlön, bonus/provision, övertid/mertid, jour/beredskap, restid, OB och ansvarstillägg, semesterlön/-tillägg/-ersättning, lagstadgad sjuklön |
| Ingår med kontroll | Arbetsbefriad lön under bestående anställning; fast kontant biltillägg som är lön |
| Ingår inte | Kostnadsersättning/milersättning/traktamente, naturaförmåner/aktier/optioner, avgångsvederlag, föräldralön, sjuklön utöver lagstadgad, ersättning från Försäkringskassan |
| Separat premie | Avtalad pensionskompensation för löneväxling, flex-/deltidspension |

För okänt eller blandat löneslag krävs uppdelning och klassificering före
beräkning. Arbetsgivaren kan lämna färdig pensionsmedförande total med
intygad klassificering; annars används underliggande poster.
Listan är en uttrycklig tillämpning för våra vanligaste löneslag, inte
ett sätt att gissa resten av Collectums tabell.

Använd utbetalningsmånadens IBB. Ingen årsutjämning av bonus; ett tak
gäller varje månad. Noll rapporteras uttryckligen och skiljs från saknad
rapport. Negativ total går till rättelse, inte negativ ny premietrappa.
Retroaktiv löneökning som faktiskt betalas nu är ny lön nu; rättelse av
felregistrerad gammal utbetalning ändrar just den gamla rapportmånaden.

## Kontrollfall

Kontant lön 40 000 + bonus 20 000: L=60 000 i utbetalningsmånaden.
Lön före växling 50 000, växling 5 000: L=45 000; komplettering separat.
Kontant biltillägg 2 000 kan ingå; milersättning 2 000 ingår inte.
