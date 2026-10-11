# Projekt 5: Kapitalförvaltning

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, förslag B-024).

## Scope

Paper trading-portfölj för placering av premiereserver (B-019), samt ett gränssnitt för att
analysera innehav/bolag och justera allokeringen – dvs. hantera portföljen, inte bara simulera den
regelstyrt. Kapitaldata ska lagras så BI (projekt 2) kan ta ut insikter ur den.

## Status

🟡 Utredning klar (Fas 2a–2e i `ATT_GORA.md`), inget byggt ännu.

## Beroenden

- Placeringsriktlinje (`05_styrdokument/`) måste finnas innan förvaltningslogik byggs
- Premieinflödet (Fas 1) kopplas som insättningar till portföljen

## Befintlig grund i repot

- B-019 (paper trading, inget riktigt kapital)
- B-003 (sandbox – gäller kapital generellt)
- Fas 2a–2e i `ATT_GORA.md`

## Öppna designfrågor

- Karl beskriver sig som osäker på kapitalförvaltningsdomänen – förslaget är att börja med en
  enkel, regelstyrd standardlösning (redan beslutat i B-019) och vidareutveckla analysgränssnittet
  i en senare iteration, snarare än att designa allt på en gång
- Hur ser analysgränssnittet ut (egen vy i handläggar-UI:t, eller fristående)?
