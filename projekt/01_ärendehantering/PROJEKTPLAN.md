# Projekt 1: Ärendehantering & handläggar-UI

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

Ett gränssnitt där en handläggare kan se och hantera ärenden, och en backend som gör att handläggningen
faktiskt påverkar systemen och databaserna bakom: policys, förmåner, tillståndsperioder och premier.

## Status

🟡 **Handläggar-UI v1 byggt och verifierat i Lakebase (Fas 4, 2026-10-12)**, lokalt och utan inloggning.
Ärenden och handläggaragent för `salary_report` är byggda (F5-1–4, B-033).
`cases` och agentrollens rättigheter infördes i Lakebase 2026-10-24. Kvar i
F5-5–6: slutverifiering av agentförslag och hela ärendeflödet från 2026-11-01.
Självständiga körningar och fler ärendetyper återstår. Den breda modelloberoende
bolagsdialogen planeras i projekt 10; den är ingen separat Claude-chatt i detta projekt.

Handläggaren kan i v1:
- söka en försäkrad på personnummer eller försäkringsnummer och se översikt, löneunderlag, premiehistorik
  och händelser;
- ansluta en ny anställd och registrera en arbetsgivare;
- ändra aktuell lön och kontaktuppgifter;
- registrera löneunderlag, sätta fribrev och rätta premier;
- godkänna eller avslå agentförslag och läsa händelseloggen.
- registrera ärenden om inrapporterat löneunderlag och låta handläggaragenten pröva dem (Fas 5, B-033; tabellen och agentrollens rättigheter finns i Lakebase sedan 2026-10-24).

Allt går via tjänstelagret och loggas. Beskrivning: `02_system/handläggar-ui.md`.

| Steg | Innehåll | Status |
|---|---|---|
| S1 | Grund, sök, översikt, löneunderlag, premiehistorik | ✅ |
| S2 | Formulär för de befintliga skrivoperationerna | ✅ |
| S3 | Godkännandekö och händelselogg | ✅ |
| S4 | Designstopp: nya operationer, se [OPERATIONER_BESLUTSFORSLAG.md](OPERATIONER_BESLUTSFORSLAG.md) | ✅ Godkänt, B-032 |
| S5 | Anslutning, aktuell lön, kontaktuppgifter, arbetsgivare | ✅ |
| S6 | Skarp verifiering i Lakebase | ✅ Backup `20261012T193537Z`. Verifieringsposten AL-000499 anslöts, fick ändrad lön och löneunderlag och sattes i fribrev. Rader och händelselogg stämmer (ATT_GORA) |

## Beroenden

- **Tjänstelagret (Fas 1f, B-028).** UI:t anropar bara dess operationer. Se `02_system/tjänstelager.md`.
- **Fas 3 (AI-abstraktionslagret, B-009)** ✅ byggdes 2026-10-11 i `src/ai/`.
  - Handläggaragenten använder dessutom harness (Fas 3b), ✅ byggd 2026-10-24
    i `src/agents/` (3b-1–3b-8, röktestet gick igenom hos båda leverantörerna), se `02_system/harness.md`.
- **`cases`-tabellen** och ärendeoperationerna är byggda enligt
  [ARENDEN_BESLUTSFORSLAG.md](ARENDEN_BESLUTSFORSLAG.md), godkänt som B-033.
  Tabellen och agentrollens läsrätt finns i Lakebase; slutverifiering enligt F5-5–6 återstår.

## Befintlig grund i repot

- Kod: `src/web/` (FastAPI + Jinja2 + HTMX) och `src/services/` (tjänstelagret)
- Start: `python scripts/web/start_ui.py`, och `.claude/launch.json` i Claude-appen
- Tester: `tests/test_web_*.py`, plus tjänstelagrets tester
- Beslut: B-020 (handläggar-UI före kundportal), B-017 (människa som fullständig operatör), B-028 (tjänstelager),
  B-030 (de första skrivoperationerna), B-032 (anslutning, stamdata och arbetsgivare)
- Datamodell: `02_system/databasschema.md`, `src/models/`
- AI-lager och agentramverk: `02_system/ai_abstraktion.md`, `02_system/agentekosystem.md` (team `forsakring`)

## Nästa steg

**Prioriteringsförtydligande 2026-10-27:** fullfölj befintlig verifiering inom
gällande datum och mandat. Nästa samordnade verksamhetsuppdrag att avgränsa
är paket A (V-01–03): löneunderlag → premie/faktura → mottagen betalning och
avstämt underlag till kapital/garanti och ekonomi. Projekt 1 samordnar
försäkringsoperationerna med projekt 4:s regler, [projekt 6:s ekonomikontrakt](../06_avdelningsfunktioner/PROJEKTPLAN.md)
och kassaflödesgränsen mot projekt 5. Avgränsa kontrakt, ansvar och normal-/
avvikelsefall före kod; ingen sådan implementation är startad genom dokumentuppdraget.

Den närmaste fråge-/rapportkedjan i [projekt 10](../10_operatörscentral/PROJEKTPLAN.md)
är ett separat avgränsat arbetsförlopp. Den utökar inte handläggaragentens
ärendemandat och ersätter inte paket A:s verksamhetsmotorer.

- Följdpunkterna i `ATT_GORA.md` under Fas 4:
  - anställningshistorik
  - lönehistorik
  - namnbyte
  - arbetsgivarens uppgifter och avslut
  - försäkringsbesked
  - interna id:n i adresserna
- Slutverifiera agentförslag och hela ärendeflödet i F5-5–6 från 2026-11-01; nuvarande regelstatus får inte kringgås.
- Bygg självständiga ärendekörningar först med bakgrundsarbetaren och enligt F5-7:s mandat/budget.
- Samordna modelloberoende bolagsdialog med [projekt 10](../10_operatörscentral/PROJEKTPLAN.md), OC-3, och försäkringsteamets område med OC-8 (B-036).

## Öppna designfrågor

### Underlag för löpande verksamhet och månadssimulering

[Processöversikten](../../01_domän/processer_översikt.md) fångar V-01–03 och V-08–09:
anställningshistorik, lön → faktura → mottagen premie, bredare ärendeintag och besked.
Paket A föreslås samordna dessa led; paket B behöver försäkringsoperationer för pension,
kapital och betalning innan de kan exponeras i UI eller kundportal. Fler agentprofiler
ersätter inte dessa motorer. Bryt ned beroendena vid nästa designstart, inklusive
arbetsgivarfil, systemskapade avvikelser och tidsfristuppföljning efter `salary_report`.

### Befintliga gränssnittsfrågor

Se `ATT_GORA.md` 🔵 och projekt 10 för den breda dialogens historik och verktygsmandat.
Fria fil-/CRUD-rättigheter i den äldre adminutredningen är inte bygginstruktion.

Kvar i detta projekt:
- **Autentisering.** I v1 körs UI:t bara lokalt utan inloggning, och verklig autentisering behövs före
  kundportalen.
- **Delad backend med kundportalen.** Tjänstelagret är redan gemensamt.
