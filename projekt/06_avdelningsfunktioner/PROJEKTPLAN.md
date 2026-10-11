# Projekt 6: Avdelningsfunktioner

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, förslag B-024).

## Scope

Bygga ut funktioner för bolagets övriga avdelningar (se "Bolagets funktionsområden",
MASTER_CONTEXT §4), i första hand en **aktuariell modul** där agenter kan hantera premiesättning
utifrån krav och koppla till regelverk från Finansinspektionen. Omfattar både att förstå/tolka
regelverk och svensk lag, och att organisera låtsasbolaget (avdelningar, mandat) så det stämmer
överens.

## Status

🔲 Ej påbörjat.

## Beroenden

- Delar av tolkningsarbetet överlappar projekt 4 (produktregelverk) – avstäm innan parallellt
  arbete påbörjas (jfr AGENTS.md §4.2)

## Befintlig grund i repot

- "Bolagets funktionsområden"-tabellen, `MASTER_CONTEXT.md` §4
- `02_system/agentkarta.md` (tio agentskelett, kan redan innehålla tankar om avdelningsindelning)

## Öppna designfrågor

- Ett delprojekt per avdelning, eller en gemensam modul som växer per avdelning? (Karl nämner att
  det kan behövas ett projekt per viktig avdelning)
- Hur mappas verkliga tjänstepensionsbolags avdelningsstruktur till det simulerade bolaget?
