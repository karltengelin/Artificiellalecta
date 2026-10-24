# Skillkatalog

> Centralt index över alla skills (B-007). En skill = instruktion (MD) i `03_skills/<kategori>/` + implementation (Python) i `src/skills/<category>/` enligt mappningen i MASTER_CONTEXT §7 / B-015.
>
> **Uppdatera detta dokument när en skill skapas, ändras eller tas bort.** Skills med PII-åtkomst ska ha uttrycklig behörighetslista (B-006).

---

## Skills

| Skill | Kategori | Syfte | PII | Behöriga agenter | Status |
|---|---|---|---|---|---|
| [beräkna-itp1-premie](beräkning/beräkna-itp1-premie.md) | beräkning | Premiemotor: ITP1-premie ur lön + IBB enligt premietrappan | Nej | Alla | 🟢 Implementerad |

## Planerade skills (ur ATT_GORA)

| Skill | Kategori | Kommentar |
|---|---|---|
| hämta-kunddata | data | PII – kräver behörighetslista (B-006) |
| skriv-kundmail | kommunikation | Utskick kräver manuellt godkännande (§3.5) |
| tolka-itp1-fråga | regelverk | Bygger på `01_domän/ITP1_regelverk.md` |
| complianceöversyn | regelverk | Compliance-agenten; gap-analys regelverk ↔ styrdokument |
| marknadsdata | data | Fas 2d (B-019): kurser via gratis-API |
| skapa-dokumentation (`create_documentation`) | kommunikation | Planerad, ej implementerad. Gemensam rapport-/dokumentationsskill i podden `dokument` för alla team/agenter genom granskad montering. En implementation och versionsstyrda mallar; domänagenten ansvarar för sakunderlaget. Allmän väg utan PII; känsliga underlag kräver separat skyddad väg. Se `../02_system/agentekosystem.md` §5.5 och ATT_GORA:s designarbete |
| skapa-presentation (`create_presentation`) | kommunikation | Planerad, ej implementerad. Samma gemensamma dokumentpodd, designgrund och behörighetsgränser som ovan; återanvänder underlag och mallar för enhetliga presentationer oavsett team. Ingen utskicks-/publiceringsbehörighet |

## Hänvisningar

- **B-006** – behörighetsmodell för PII-skills
- **B-007** – delat skillsbibliotek
- **B-008** – skills före nya agenter
- Agenternas skill-listor: `02_system/agenter/<agent>.md`
- Skill-kontrakt och skill-poddar (behörighetsenhet i körning, B-026): `02_system/agentekosystem.md` §5
