# Beslutslogg – ITP1 Administrationsplattform

> Löpande logg över beslut som fattas i projektet. Varje beslut har en motivering så att framtida Claude (och framtida du) förstår *varför* något bestämdes, inte bara *vad*.
>
> **Format:** Nya beslut läggs överst. Ändra inte gamla poster – om ett beslut ändras, lägg in ett nytt och referera till det gamla.

---

## Beslut

### B-016 | 2026-05-15 | Hybrid orchestration som agentarkitektur

**Beslut:** Agentsamverkan i systemet struktureras som en hybrid mellan två mönster:

- **Dynamisk samverkan** – agenter känner till varandras gränssnitt och kan anlita varandra ad hoc för ostrukturerade, oförutsägbara uppgifter i vardagsarbetet.
- **Orkestrerade flöden** – fördefinierade, sekventiella workflows för kända processer med tydliga triggers. Dokumenteras i `02_system/Agentsystem/`, en MD-fil per flöde.

Orkestrerade flöden används när processen (a) involverar flera agenter i en känd ordning, (b) är compliance-kritisk och måste vara granskningsbar, eller (c) kräver manuellt godkännande vid varje etapp.

**Motivering:**
- Regelverksförändringar, ORSA-processen och rapporteringscykler måste vara deterministiska och fullt spårbara – en tillsynsmyndighet ska kunna följa exakt vad som hände i vilken ordning. Det utesluter ren dynamisk samverkan för dessa processer.
- Dynamisk samverkan är tillräcklig och mer flexibel för ad hoc-uppgifter där utfallet inte är förutsägbart i förväg.
- Hybrid-modellen är etablerad best practice i multi-agent-system (jfr LangGraph, Autogen, CrewAI) och kombinerar spårbarhet med flexibilitet.

**Övervägda alternativ:**

*Alternativ 1: Ren dynamisk samverkan*
Agenter har kopplingar och avgör själva när och hur de anlitar varandra. Fördelar: flexibelt, hanterar oförutsedda situationer bra. Nackdelar: svårt att granska i efterhand, oförutsägbart beteende i compliance-kritiska processer, svårare att felsöka.

*Alternativ 2: Ren orkestrering*
Alla agentinteraktioner definieras i förväg som strukturerade flöden. Fördelar: maximalt spårbart och deterministiskt. Nackdelar: orimlig overhead för vardagsarbete, skalerar dåligt – varje ny interaktionstyp kräver ett nytt dokumenterat flöde.

**Konsekvenser:**
- `02_system/Agentsystem/` skapas för orkestrerade flöden (en MD-fil per flöde)
- Kända kandidater för orkestrerade flöden: regelförändringsflödet, ORSA-processen, rapporteringscykeln
- Varje orkestrerat flöde dokumenterar trigger, inblandade agenter, godkännandesteg och spårbarhetskrav

---

### B-015 | 2026-05-14 | Mappstruktur: dokumentation och kod separerade

**Beslut:** Projektets mappstruktur separerar dokumentation (svenska namn, numrerade mappar i roten) från Python-kod (i `src/`, engelska namn).

- **Dokumentation:** `01_domän/`, `02_system/`, `03_skills/`, `04_regulatoriskt/`, `05_styrdokument/` – svenska namn OK
- **Kod:** `src/agents/`, `src/skills/`, `src/models/`, `src/ai/`, `src/utils/` – engelska namn
- **Övrigt:** `tests/`, `data/`, `scripts/` på rotnivå

För skills och agenter används mönstret att *instruktion (MD)* ligger i dokumentationsmappen och *implementation (Python)* ligger i `src/`. En skill identifieras alltså av två filer:

- `03_skills/data/hämta-kunddata.md` (instruktion)
- `src/skills/data/get_customer_data.py` (implementation)

**Motivering:**
- Pythons modulnamn klarar inte svenska tecken (`å`, `ä`, `ö`) – `import skills.beräkning` är ogiltigt
- Att bygga ihop instruktion och kod i samma mapp (alternativ "skill = en mapp") fungerar inte med svenska kategorinamn
- Separationen bevarar svensk dokumentationsestetik utan att kompromissa med kodens importerbarhet
- Mappning mellan svenska och engelska kategorinamn dokumenteras i MASTER_CONTEXT §7

**Mappning skill-kategorier:**
| Dokumentation (sv) | Kod (en) |
|--------------------|----------|
| `03_skills/data/` | `src/skills/data/` |
| `03_skills/beräkning/` | `src/skills/calculation/` |
| `03_skills/kommunikation/` | `src/skills/communication/` |
| `03_skills/regelverk/` | `src/skills/regulatory/` |

**Konsekvenser:**
- `pyproject.toml` pekar på `src/` som paketrot
- `__init__.py` finns i alla Python-paket
- Skillkatalogen (`03_skills/skillkatalog.md`) listar både MD- och Python-filens sökväg per skill

---

### B-014 | 2026-05-14 | Supabase + SQLAlchemy som databaslager

**Beslut:** Som databas används **Supabase** (managed PostgreSQL i molnet). All databasåtkomst i Python sker via **SQLAlchemy** som ORM/abstraktionslager. Tabeller definieras som Python-klasser, inte som rå SQL.

**Motivering:**
- **Supabase free-tier** räcker för sandbox-skala (500 MB databas, 50 000 MAUs, obegränsade API-anrop) och kostar 0 kr
- Riktig PostgreSQL → projektmiljön speglar verkligheten (i linje med projektets simuleringssyfte)
- Inget Docker eller lokal serveruppsättning krävs
- Webb-UI för att kika på data direkt – bra för debugging och inspektion under utveckling
- **SQLAlchemy** abstraherar bort databasleverantören: schemat följer med vid byte. Samma princip som vår modellagnostiska AI-arkitektur (B-009)
- Schema-versionering via Alembic blir naturlig nästa steg

**Konsekvenser:**
- Skapa Supabase-konto och projekt (se ATT_GORA)
- Spara connection string och API-nycklar säkert – aldrig i Git (skäl till att `.gitignore` är prioriterat)
- All ny kod som rör data skrivs mot SQLAlchemy-modeller, inte direkt SQL
- Backup-strategi behövs på sikt (free-tier saknar automatisk backup)
- **Notera:** Projekt på free-tier pausas efter 7 dagars inaktivitet men kan startas manuellt igen utan dataförlust

---

### B-013 | 2026-05-14 | Git + GitHub som versionskontroll

**Beslut:** Git används som versionskontrollsystem. Hela projektets kodbas och dokumentation lagras i GitHub-repot [Artificiellalecta](https://github.com/karltengelin/Artificiellalecta.git). Cowork kopplas till repot via GitHub-connector.

**Motivering:**
- Git är de facto-standard – stort ekosystem, väl integrerat med Cowork och alla större verktyg
- GitHub ger versionshistorik, ändringsspårning och möjlighet till samarbete på sikt
- Markdown-filer (B-012) diffas bra i Git – passar perfekt med vår dokumentstrategi
- Cowork har inbyggd connector som möjliggör att agenter och utvecklare jobbar mot samma repo

**Konsekvenser:**
- All kod och alla dokument (inkl. MASTER_CONTEXT, beslutslogg, styrdokument, regelverk) versioneras i samma repo
- `.gitignore` måste sättas upp för att exkludera API-nycklar, `.env`-filer, databasfiler etc. (tas vid behov, separat post i ATT_GORA)
- Behöver besluta om branch-strategi senare (main + feature branches? Eller direkt mot main i tidigt skede?)

---

### B-012 | 2026-05-14 | Markdown som primärt informationsformat

**Beslut:** All information i projektet sparas i första hand som Markdown-filer. PDF (eller andra format) genereras från Markdown vid behov – när en människa ska läsa formella beslut, rapporter eller utskick.

**Motivering:**
- Markdown är ren text och därmed lätt för LLM att läsa och tolka, till skillnad från PDF som ofta har komplex struktur
- Markdown är versionskontrollerbart (fungerar väl med Git, diffar är läsbara)
- Markdown är mänskligt läsbart även i råform – ingen specialprogramvara krävs
- Markdown konverteras enkelt till PDF, HTML, DOCX vid behov (Pandoc, WeasyPrint m.fl.)
- PDF låser fast layout men förlorar semantisk struktur – passar leverans, inte arbete

**Konsekvenser:**
- Styrdokument, processbeskrivningar, regelverkstolkningar, agentinstruktioner, beslut, journalanteckningar skrivs alltid som Markdown
- En md→PDF-pipeline ska sättas upp för formell dokumentgenerering
- Mallar (styrdokumentsmallar etc.) skrivs som Markdown med metadata-block i toppen

---

### B-011 | 2026-05-14 | Compliance-agent äger både regelverk och styrdokument

**Beslut:** En enda compliance-agent ansvarar för både regelverkskunskap och styrdokumentsstruktur. Ingen separat styrdokuments-agent skapas.

**Motivering:**
- Regelverk och styrdokument är tätt sammankopplade – ändras en regel kan styrdokument behöva uppdateras, och vice versa
- Att splittra ansvaret skulle skapa agent-till-agent-kommunikation som vi vill undvika (se B-008)
- Skillsbiblioteket räcker för att täcka olika operationer (slå upp regelverk, granska styrdokument, kontrollera efterlevnad etc.)

**Konsekvenser:**
- Compliance-agenten får skills för både regelverksuppslag och styrdokumentshantering
- Andra agenter kan eskalera till compliance-agenten vid juridiskt tveksamma fall – ett av undantagen från B-008

---

### B-010 | 2026-05-14 | Fyrlagermodell för regelefterlevnad

**Beslut:** Regelefterlevnad i projektet struktureras i fyra lager:
1. **Regelverkskällor** (`04_regulatoriskt/`) – ursprungliga lagar, förordningar, föreskrifter
2. **Tolkningar** – översättning av regelverk till operativa konsekvenser för bolaget
3. **Styrdokument** (`05_styrdokument/`) – interna policies, riktlinjer, processer
4. **Operativt arbete** – det dagliga arbetet som agenter och människor utför

Styrdokument ska alltid referera tillbaka till de regelverk de implementerar.

**Motivering:**
- Speglar hur verkliga tjänstepensionsbolag arbetar (LTF/FFFS 2019:21 förutsätter denna struktur)
- Möjliggör spårbarhet – varje regel går att följa till sitt ursprung
- Skiljer på "vad lagen säger" och "vad vi har bestämt" – båda måste vara dokumenterade men inte i samma fil
- Förenklar uppdatering vid regelverksförändringar – tydligt vad som måste revideras

**Konsekvenser:**
- Två separata mappstrukturer i projektet: `04_regulatoriskt/` och `05_styrdokument/`
- Varje styrdokument ska ha standardiserad metadata i toppen (syfte, ägare, beslutas av, refererade regelverk, versionshistorik)

---

### B-009 | 2026-05-14 | Modellagnostisk arkitektur via abstraktionslager

**Beslut:** All kod som anropar AI-modeller ska gå via ett abstraktionslager, inte direkt mot en specifik leverantörs SDK. Det ska gå att byta modell eller leverantör (OpenAI ↔ Anthropic ↔ andra) genom konfiguration, utan att ändra agentkod eller skills.

**Motivering:**
- Undviker inlåsning hos en enskild leverantör
- Modeller utvecklas snabbt – nya, bättre eller billigare modeller kommer löpande
- Olika modeller passar olika uppgifter (en agent kan använda en kraftfull modell, en annan en billigare för enklare uppgifter)
- API-priser och tillgänglighet ändras över tid
- Möjliggör jämförande utvärdering av modellers prestanda inom projektet

**Konsekvenser:**
- Inga direktanrop till `openai.ChatCompletion` eller `anthropic.messages.create` i agent- eller skillkod
- Modellval, API-nyckel och provider hanteras via konfigurationsfil eller miljövariabler
- Prompter skrivs så generiskt som möjligt – leverantörsspecifika finesser kapslas in i abstraktionslagret
- Behöver utvärdera färdiga lösningar (LiteLLM, OpenRouter) eller bygga egen wrapper
- Lägg till `02_system/ai_abstraktion.md` för att specificera lagret

---

### B-008 | 2026-05-14 | Arkitekturprincip: hellre fler skills än fler agenter

**Beslut:** När en ny funktion ska byggas, default är att skapa en eller flera skills som en befintlig agent får tillgång till. Skapa inte en ny agent om det inte krävs ett distinkt mandat eller ansvar.

**Motivering:**
- Agent-till-agent-kommunikation riskerar att tappa kontext vid varje överlämning
- Multi-agent-flöden innebär fler LLM-anrop, vilket är dyrare och långsammare
- Färre agenter = enklare felsökning (tydligt vem som fattade vilket beslut)
- Skills är återanvändbara mellan agenter; en ny agent är en helt ny enhet att underhålla

**Undantag:** Multi-agent är motiverat när olika delar av arbetet kräver fundamentalt olika mandat (t.ex. handläggare som eskalerar till compliance), när parallellt arbete är meningsfullt, eller när det finns behörighetsskillnader.

---

### B-007 | 2026-05-14 | Delat skillsbibliotek med behörighetsmodell

**Beslut:** Alla skills ligger i ett centralt bibliotek (`03_skills/`). Varje agent har en deklarerad lista över vilka skills den får använda – inte alla agenter får tillgång till alla skills.

**Motivering:**
- Delat bibliotek undviker duplicering – en uppdatering slår igenom överallt
- Centralt index gör skills upptäckbara, så samma funktion inte byggs två gånger
- Behörighetsmodellen behövs för GDPR-efterlevnad och säkerhetshygien (se B-006)
- Tydlig agentdefinition: man ser direkt vad varje agent har för verktygslåda

---

### B-006 | 2026-05-14 | Skills med kunddataåtkomst ska ha begränsad behörighet

**Beslut:** Skills som hämtar, ändrar eller exponerar personuppgifter får inte vara tillgängliga för alla agenter. Varje sådan skill ska ha en uttrycklig lista över vilka agenter som är behöriga.

**Motivering:**
- GDPR: dataminimeringsprincipen kräver att endast den som faktiskt behöver data får åtkomst
- Exempel: Kapitalförvaltningsagenten behöver aggregerade portfölj­data, inte enskilda kunders personuppgifter
- Säkerhetshygien: minskar attackytan om en agent kompromiteras eller får felaktiga instruktioner
- Internrevision/spårbarhet: tydligt vem som hade rätt att se vad

---

### B-005 | 2026-05-14 | Hybrid dataarkitektur: databas + dokumentlager

**Beslut:** Strukturerad data (kunder, policys, transaktioner) lagras i en databas. Regler, processer, villkor och instruktioner lagras som textfiler.

**Motivering:**
- Speglar hur verkliga bolag arbetar
- Databas ger frågbarhet och dataintegritet för operativa flöden
- Dokumentlager ger versionerbara, läsbara regelverk som både människor och AI kan tolka

---

### B-004 | 2026-05-14 | Python som primärt programspråk

**Beslut:** All kod skrivs i Python där inte annat motiveras.

**Motivering:**
- Bred ekosystem för dataanalys, aktuariella beräkningar, API-integrationer
- Användarens preferens
- God Claude-kompetens i språket

---

### B-003 | 2026-05-14 | Sandbox/simulering, inga riktiga kunder

**Beslut:** Plattformen byggs som ett simulerat bolag med fiktiv data. Inga riktiga kunder eller riktigt kapital hanteras.

**Motivering:**
- Möjliggör experiment och felsteg utan reglerings- eller skaderisk
- Kringgår tillståndskrav från Finansinspektionen
- Möjliggör utveckling av processer som speglar verkligheten

---

### B-002 | 2026-05-14 | Scope begränsat till ITP1 ålderspension

**Beslut:** Endast ålderspension inom kollektivavtalet ITP1 ingår. Sjukpension, familjepension, ITPK, andra kollektivavtal och individuella lösningar är utanför scope.

**Motivering:**
- Begränsar komplexitet till en hanterbar nivå
- Möjliggör djupare detaljerings­grad inom ett tydligt avgränsat område
- ITP1 är en välanvänd och väldokumenterad produkt – bra för simulering

---

### B-001 | 2026-05-14 | Master-kontextdokument som projektets fundament

**Beslut:** `MASTER_CONTEXT.md` är det dokument som alla Claude-sessioner och agenter ska läsa först. Det innehåller vision, scope, arkitektur och status.

**Motivering:**
- Garanterar att varje ny session har samma utgångspunkt
- Förebygger drift och inkonsekvenser mellan sessioner
- Fungerar som onboardingdokument för framtida agenter

---

## Mall för nya beslut

```
### B-XXX | YYYY-MM-DD | [Kort titel]

**Beslut:** [Vad bestämdes]

**Motivering:**
- [Varför]
- [Varför]

**Konsekvenser:** [Vad det innebär praktiskt, om relevant]

**Ersätter:** [Referens till tidigare beslut om det är en ändring]
```
