# Gemensamma uttagsförutsättningar

> **Version:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> Ingår i det fullständiga dokumentunderlaget. Införande och implementation är separata.

## Begäran, beslut och rättighet

Kunden eller verifierat ombud väljer en identifierad uttagsdel.
Begäran om ny start, paus, återstart eller förlängning ska ha kommit in
senast sista kalenderdagen i månaden före önskad ändringsmånad, i
Europe/Stockholm. Det är ett eget servicevillkor. Mottagning registreras
även om handläggningen sker senare. En fullständig behörig begäran i tid
förlorar inte önskad dag enbart genom bolagets dröjsmål.

Sena/otillräckliga begäranden ger konkret komplettering eller förslag
på nästa möjliga månad; kundens bekräftelse behövs om datum ändras.
Ingen vanlig retroaktiv paus eller radering av redan uppkommen rätt.
Bolagets handläggningsfel rättas enligt PR-019 med prövning av den
ursprungliga giltiga begäran. Godkänd framtida plan ändrar inte dagens
läge före giltighetsdagen. Motstridiga planer ska uttryckligen ersättas.

Fullständigt kundval innehåller startmånad, livsvarig/tidsbegränsad form,
antal betalningsmånader om ändlig, delningsandel om deluttag och eventuell
paus/återstart. Alltid identitet, behörighet och levandestatus.
Tidigt uttag behöver PR-002/024:s pensioneringsunderlag. Beslut sparar
regel-/villkorsversion, tariff/faktorer, belopp, skattestatus, motivering
och beslutsfattare. Belopp, månadsanspråk och banköverföring är olika händelser.

## Tre oberoende förlopp

| Förlopp | Lägen som ska kunna uttryckas |
|---|---|
| Premie/intjänande | Giltigt premieintervall, premiefri, avslutad tillhörighet; sena poster separat |
| Uttagsdelens pension | Ej startad, framtida plan, pågående, pausad, rättighetsavslutad |
| Betalningsanspråk | Uppkommen, finansierad/ej finansierad, bankförberedd, skickad/okänd, betald, avvisad/återkommen |

Verifierat dödsfall har företräde utan att radera tidigare betalningsanspråk.
Fribrev är upphörd premie, inte paus. En person kan samtidigt ha olika lägen
på olika delar. Ett enda försäkringstillstånd räcker därför inte.

## Konceptuellt dataunderlag för byggsessionen

- Person, arbetsgivare, ITP-anslutning, anställningsperiod och behörighet.
- Avtal/förmån och uttagsdel med ursprunglig försäkring, delningshistorik,
  öppningsbas och premieallokering. Varje ekonomisk post tillhör exakt en del.
- Planversion: originalstart, form, totalt/förbrukat/kvarvarande antal
  rättigheter, kundval, pausintervall, återstart och härledd slutmånad.
- Garantidel per nettopremie: premie-/mottagningsperiod, historisk tariff,
  referens-/aktuell plan, garanterat belopp, rättelser och ursprung.
- Kapitaljournal samt separata konton för premiefordran, avstämning,
  kundkapital, betalnings-/skatteskuld, arvsvinstpool och bolagskapital.
- Månadsanspråk: rättighetsmånad, brutto, finansiering, faktiska
  betalningsförsök/-dagar, avdrag, netto och rapporteringsversion.
- Verifierat dödsdatum och rapportdatum, avräkning och obetalda rättigheter.
- Besked/ärende/beslut med käll-, regel-, villkors- och parameterreferenser.

Det är informationskrav, ingen ändring av databas eller kod.
Kapital bevaras vid delning/poolöverföring. Inga dubbla premier eller
månadsrätter. Paus förbrukar inte betalningsmånader och nytt bankförsök
skapar ingen rätt. Livsvarigt har inget faktiskt slutdatum.
Se [katalogen](README.md) och [leveranskontrollen](../../projekt/04_produktregelverk/LEVERANSKONTROLL.md).
