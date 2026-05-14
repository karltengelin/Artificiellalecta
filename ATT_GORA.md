# Att-göra-lista – ITP1 Administrationsplattform

> Löpande backlog över saker som ska göras, byggas eller utredas. Strukturerad efter prioritet och område.
>
> **Format:** Markera klart med ✅. Lägg till datum och kort kommentar när något genomförs. Saker som inte längre är aktuella stryks ej – arkiveras längst ned.

---

## 🔴 Hög prioritet – grunden

- [ ] **Skriva `02_system/agentkarta.md`** – översikt över alla planerade agenter, deras mandat och vilka skills de har tillgång till
- [ ] **Skriva `03_skills/skillkatalog.md`** – översikt över alla skills, syfte, kategori och behörighetslista
- [ ] **Bygga ut `04_regulatoriskt/`** – bryta ner regelverkskartan i underdokument per regelverk (LTF, FFFS:er, DORA, GDPR, IDD, SFDR, AI-förordningen, skatt)
- [ ] **Skapa styrdokumentsstruktur** i `05_styrdokument/` – skriva `styrdokumentshierarki.md` som definierar struktur, ägarskap, revisionscykel och standardmetadata för alla styrdokument
- [ ] **Definiera databasschema** – tabellstruktur för kunddata (`02_system/databasschema.md`). Skrivs som SQLAlchemy-modeller (se B-014)
- [ ] **Sätta upp Google-konto** för det fiktiva bolaget (Gmail, Calendar, Drive)
- [ ] **Skapa Supabase-konto och projekt** för databasen

### Guide: Skapa Supabase-projekt

1. Gå till **supabase.com** och klicka på *Start your project* (eller *Sign in* om du redan har konto)
2. Logga in – enklast via GitHub-kontot du redan har (då hänger projekten ihop) eller via e-post
3. Klicka på *New project*. Välj vilken organisation det ska tillhöra (din egen personliga räcker)
4. Fyll i:
   - **Project name:** `Artificiellalecta` (eller liknande)
   - **Database password:** Generera ett starkt lösenord. **Spara det säkert** (lösenordshanterare) – det går inte att se igen efteråt
   - **Region:** Välj `Europe (Stockholm)` eller `Europe (Frankfurt)` – närmast = snabbast
   - **Pricing plan:** Free
5. Vänta ~2 minuter medan projektet sätts upp
6. När det är klart, gå till **Project Settings → API**. Spara följande (men lägg dem ALDRIG i Git):
   - **Project URL** (ser ut som `https://xxxxx.supabase.co`)
   - **anon public key** (för läsåtkomst)
   - **service_role key** (för full åtkomst – behandlas som lösenord)
7. Gå till **Project Settings → Database** och spara **connection string** (för SQLAlchemy)

**Tips:** Logga in i projektet minst en gång i veckan så pausas det inte. Eller acceptera att det pausas – det räcker att klicka *Restore project* om så händer.

---## 🟡 Medium prioritet – domänkartläggning

- [ ] **Specificera AI-abstraktionslagret** i `02_system/ai_abstraktion.md` – utvärdera LiteLLM/OpenRouter vs egen wrapper, definiera gränssnitt
- [ ] **Kartlägga processer** i `01_domän/processer_översikt.md` (kundärenden, premiehantering, rapportering, etc.)
- [ ] **Skriva ut försäkringsvillkor** för ITP1 ålderspension i `01_domän/försäkringsvillkor.md`
- [ ] **Dokumentera aktuariell grund** – antaganden, tabeller, beräkningsmodeller
- [ ] **Beslut om databas** – välja konkret databas (PostgreSQL föreslaget)

## 🟢 Lägre prioritet – när grunden står

- [ ] **Sätta upp md→PDF-pipeline** – välja verktyg (Pandoc eller WeasyPrint), definiera mallar för formella dokument (rapporter, kundbrev, styrelseprotokoll)
- [ ] **Standardmall för officiella dokument** – logga, sidhuvud/sidfot, signaturplats, sidnumrering, dokument-ID, versionsinfo. Tas i samband med PDF-pipelinen
- [ ] **Bygga första agent: Handläggaragent** (ärendehantering)
- [ ] **Bygga första skills:** `hämta-kunddata`, `skriv-kundmail`, `tolka-itp1-fråga`
- [ ] **Sätta upp koppling Cowork ↔ Gmail** (MCP)
- [ ] **Generera testdata** – fiktiva kunder, policys, transaktioner

## 💭 Att utreda / oklart

- [ ] **Git branch-strategi** – kör main direkt i tidigt skede, eller feature branches + PR redan från start?
- [ ] Hur ska godkännandeflöden fungera (mail till kund ska godkännas innan utskick)?
- [ ] Loggning och spårbarhet – hur sparas agentbeslut?
- [ ] Backup-strategi för databas och dokument

---

## ✅ Klart

- [x] **2026-05-14** Skriva MASTER_CONTEXT.md
- [x] **2026-05-14** Skapa beslutslogg
- [x] **2026-05-14** Skapa att-göra-lista (detta dokument)
- [x] **2026-05-14** Ta emot regelverkskarta som grund för `04_regulatoriskt/`
- [x] **2026-05-14** Koppla Cowork till GitHub-repot Artificiellalecta via connector
- [x] **2026-05-14** Lägga upp grunddokumenten i repot (MASTER_CONTEXT, BESLUTSLOGG, ATT_GORA, regelverkskarta) som första commit
- [x] **2026-05-14** Skriva `.gitignore` – exkludera API-nycklar, `.env`, databasfiler, cache, virtuella miljöer m.m.

---

## 🗄️ Arkiv

*(Inga arkiverade poster ännu)*
