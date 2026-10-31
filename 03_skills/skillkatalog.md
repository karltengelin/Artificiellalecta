# Skillkatalog

> Centralt index över skills (B-007). Ren beräkningskod finns i `src/skills/<category>/` med instruktioner i `03_skills/<kategori>/` (B-015). Agentverktyg registreras i harness och återanvänder tjänstelagrets operationer eller domängateways; varje verktyg behöver inte en separat implementation i `src/skills/`. Körpolicyn styr tillgängliga poddar och begränsningar.
>
> **Uppdatera detta dokument när en skill skapas, ändras eller tas bort.** Skills med PII-åtkomst ska ha uttrycklig behörighetslista (B-006).

---

## Skills

| Skill | Kategori | Podd | Syfte | PII | Behöriga agenter | Status |
|---|---|---|---|---|---|---|
| [beräkna-itp1-premie](beräkning/beräkna-itp1-premie.md) | beräkning | `berakning` (som `calculate_premium_preview`) | Premiemotor: ITP1-premie ur lön + IBB enligt premietrappan | Nej | Alla | 🟢 Implementerad |

**Kategori och podd är olika saker** (`02_system/agentekosystem.md` §5.1): kategorin styr var dokumentationen ligger, podden styr behörigheten i körning. Agenter når premiemotorn genom tjänstelagrets operation `calculate_premium_preview`, inte genom funktionen direkt.

## Skills i körpolicyn (harness)

Skills som agenter kan få som verktyg, enligt `src/agents/ecosystem.yaml`. Varje skill är ett tunt omslag runt en operation i tjänstelagret eller, sedan 3c-T, ett gatewayverktyg (`regelverk`, `dokument`, `harness.md` §5.2), och hör till exakt en podd. Gatewayverktyg har ingen nivå i åtkomstregistret; gatewayen verkställer sin egen policy. **Åtkomstregistret** visar registrets nivå; effektiv nivå per dag står i `02_system/tjänstelager_operationer.md`. Verktyg med personuppgifter visas först med resursmandat och teamets databasroll (`02_system/harness.md` §5.1). Effektiv profil för en agent: `python scripts/documentation/show_agent_profile.py`.

<!-- list_skills.py: start – genererad, ändra inte för hand -->
| Skill | Podd | Operation eller verktyg | Typ | PII | Åtkomstregistret | Behöriga agenter |
|---|---|---|---|---|---|---|
| `calculate_premium_preview` | `berakning` | `calculate_premium_preview` | compute | Nej | AGENT | actuary_agent (Aktuarieagent), case_handler (Handläggaragent), compliance_agent (Compliance-agent) |
| `correct_premium_transaction` | `kunddata` | `correct_premium_transaction` | write | Ja | HUMAN_ONLY | – |
| `delegate_to_team` | `delegering` | harness `delegate_to_team` | read | Nej | – (körpolicyns delegeringsmål och uppdragets `delegation_targets`) | compliance_agent (Compliance-agent) |
| `estimate_parameter_change_impact` | `bestand` | `estimate_parameter_change_impact` | read | Nej | AGENT, kräver godkänt parameterförslag | actuary_agent (Aktuarieagent) |
| `get_case` | `kunddata` | `get_case` | read | Ja | AGENT | case_handler (Handläggaragent) |
| `get_company_metrics` | `bestand` | `get_company_metrics` | read | Nej | AGENT | actuary_agent (Aktuarieagent) |
| `get_insured_overview` | `kunddata` | `get_insured_overview` | read | Ja | AGENT | case_handler (Handläggaragent) |
| `get_portfolio_snapshot` | `bestand` | `get_portfolio_snapshot` | read | Nej | AGENT | actuary_agent (Aktuarieagent) |
| `get_premium_flows` | `bestand` | `get_premium_flows` | read | Nej | AGENT | actuary_agent (Aktuarieagent) |
| `get_premium_history` | `kunddata` | `get_premium_history` | read | Ja | AGENT | case_handler (Handläggaragent) |
| `get_product_parameters` | `regelverk` | `get_product_parameters` | read | Nej | AGENT | actuary_agent (Aktuarieagent), compliance_agent (Compliance-agent) |
| `get_salary_reports` | `kunddata` | `get_salary_reports` | read | Ja | AGENT | case_handler (Handläggaragent) |
| `get_valuation_basis` | `antaganden` | `get_valuation_basis` | read | Nej | AGENT | actuary_agent (Aktuarieagent) |
| `list_regulatory_documents` | `regelverk` | gateway `list_regulatory_documents` | read | Nej | – (gatewayens policy) | actuary_agent (Aktuarieagent), compliance_agent (Compliance-agent) |
| `list_valuation_bases` | `antaganden` | `list_valuation_bases` | read | Nej | AGENT | actuary_agent (Aktuarieagent) |
| `read_regulatory_document` | `regelverk` | gateway `read_regulatory_document` | read | Nej | – (gatewayens policy) | actuary_agent (Aktuarieagent), compliance_agent (Compliance-agent) |
| `register_salary_report` | `kunddata` | `register_salary_report` | write | Ja | APPROVAL | case_handler (Handläggaragent) |
| `set_policy_paid_up` | `kunddata` | `set_policy_paid_up` | write | Ja | APPROVAL | – |
| `write_draft` | `dokument` | gateway `write_draft` | write | Nej | – (gatewayens policy) | actuary_agent (Aktuarieagent), compliance_agent (Compliance-agent) |

Operationer utan poddmappning – stängda för alla agenter: `adopt_valuation_basis`, `amend_salary_case`, `close_case`, `count_approval_requests`, `create_case`, `enroll_insured_person`, `get_operation_events`, `list_approval_requests`, `list_cases`, `list_employers`, `list_insured_persons`, `propose_valuation_basis`, `register_employer`, `reject_valuation_basis`, `schedule_product_parameter_change`, `update_case_status`, `update_contact_details`, `update_current_salary`, `withdraw_product_parameter_change`.
<!-- list_skills.py: slut -->

## Planerade skills (ur ATT_GORA)

| Skill | Kategori | Kommentar |
|---|---|---|
| hämta-kunddata | data | PII – kräver behörighetslista (B-006). *Delvis täckt av läsoperationerna i podden `kunddata` ovan* |
| skriv-kundmail | kommunikation | Utskick kräver manuellt godkännande (§3.5) |
| tolka-itp1-fråga | regelverk | Bygger på `01_domän/ITP1_regelverk.md`; podden `regelverk` har en läsgateway sedan 3c-G (`list_regulatory_documents`, `read_regulatory_document`, `harness.md` §5.2), monterad på compliance och aktuarie sedan 3c-T |
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
- Körpolicy och skill-register: `src/agents/ecosystem.yaml`, `src/agents/skills.py`, `02_system/harness.md` §3–4
