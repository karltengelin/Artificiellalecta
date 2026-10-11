# Bevakning, källversion och övergång

> Sammanställning 2026-10-11. PR-032 och [källregistret](../kallregister.md).

Källorna är versionsidentifierade länkar, avsnitt och kontrolldatum.
SCB-tabellen är sparad lokalt; övriga fulltexter påstås inte vara arkiverade.
Kontrollera ändringsregister/giltighetsbestämmelse, inte bara senaste rubrikdatum.

Bolaget väljer följande dokumentrutin:
1. Inför varje årsskifte: fastställ IBB, SLR/avkastningsskattesats, pensions-
   skattetabell/kolumn, SINK och svensk bankkalender för det nya året.
2. Inför ny produkt-/AI-version: kontrollera relevanta avtals- och
   författningsutgåvor och vilka befintliga rättigheter som berörs.
3. Vid identifierad ändring: spara gammal/ny källa, giltighetsdag, egen
   tolkning, berörda PR/villkor/parametrar och ekonomisk konsekvens.
4. Samlat införandebeslut och kundinformation före verkställighet.
   Historiska garantidelar och ekonomiska rättigheter bevaras.
5. Byggsessionen kompletterar med kod-/testkoppling och återställningsplan
   enligt [regelförändringsflödet](../../02_system/Agentsystem/regelförändringsflöde.md).

Ingen ny källversion får tyst flytta dagens regler bakåt till mockhistorik.
Importerad faktiskt äldre rätt kräver sin verkliga grund. Syntetisk
SIM-HIST får användas enbart i uttryckligt omgenererat demo-scenario.

Föreslaget dokumentdemo är en årsväxling av IBB: källa → parameter →
berörd premie och information med oförändrad historisk garanti.
Det kräver inte att vi hittar på en pensionsåldersändring.
Det automatiserade agentflödet byggs i en senare session.
