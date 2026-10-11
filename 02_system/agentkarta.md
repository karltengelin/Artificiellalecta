# Agentkarta – ITP1 Administrationsplattform

> Samlad översikt över alla agenter i systemet. Varje agent har en detaljerad MD-fil i `02_system/agenter/`.
> Uppdatera detta dokument när agenter tillkommer, förändras eller tas ur drift.

---

## 1. Agentöversikt

Varje agent tillhör ett team (B-026). Teamets ledande agent är dess orkestrerare; specialister arbetar på uppdrag av den. Teamets verktyg är de skill-poddar som är monterade på teamet – se `agentekosystem.md` §3 och §5.

| Team | Agent | Roll i teamet | Funktionsområde | Status |
|------|-------|---------------|-----------------|--------|
| Försäkring & kund (`forsakring`) | [Handläggaragent](agenter/handlaggaragent.md) | Ledande (orkestrerare) | Kundadministration & ärendehantering | 🔲 Ej påbörjad |
| Kommunikation (`kommunikation`) | [Kommunikationsagent](agenter/kommunikationsagent.md) | Ledande (orkestrerare) | Kund- & intressentkommunikation | 🔲 Ej påbörjad |
| Kapitalförvaltning (`kapital`) | [Portföljförvaltningsagent](agenter/portfoljforvaltningsagent.md) | Ledande (orkestrerare) | Kapitalförvaltning | 🔲 Ej påbörjad |
| Aktuarie & analys (`aktuarie`) | [Aktuarieagent](agenter/aktuarieagent.md) | Ledande (orkestrerare) | Aktuariell verksamhet | 🔲 Ej påbörjad |
| Aktuarie & analys (`aktuarie`) | [Data scientist-agent](agenter/data-scientist-agent.md) | Specialist | Datahantering & analys | 🔲 Ej påbörjad |
| Regelefterlevnad & rapportering (`compliance`) | [Compliance-agent](agenter/compliance-agent.md) | Ledande (orkestrerare) | Regelefterlevnad | 🔲 Ej påbörjad |
| Regelefterlevnad & rapportering (`compliance`) | [Rapporteringsagent](agenter/rapporteringsagent.md) | Specialist | Regulatorisk rapportering | 🔲 Ej påbörjad |
| Ekonomi & inköp (`ekonomi`) | [Ekonomiagent](agenter/ekonomiagent.md) | Ledande (orkestrerare) | Ekonomi & redovisning | 🔲 Ej påbörjad |
| Ekonomi & inköp (`ekonomi`) | [Inköpsagent](agenter/inkopsagent.md) | Specialist | Inköp & avtalsgranskning | 🔲 Ej påbörjad |
| Utveckling & plattform (`utveckling`) | [Utvecklaragent](agenter/utvecklaragent.md) | Ledande (orkestrerare) | IT & dataplattform | 🔲 Ej påbörjad |

---

## 2. Mandatbeskrivningar

**Compliance-agent**
Tolkar lagar, förordningar och föreskrifter och omsätter dem till operativa konsekvenser för bolaget. Ansvarar för styrdokumentsstruktur och tar emot eskaleringar från samtliga agenter i juridiskt tveksamma fall. (B-011)

**Handläggaragent**
Hanterar löpande kundadministration (premieflöden, policyändringar, förmånstagaruppdateringar) och inkommande ärenden. Routar ärenden internt och förbereder svar – men lämnar över faktisk kundkommunikation till Kommunikationsagenten.

**Kommunikationsagent**
Äger alla utgående kanaler och kommunikationsmallar. Producerar kundutskick, mailsvar och standardiserade meddelanden på uppdrag av övriga agenter. Alla externa utskick kräver manuellt godkännande (§3.5).

**Data scientist-agent**
Utför statistiska analyser och bygger datamodeller. Levererar analytiska underlag till Aktuarieagenten, Rapporteringsagenten och Portföljförvaltningsagenten. Samarbetar med Utvecklaragenten kring datainfrastruktur.

**Portföljförvaltningsagent**
Övervakar placeringstillgångar mot fastställda placeringsriktlinjer. Förbereder investeringsbeslut och ombalanseringar för manuellt godkännande (§3.5). Arbetar inom ramarna för LTF och Solvens II.

**Utvecklaragent**
Bygger och underhåller kod, agenter, skills och integrationer (utvecklarroll). Ansvarar för datapipelines och databasens integritet (data engineer-roll). Ingår i regelförändringsflödet.

**Aktuarieagent**
Beräknar försäkringstekniska avsättningar, upprätthåller aktuariella antaganden och genomför känslighetsanalyser. Levererar underlag till Rapporteringsagenten och stödjer Portföljförvaltningsagenten med riskperspektiv (ALM).

**Rapporteringsagent**
Sammanställer och lämnar in regulatorisk rapportering till FI och övriga myndigheter. Äger ORSA-processen. Producerar intern rapportering till ledning och styrelse. Alla inlämningar kräver manuellt godkännande (§3.5).

**Inköpsagent**
Granskar leverantörsavtal och säkerställer att de är förenliga med bolagets policies och regulatoriska krav (inkl. DORA:s krav på tredjepartshantering). Förbereder avtalsunderlag för manuellt godkännande (§3.5).

**Ekonomiagent**
Ansvarar för bokföring, budget och likviditetsuppföljning. Levererar finansiella underlag till Rapporteringsagenten och samarbetar med Inköpsagenten kring kostnadsuppföljning.

---

## 3. Agentinteraktioner

### Eskaleringsvägar

Alla agenter kan eskalera till **Compliance-agenten** vid juridiskt tveksamma situationer.

### Löpande samarbeten

Pilarna beskriver vilka underlag som flödar mellan agenterna. Arbete mellan **olika team** beställs via mottagarteamets ledande agent – inte direkt hos en specialist (B-026, `agentekosystem.md` §3.2 och §6.1). Inom ett team fördelar den ledande agenten arbetet.

```
Handläggaragent  ──────────────► Kommunikationsagent   (kundkommunikation)
Handläggaragent  ──────────────► Compliance-agent       (eskalering)

Data scientist-agent ──────────► Aktuarieagent          (analytiska underlag)
Data scientist-agent ──────────► Rapporteringsagent     (analytiska underlag)
Data scientist-agent ──────────► Portföljförvaltningsagent (portföljanalys)
Data scientist-agent ◄──────────► Utvecklaragent        (datainfrastruktur)

Aktuarieagent ─────────────────► Rapporteringsagent    (aktuariella underlag, ORSA)
Aktuarieagent ◄────────────────► Portföljförvaltningsagent (ALM)

Portföljförvaltningsagent ─────► Rapporteringsagent    (portföljdata)
Portföljförvaltningsagent ─────► Compliance-agent       (placeringsriktlinjer)

Inköpsagent ◄──────────────────► Ekonomiagent          (kostnadsuppföljning)
Inköpsagent ───────────────────► Compliance-agent       (avtalsgranskning)

Ekonomiagent ──────────────────► Rapporteringsagent    (finansiella underlag)
Ekonomiagent ◄─────────────────► Portföljförvaltningsagent (värdering)
```

### Regelförändringsflöde (multi-agent)

Ett dedikerat flöde triggas när ett regelverk ändras. Dokumenteras separat i `02_system/Agentsystem/regelförändringsflöde.md`.

```
1. Compliance-agent      → tolkning och konsekvensanalys
2. Utvecklaragent        → identifierar kodpåverkan
3. Kommunikationsagent   → förbereder kundkommunikation (om relevant)
```

---

## 4. Designprinciper för agenter

- **Skills före nya agenter (B-008):** Ny funktion byggs som skill till befintlig agent. Ny agent skapas bara vid distinkt, annorlunda mandat.
- **Delat skillsbibliotek (B-007):** Alla skills ligger centralt i `03_skills/`. Varje agent har en deklarerad lista över vilka skills den får använda.
- **Behörighetsmodell (B-006):** Skills som rör personuppgifter är begränsade till de agenter som faktiskt behöver dem.
- **Människa-i-loopen (§3.5):** Alla externa åtgärder (utskick, rapportinlämningar, transaktioner, avtalssigneringar) kräver manuellt godkännande.
- **Team och skill-poddar (B-026):** Agenterna organiseras i sju team där den ledande agenten är teamets orkestrerare; behörighet ges per skill-pod. Se `agentekosystem.md` §3–5.

---

## 5. Hänvisningar

- Detaljerade agentbeskrivningar: `02_system/agenter/`
- Skillkatalog: `03_skills/skillkatalog.md`
- Regelförändringsflöde: `02_system/Agentsystem/regelförändringsflöde.md`
- Agentekosystem (team, poddar, delegering, modellval, nycklar): `02_system/agentekosystem.md`
- AI-lagret som alla agenter anropar modeller via: `02_system/ai_abstraktion.md`
- Arkitekturprinciper: `MASTER_CONTEXT.md §3`
- Beslut om agentarkitektur: B-006, B-007, B-008, B-011
