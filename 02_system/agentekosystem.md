# Agentekosystem

> **Typ:** Tvärgående arkitekturramverk (MASTER_CONTEXT §4b, B-024) – inte ett delprojekt utan det sätt alla delprojekt bygger agenter på
> **Status:** 🟡 Ramverket beslutat (**B-026**), byggs stegvis. AI-lagret som ekosystemet vilar på är byggt (`src/ai/`, se `ai_abstraktion.md`). Agent-runtime, skill-poddar och flödesmotor är ännu inte byggda – se byggordningen i §12.
> **Vidareutvecklar:** B-006, B-007, B-008, B-009, B-011, B-016, B-017

---

## 1. Syfte och designmål

Ramverket beskriver hur bolagets agenter organiseras, vilka förmågor de får, hur de samarbetar och hur de når AI-modellerna – så att varje delprojekt (MASTER_CONTEXT §4b) bygger sina agenter på samma sätt och flaggskeppsscenariot (§1) kan köras över avdelningsgränserna.

**Designmål:**

1. **Spegla ett riktigt bolag** – avdelningar med mandat och ansvar – utan att bryta B-008 (hellre fler skills än fler agenter).
2. **Spårbarhet och mänsklig kontroll** – varje agentkörning går att följa i efterhand, externa handlingar godkänns av operatören (B-016, §3.5).
3. **Behörighet styrs av struktur, inte av prompt** – vad en agent *kan* göra avgörs av vilka skills den har monterade, inte av vad dess instruktion säger (B-006, B-007).
4. **Modell- och leverantörsoberoende** – agenter väljer roller, aldrig modeller (B-009).
5. **Samma förmågor för alla** – operatören och externa AI-verktyg ska kunna använda samma skills som bolagets agenter (B-017, B-024).

---

## 2. Byggstenar

```
                         Operatör (Karl)
          Cowork · Claude Code · Codex · handläggar-UI (Fas 4)
               │                                   │
   startar flöden, godkänner steg,         använder skills direkt
   ger ad hoc-uppdrag till team             (MCP-exponerade poddar)
               │                                   │
   ┌───────────▼────────────┐                      │
   │ Flödesmotor (B-016)    │  deterministiska     │
   │ t.ex. regelförändring  │  steg + godkännande  │
   └─────┬────────────┬─────┘                      │
         ▼            ▼                            │
   ┌──────────┐ delegering ┌──────────┐            │
   │ Team A   │◄──────────►│ Team B   │   ...      │
   │ ledande  │ (via ledande│ ledande  │            │
   │ agent    │   agent)    │ agent    │            │
   │ + spec.  │             │          │            │
   └────┬─────┘             └────┬─────┘            │
        │   monterade skill-poddar                  │
        ▼                        ▼                  ▼
   ┌───────────────────────────────────────────────────────┐
   │ Skill-poddar: berakning · kunddata (PII) · regelverk · │
   │ bestand · marknadsdata · kommunikation · dokument …    │
   └───────────────────────────────────────────────────────┘
        │ alla modellanrop går via
        ▼
   AI-lagret src/ai/  →  Anthropic / OpenAI   (team-nycklar)
```

| Byggsten | Vad det är | Var det beskrivs/byggs |
|----------|-----------|------------------------|
| **Team** | En avdelning: mandat, ledande agent, ev. specialister, monterade poddar, nyckelscope, modellpolicy | §3 |
| **Agent** | En instans med mandat och instruktion som kör en agentloop mot AI-lagret | §4, `02_system/agenter/` |
| **Skill-pod** | Paket av relaterade skills med gemensam dataåtkomst och behörighetsklass – behörighetsenheten | §5, `03_skills/` |
| **Flöde** | Deterministisk, granskningsbar process över flera team med godkännandesteg | §6.2, `02_system/Agentsystem/` |
| **AI-lagret** | Modellagnostiskt lager med roller, nycklar och anropslogg | `ai_abstraktion.md`, `src/ai/` |

---

## 3. Team

### 3.1 Definition

Ett **team** motsvarar ett funktionsområde (MASTER_CONTEXT §4) och har:

- ett **mandat** – vad teamet ansvarar för och får besluta om,
- en **ledande agent** som tar emot uppdrag och orkestrerar teamets arbete,
- eventuella **specialistagenter** – bara när mandatet skiljer sig fundamentalt (B-008),
- **monterade skill-poddar** – teamets verktygslåda och behörighet,
- ett **team-id** (ASCII, gemener) som styr nyckelval och kostnadsuppföljning i AI-lagret,
- en **modellpolicy** – standardroller per agent.

### 3.2 Orkestreraren är teamets ledande agent

Varje team har en egen orkestrerare – men det är **teamets ledande agent**, inte en extra "chefsagent". En separat chef per team skulle fördubbla antalet agenter, lägga en överlämning med kontextförlust framför varje uppgift och bryta B-008.

- Den ledande agenten löser det mesta själv med teamets skills.
- Den delegerar till en specialist i teamet bara när uppgiften kräver specialistens mandat (t.ex. att utgående kundkommunikation formuleras av kommunikationsagenten).
- Ett enagentsteam har därmed ingen orkestreringskostnad alls.

**Teamets ytterdörr:** andra team, flöden och operatören når ett team via dess ledande agent – aldrig direkt till en specialist. Det ger en ansvarig per team och en tydlig behörighetsgräns. Undantag: eskalering till compliance-agenten är alltid tillåten (B-011).

**Ingen VD-agent i v1.** Operatören är högsta orkestrerare. Kända tvärgående processer körs av flödesmotorn (§6.2); ad hoc-samarbete sker via delegering mellan ledande agenter (§6.1).

### 3.3 Teamindelning

De tio befintliga agenterna (`agentkarta.md`) fördelas på sju team:

| Team-id | Team | Ledande agent | Specialister | Funktionsområde (MC §4) | Delprojekt |
|---------|------|---------------|--------------|-------------------------|------------|
| `forsakring` | Försäkring & kund | Handläggaragent | – | Kundadministration, ärendehantering | 1, 3, 7 |
| `kommunikation` | Kommunikation | Kommunikationsagent | – | Utgående kanaler (alla team) | 1, 7 |
| `kapital` | Kapitalförvaltning | Portföljförvaltningsagent | – | Kapitalförvaltning | 5 |
| `aktuarie` | Aktuarie & analys | Aktuarieagent | Data scientist-agent | Aktuariell verksamhet, analys/BI | 2, 6 |
| `compliance` | Regelefterlevnad & rapportering | Compliance-agent | Rapporteringsagent | Regelefterlevnad, rapportering | 4, 6 |
| `ekonomi` | Ekonomi & inköp | Ekonomiagent | Inköpsagent | Ekonomi, inköp | 6 |
| `utveckling` | Utveckling & plattform | Utvecklaragent | – | IT och dataplattform | Alla |

**Kommunikation som eget team:** kommunikationsagenten äger alla utgående kanaler på uppdrag av *alla* team (agentkarta §2). Som eget enagentsteam blir den bolagets enda väg ut – och därmed den naturliga platsen för godkännandesteget i §3.5. Alternativet att lägga den under `forsakring` skulle tvinga andra team att gå via handläggaragenten för att nå den.

**Internrevision** (MC §4) saknar agent. En internrevisionsfunktion måste vara oberoende av det den granskar och bör därför bli ett eget team när den byggs (öppen fråga, §13).

---

## 4. Agenter

### 4.1 Agentdefinition

En agent består, i linje med B-015, av:

- **Mandat och instruktion** i `02_system/agenter/<agent>.md` (finns som skelett för alla tio).
- **En körprofil** som runtime läser. Förslaget är en samlad fil `src/agents/ecosystem.yaml` med team, agenter och poddmontering – en enda källa för behörigheter som går att granska i en diff:

```yaml
teams:
  forsakring:
    lead: case_handler
    pods: [kunddata, berakning, regelverk, bestand, dokument]
agents:
  case_handler:
    name: Handläggaragent
    team: forsakring
    instruction: 02_system/agenter/handlaggaragent.md
    model_role: standard
    pods: [kunddata, berakning, regelverk]      # delmängd av teamets poddar
    delegates_to: [kommunikation, compliance]
    limits: {max_steps: 20, max_cost_usd: 0.50}
```

Agent-id är engelska `snake_case` (kod, B-015); visningsnamnet är svenskt. Det exakta formatet bestäms när runtime byggs (Fas 3b).

### 4.2 Agentloopen

Runtime kör en loop ovanpå AI-lagrets verktygsgränssnitt (`ai_abstraktion.md` §5.2):

1. **Bygg kontext:** systeminstruktion = agentens MD-instruktion + bolagskontext + datum. Uppdraget blir första användarmeddelandet.
2. **Bygg verktygslistan:** skills från agentens monterade poddar, filtrerade mot behörighet (§5). Agenten ser bara verktyg den får använda.
3. **Anropa modellen** via `ai.bind(team=…, agent=…, run_id=…).complete(...)` med agentens modellroll.
4. **Hantera verktygsanrop** enligt skillens sidoeffektsklass (§5.3): kör direkt, eller skapa ett godkännandeärende och stoppa.
5. **Lägg till resultat** och upprepa tills modellen är klar, stegtaket nås eller kostnadstaket för körningen nås.
6. **Journalför** varje steg (§4.3).

Historiken är append-only – inget tidigare meddelande redigeras eller tas bort under en körning. Det krävs för prompt caching och för att Anthropics tänkande-block ska accepteras.

### 4.3 Körjournal

Varje körning får ett `run_id` och en journal: uppdrag, varje verktygsanrop med indata och resultat, godkännanden, slutresultat, total kostnad, samt `parent_run_id` vid delegering. Journalen är den verksamhetsmässiga spårbarheten som B-016 kräver – vad agenten gjorde och varför. AI-lagrets anropslogg (`logs/ai_calls.jsonl`) är det tekniska lagret och länkas via `run_id`.

- **v1:** JSONL-fil per körning under `logs/agent_runs/`.
- **Senare:** tabeller `agent_runs`/`agent_steps` i Lakebase, så att handläggar-UI:t (Fas 4) kan visa vad en agent gjort, och så att manuella och automatiserade åtgärder lämnar samma spår (B-017).
- **Personuppgifter i journalen:** poddar med PII anger om resultat journalförs i klartext eller som referens (t.ex. försäkrings-id i stället för personnummer).

---

## 5. Skill-poddar

### 5.1 Definition

En **skill-pod** är ett namngivet paket av relaterade skills som delar:

- **dataåtkomst** – vilka tabeller, vyer eller mappar skillsen läser eller skriver,
- **behörighetsklass** – personuppgifter eller inte (B-006),
- **högsta sidoeffektsklass** – från ren beräkning till extern handling (§5.3),
- **ägarteam** – som ansvarar för poddens skills och deras dokumentation,
- **monteringslista** – vilka team/agenter som får montera podden.

Podden är **behörighetsenheten**: agenter får poddar, inte enskilda skills (enskilda skills kan däremot nekas). Det gör behörighetsgranskning hanterbar – sju team × ett tiotal poddar i stället för tio agenter × alla skills.

**Pod ≠ skillkategori.** Kategorin (`03_skills/data/`, `beräkning/` …) styr var dokumentationen ligger (B-015). Podden styr behörighet i körning. Exempel: `hämta-kunddata` (PII) och `marknadsdata` (ingen PII) ligger båda i kategorin `data` men i olika poddar. Varje skill hör till exakt en kategori och exakt en pod; skillkatalogen får en kolumn för pod när runtime byggs.

### 5.2 Skill-kontrakt

Varje skill-implementation deklarerar:

| Fält | Innehåll |
|------|----------|
| `name` | Engelska `snake_case` = Python-funktionens namn = verktygsnamnet mot modellen |
| `description` | Vad skillen gör och när den ska användas – läses av modellen (svenska går bra) |
| `input` | Pydantic-modell → `ToolSpec.from_model()` i AI-lagret ger ett strikt schema |
| `output` | JSON-serialiserbart resultat |
| `side_effect` | `read` / `compute` / `write` / `external` (§5.3) |
| `pii` | Om skillen hanterar personuppgifter |
| `pod` | Vilken pod skillen tillhör |

Befintliga skillen `calculate_itp1_premium` är ren beräkning (`compute`, ingen PII) och kan exponeras som verktyg genom att dess indata beskrivs som en Pydantic-modell – själva beräkningsfunktionen behöver inte ändras.

### 5.3 Sidoeffektsklasser och godkännande

| Klass | Exempel | Hantering |
|-------|---------|-----------|
| `read` | Hämta kunddata, slå upp regelverk, hämta kurser | Körs direkt, journalförs |
| `compute` | Premieberäkning, beståndsaggregat | Körs direkt, journalförs |
| `write` | Uppdatera internt ärende, skriva utkast till dokument | Körs direkt och journalförs; i compliance-kritiska flöden kan steget kräva godkännande |
| `external` | Mail till kund, rapportinlämning, transaktion, produktionssättning | **Körs aldrig direkt av en agent.** Runtime skapar ett godkännandeärende med utkastet; operatören godkänner, och först då utförs handlingen – av runtime, journalförd med godkännandet (§3.5) |

### 5.4 Föreslagna poddar

| Pod | Skills (befintliga/planerade) | PII | Högsta sidoeffekt | Ägarteam | Monteras på |
|-----|-------------------------------|-----|-------------------|----------|-------------|
| `berakning` | `beräkna-itp1-premie` | Nej | `compute` | aktuarie | Alla |
| `kunddata` | `hämta-kunddata` m.fl. | Ja | `write` | forsakring | forsakring (kommunikation: bara mottagaruppgifter) |
| `regelverk` | `tolka-itp1-fråga`, `complianceöversyn`, uppslag i källregister, tolkningar och produktregler (`04_regulatoriskt/`, `01_domän/produktregler/`) samt `05_styrdokument/` | Nej | `read` | compliance | Alla |
| `bestand` | Aggregerade nyckeltal om beståndet (antal, premievolym, kapital per segment) – ingen individdata | Nej | `compute` | aktuarie | Alla |
| `marknadsdata` | `marknadsdata` (Fas 2d) | Nej | `read` | kapital | kapital, aktuarie |
| `portfolj` | Allokering, rebalanseringsförslag, order | Nej | `external` | kapital | kapital |
| `kommunikation` | `skriv-kundmail` | Ja | `external` | kommunikation | kommunikation |
| `dokument` | Läsa/skriva Markdown i bolagsmappen, avgränsat per team | Nej | `write` | utveckling | Alla (med mappavgränsning) |
| `delegering` | `delegate_to_team` (§6.1) | Nej | `read` | utveckling | Ledande agenter |

`bestand` är nyckeln till flaggskeppets "business insight": den ger aggregerade svar utan att någon agent behöver personuppgifter, och är samma förmåga som BI-delprojektet (2) behöver.

---

## 6. Samverkan

### 6.1 Dynamisk delegering mellan team (B-016)

Ledande agenter får skillen `delegate_to_team(team, uppdrag)`. Uppdraget är **strukturerat** – för att motverka kontextförlusten som B-008 varnar för:

| Fält | Innehåll |
|------|----------|
| `goal` | Vad mottagaren ska åstadkomma |
| `background` | Det mottagaren behöver veta – sammanfattat, inte hela historiken |
| `constraints` | Avgränsningar, t.ex. "endast aggregerade siffror" |
| `expected_output` | Svarsform, gärna ett schema |
| `references` | Id:n och filvägar i stället för rådata (dataminimering, B-006) |

Runtime startar en barnkörning hos mottagarteamets ledande agent med `parent_run_id`, ärvt kostnadstak och ett djuptak (förslag: 2 nivåer). Svaret kommer tillbaka som verktygsresultat. Tillåtna mottagare deklareras per agent (`delegates_to`).

### 6.2 Orkestrerade flöden (B-016)

Flöden är **deterministisk kod**, inte en LLM som bestämmer ordningen. Ett flöde består av steg: vilket team, vilken indata (mappad från tidigare steg), förväntat utdataschema, och om steget kräver godkännande. Flödets tillstånd **persisteras**, eftersom ett godkännande kan dröja dagar.

Modellen är agent-factorys `Orchestrator`/`WorkflowStep` (steg, villkor, obligatoriska steg) – utökad med persisterat tillstånd, godkännandegrindar och strukturerade svar per steg i stället för fritext.

**Flaggskeppsflödet** (MC §1) som flöde över teamen:

| Steg | Team (roll) | Uppgift | Pod(ar) | Godkännande |
|------|-------------|---------|---------|-------------|
| 1 | compliance (`deep`) | Tolka regelverksändringen och gör konsekvensanalys – ny/ändrad tolkning `T-ITP1-…` i `04_regulatoriskt/tolkningar/` | regelverk, dokument | Ja |
| 2 | compliance (`deep`) | Föreslå ändrade produktregler `PR-ITP1-…` i `01_domän/produktregler/` och ev. villkor | regelverk, dokument | Ja |
| 3 | utveckling (`standard`) | Ändra kod/konfiguration (t.ex. premiemotorns åldersfönster), tester | dokument | Ja – operatören granskar ändringen innan produktionssättning |
| 4 | aktuarie (`deep`) | Beståndsinsikt: hur många berörs, effekt på premier och kapital | bestand, berakning | Nej (rapport) |
| 5 | kommunikation (`standard`) | Utkast till kundinformation, om relevant | kommunikation | Ja – externt utskick (§3.5) |

Det befintliga `02_system/Agentsystem/regelförändringsflöde.md` täcker steg 1, 3 och 5; steg 2 och 4 tillkommer med flaggskeppet. Dokumentkedjan källa → tolkning → produktregel följer arbetssättet i `projekt/04_produktregelverk/ARBETSSATT.md`.

---

## 7. Modellval

- **Agenter väljer roller, inte modeller.** Varje agent har en standardroll (`fast`/`standard`/`deep`, se `ai_abstraktion.md` §6.1); ett flödessteg kan överstyra den, och ett enskilt anrop likaså.
- **Riktlinje:**

| Arbete | Roll |
|--------|------|
| Routing, klassificering, extraktion, korta sammanfattningar | `fast` |
| Ledande agents ordinarie arbete med verktyg, utkast, handläggning | `standard` |
| Regeltolkning, konsekvensanalys, aktuariella bedömningar, granskning av andras arbete | `deep` |

- **Modellbyte är konfiguration** – `src/ai/ai_config.yaml` för permanenta ändringar, `AI_ROLE_<ROLL>` för tillfälliga.
- **Utvärdering:** samma uppgift körs med olika rollmappningar, och resultat och kostnad jämförs via anropsloggen. Fasta utvärderingsuppsättningar per agent/skill är en öppen fråga (§13).
- **Second opinion (option):** ett compliance-kritiskt steg kan köras på båda leverantörerna och avvikelser flaggas för operatören – ett praktiskt sätt att utnyttja modellagnostiken som kontrollmekanism.

---

## 8. Nyckelhantering och behörighet i data

**AI-nycklar per team** (detaljer i `ai_abstraktion.md` §7):

- Runtime binder varje körning till agentens team: `ai.bind(team="kapital", …)`. AI-lagret väljer då `ANTHROPIC_API_KEY_KAPITAL`/`OPENAI_API_KEY_KAPITAL` om de finns, annars den gemensamma nyckeln.
- Hos leverantörerna motsvaras ett team av ett Anthropic-*Workspace* och ett OpenAI-*Project*, med eget kostnadstak. Start: bara gemensamma nycklar.
- Agenter ser aldrig nycklar – de finns bara i AI-lagret.

**Behörighet i data – motsvarigheten för databasen:**

- Poddar som rör personuppgifter (`kunddata`) använder en egen Lakebase-roll med åtkomst bara till de tabeller de behöver; övriga poddar använder en roll som bara ser icke-personanknutna tabeller och aggregerade vyer.
- Därmed hindras en agent utan `kunddata`-podden från att nå personuppgifter även om dess instruktion skulle säga åt den – behörigheten ligger i strukturen, inte i prompten (designmål 3).
- Rollerna sätts upp av operatören i Databricks (externa konton, CLAUDE.md §3) när den första PII-podden byggs.

---

## 9. Exponering via MCP (B-017, B-024)

Varje pod kan exponeras som en **MCP-server** med samma skill-implementationer och samma behörighetsklass:

- **Operatören** använder bolagets skills direkt från Cowork eller Claude Code – samma förmågor som agenterna, med samma journalföring (B-017: manuella och automatiserade åtgärder lämnar samma spår).
- **Externa AI-verktyg** (Codex m.fl.) får som standard bara poddar utan personuppgifter.
- **En implementation, två ingångar:** agent-runtime och MCP-servern anropar samma Python-funktioner. Det uppfyller B-024:s mål att system och data ska vara tillgängliga för vilken AI-agent som helst, inte bara bolagets egna.

Byggs efter agent-runtime (§12).

---

## 10. Kostnad och budget

| Nivå | Mekanism |
|------|----------|
| Anrop | AI-lagret beräknar uppskattad kostnad per anrop och loggar den med team, agent och körning |
| Körning | Runtime summerar kostnaden och stoppar vid agentens `max_cost_usd` |
| Team | Kostnad per team ur anropsloggen; senare som indikator i BI (delprojekt 2) och företagsöversikten (delprojekt 8) |
| Hård spärr | Kostnadstak per workspace/projekt hos leverantören – gäller även om koden skulle fallera |

---

## 11. Lärdomar från agent-factory

| agent-factory | Här |
|---------------|-----|
| Orchestrator → Agents → Skills → Tools, inget korsanrop | Behålls i grunden; agenter anropar skills, skills anropar data – men delegering mellan team tillkommer, kontrollerat via ledande agenter |
| En global orkestrerare med fast pipeline (lambdas) | Två mönster (B-016): deterministiska flöden med persisterat tillstånd och godkännande, plus dynamisk delegering |
| Skills = LLM-drivna komponenter per agent | Skills = deklarerade förmågor (oftast ren kod) i delade poddar med behörighetsklass |
| Read-only som princip | Sidoeffektsklasser – bolaget måste kunna *göra* saker, men externa handlingar kräver godkännande |
| Agentregistrering via dekorator + YAML per agent | En samlad `ecosystem.yaml` för team, agenter och poddar – granskbar behörighet i en fil |
| `data_minimizer` sammanfattar data före LLM-anrop | Dataminimering genom poddar (aggregerade vyer, referenser i stället för rådata) och PII-styrd journalföring |
| Användningslogg per agent | Anropslogg per team, agent och körning + körjournal för verksamhetsspårbarhet |

---

## 12. Byggordning

| Fas | Innehåll | Möjliggör |
|-----|----------|-----------|
| **3** ✅ | AI-lagret (`src/ai/`) med roller, team-nycklar, verktygsgränssnitt, anropslogg, fejkleverantör | Allt nedan |
| **3b** | Agent-runtime v1: `ecosystem.yaml`, skill-register med kontrakt och behörighetsfilter, agentloop, körjournal (JSONL), godkännandekö (fil), första podden (`berakning`) | Fas 5 – handläggaragenten |
| **3c** | Delegering mellan team, flödesmotor med persisterat tillstånd (Lakebase-tabeller), regelförändringsflödet | Flaggskeppsscenariot |
| Senare | MCP-exponering av poddar, databas-sink för anropsloggen, kostnadsindikatorer, egen Lakebase-roll för PII-poddar | B-017/B-024 fullt ut, BI |

---

## 13. Öppna frågor

- **Internrevision:** eget oberoende team – när, och med vilka poddar (läsåtkomst till journaler och anropsloggar)?
- **Lagring av journal och godkännandekö** i Lakebase – tabellschema i `databasschema.md` när Fas 3c påbörjas.
- **Formatet för agentdefinitioner** – samlad `ecosystem.yaml` (förslag) eller körprofil i respektive agents MD-fil?
- **Utvärderingsuppsättningar** per agent/skill för att kunna byta modell med belägg.
- **Ledningsfunktion:** behövs en agent för tvärgående prioritering (VD-roll) – eller förblir operatören och flödesmotorn den rollen?
- **Godkännandegränssnitt:** fil/CLI i Fas 3b, handläggar-UI:t (Fas 4) på sikt.

---

## 14. Hänvisningar

- **B-026** – detta ramverk
- **B-025** – AI-lagret som ramverket bygger på
- **B-006/B-007** – behörighetsmodell och delat skillbibliotek (poddar är behörighetsenheten)
- **B-008** – få agenter (ledande agent som orkestrerare, inga chefsagenter)
- **B-011** – compliance-agenten tar emot eskaleringar från alla
- **B-016** – hybrid orkestrering (delegering + flöden)
- **B-017** – operatören som fullständig operatör (MCP-exponering)
- `02_system/ai_abstraktion.md`, `02_system/agentkarta.md`, `02_system/agenter/`, `02_system/Agentsystem/`, `03_skills/skillkatalog.md`
