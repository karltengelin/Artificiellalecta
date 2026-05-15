# Regelförändringsflöde

> **Typ:** Orkestrerat agentflöde
> **Trigger:** Nytt eller ändrat lagkrav, förordning eller föreskrift identifieras
> **Status:** 🔲 Ej implementerat

---

## Syfte

Säkerställer att en regelverksförändring hanteras strukturerat och spårbart – från initial tolkning till teknisk anpassning och eventuell kundkommunikation. Flödet involverar tre agenter i sekvens och kräver manuellt godkännande vid varje etapp innan nästa startar.

---

## Involverade agenter

| Steg | Agent | Ansvar |
|------|-------|--------|
| 1 | Compliance-agent | Tolkning och konsekvensanalys |
| 2 | Utvecklaragent | Kodpåverkan och teknisk anpassning |
| 3 | Kommunikationsagent | Kundkommunikation (om relevant) |

---

## Flödesbeskrivning

### Steg 1 – Compliance-agent: Tolkning och konsekvensanalys

**Input:** Regelverksändring (lagtext, föreskrift, vägledning)

**Uppgift:**
- Analysera vad ändringen innebär för bolaget
- Identifiera påverkade produktregler, processer och styrdokument
- Bedöma om kundpåverkan föreligger
- Föreslå nödvändiga ändringar i styrdokument

**Output:** Konsekvensanalys (MD-fil) med lista över påverkade områden

**Manuellt godkännande:** Ja – konsekvensanalysen godkänns innan steg 2 startar

---

### Steg 2 – Utvecklaragent: Kodpåverkan och teknisk anpassning

**Input:** Godkänd konsekvensanalys från steg 1

**Uppgift:**
- Identifiera vilka delar av systemet som behöver ändras
- Specificera tekniska anpassningar (modeller, beräkningar, databasschema, etc.)
- Uppskatta omfattning och prioritet

**Output:** Teknisk åtgärdslista

**Manuellt godkännande:** Ja – åtgärdslistan godkänns innan implementering påbörjas

---

### Steg 3 – Kommunikationsagent: Kundkommunikation (villkorat)

**Villkor:** Utförs endast om konsekvensanalysen (steg 1) bedömt att ändringen påverkar kunder

**Input:** Godkänd konsekvensanalys + beslut om kundkommunikation

**Uppgift:**
- Utforma kundanpassad information om förändringen
- Välja lämplig kanal och timing

**Output:** Kommunikationsutkast

**Manuellt godkännande:** Ja – alla utskick godkänns innan avsändning (§3.5)

---

## Spårbarhet

Varje körning av flödet ska producera:
- Konsekvensanalys (daterad MD-fil)
- Teknisk åtgärdslista (daterad MD-fil)
- Eventuellt kommunikationsutkast

*(Lagringsplats för körningsloggar beslutas när flödet implementeras)*

---

## Hänvisningar

- Beslutslogg: B-008 (skills före agenter – detta flöde är ett motiverat undantag), B-016 (hybrid orchestration)
- Agentbeskrivningar: `02_system/agenter/`
