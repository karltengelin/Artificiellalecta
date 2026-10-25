# Projekt 5: Kapitalförvaltning

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

Paper trading-portfölj för placering av premiereserver (B-019), samt ett gränssnitt för att
analysera innehav/bolag och justera allokeringen – dvs. hantera portföljen, inte bara simulera den
regelstyrt. Kapitaldata ska lagras så BI (projekt 2) kan ta ut insikter ur den.

## Status

🟡 Fas 2a och 2b:s dokumentleveranser klara som beslutsutkast 2026-10-24:
minimal styrdokumentshierarki (SD-STYR-001 v0.1) och placeringsriktlinje
(SD-KAP-001 v0.1). Antagande och giltighetsdag återstår. Fas 2c:s datamodell
är byggd och testad lokalt; tabellerna är inte skapade i Lakebase.
Marknadsdata och förvaltningslogik (2d/2e) samt analysgränssnittet återstår;
ingen paper trading-funktion är aktiverad.

**Fas 2c, steg 1 och 2 klara 2026-10-24:** [Modellval A–F](DATAMODELL_BESLUTSFORSLAG.md)
har tillämpats inom operatörens mandat att välja modell och fortsätta efter
designstoppet. `Portfolio`, `PortfolioHolding` och `Trade` finns i `src/models/`,
dokumenterade i databasschemat §§9d–9f. Separat startkassa, härledda saldon
(beräkningskod senare), kompletta affärskvittenser och bevarade prisunderlag.
Lokala SQLite-tester samt kompilering av Postgres-DDL utan anslutning;
ingen gateway, extern handelsplattform, seed eller Lakebase-körning ingår.
Modellerna registreras automatiskt för befintligt `create_tables.py`, som inte körts.

## Beroenden

- Placeringsriktlinjen finns som beslutsutkast; före tillämpning krävs antagna
  styrdokument, godkänd instrumentlista, dokumenterat scenario och fungerande kontroller
- Beståndskoppling kräver dessutom avstämd finansiering och ALM-underlag enligt riktlinjens §§2/7
- Premieinflödet (Fas 1) kopplas som insättningar till portföljen
- För månadssimuleringen samordnas V-07 och paketen A/B i
  [processöversikten](../../01_domän/processer_översikt.md): avstämda faktiska kassaflöden
  från premier och till pensionsbetalningar, kurs-/värderingsversioner, likviditet och
  avkastningsunderlag till kapitaljournalen. Stäm även av ingående portfölj/kassa mot
  startbeståndets finansiering (S-04). Kundkapital eller garantier får inte kopieras som
  en extra insättning i portföljen

## Befintlig grund i repot

- B-019 (paper trading, inget riktigt kapital)
- B-003 (sandbox – gäller kapital generellt)
- [Minimal styrdokumentshierarki](../../05_styrdokument/styrdokumentshierarki.md) – Fas 2a, beslutsutkast
- [Placeringsriktlinje](../../05_styrdokument/03_riktlinjer/placeringsriktlinje.md) – Fas 2b, beslutsutkast
- Fas 2a–2e i `ATT_GORA.md`

## Öppna designfrågor

- Karl beskriver sig som osäker på kapitalförvaltningsdomänen – förslaget är att börja med en
  enkel, regelstyrd standardlösning (redan beslutat i B-019) och vidareutveckla analysgränssnittet
  i en senare iteration, snarare än att designa allt på en gång
- Hur ser analysgränssnittet ut (egen vy i handläggar-UI:t, eller fristående)?
