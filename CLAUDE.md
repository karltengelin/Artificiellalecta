# Cowork-instruktioner – Artificiellalecta

> Stående arbetsregler för Claude när den jobbar i detta projekt via Cowork. Versioneras tillsammans med övrig projektdokumentation så reglerna inte behöver upprepas vid varje session.
>
> **Användning:** Vid sessionsstart, säg: *"Läs `CLAUDE.md` och de tre filerna den hänvisar till. Bekräfta enligt instruktionen och säg när du är redo."*
>
> **Ändringar:** Föreslå nya regler eller justeringar via diff – godkänns och committas som vilken annan ändring som helst. Gör inte ändringar i denna fil på eget initiativ.

---

## 1. Innan du börjar

Läs dessa filer i ordning:

1. `MASTER_CONTEXT.md` – projektets fundament (vision, scope, arkitekturprinciper, mappstruktur)
2. `BESLUTSLOGG.md` – alla fattade beslut med motivering. Refereras med beteckningar som B-008, B-015 etc.
3. `ATT_GORA.md` – backlog och prioriteringar
4. `AGENTS.md` – gemensamma arbetsregler när flera AI-verktyg (Claude Code/Cowork, Codex m.fl.) jobbar parallellt i repot

Kontrollera även repo-tillståndet. Om det finns ocommittade ändringar, oväntade filer eller något som ser konstigt ut – fråga innan du fortsätter.

## 2. Bekräfta förståelse

Innan du börjar bygga eller skriva något, sammanfatta kort:

- Projektets syfte (en mening)
- De viktigaste arkitekturprinciperna (3–5 punkter)
- Vad som prioriteras närmast (ur ATT_GORA hög prioritet)

Steget är medvetet inlagt – fel som upptäcks här är billigare att rätta än fel som byggs in i kod eller dokument. När rutinen sitter och det är uppenbart att du har koll kan jag säga "skippa bekräftelsen den här gången".

## 3. Arbetsregler

- **Diff i samma svar som committen.** Visa vad som ändrades (diff eller sammanfattning) i samma rapport som du gör committen i – inte som ett separat godkännandesteg innan. Jag kan alltid be dig backa en commit om något är fel.
- **Commit-meddelanden.** Kort rubrik som säger vad ändringen gör. Använd kategori-prefix där det passar – t.ex. `skelett:`, `dokumentation:`, `skill:`, `agent:`, `regelverk:`. Föreslå alltid commit-meddelandet tillsammans med diff:en.
- **Följ B-015 (mappstruktur).** Dokumentation på svenska i numrerade mappar i roten. Kod under `src/` med engelska namn. Inga svenska tecken i Python-modulnamn.
- **Följ B-012.** Allt skrivs som Markdown. PDF eller andra format genereras bara vid behov.
- **Föreslå – logga inte själv.** När du tycker att ett beslut bör in i `BESLUTSLOGG.md`, formulera förslaget och vänta på mitt godkännande. Skriv aldrig in nya poster där på eget bevåg.
- **`DEMO_ANTECKNINGAR.md` lever separat.** Uppdatera den filen bara om jag uttryckligen ber om det.
- **Externa konton sätter jag upp manuellt.** Om en uppgift kräver Supabase, Google Workspace eller liknande externa tjänster – avbryt och be mig göra den biten. Du kan inte skapa konton åt mig. (Supabase-guiden i `ATT_GORA.md` är arkiverad – databasen är Databricks Lakebase, B-018.)
- **Konsistenskontroll efter ändringar.** Många fakta beskrivs på flera ställen (teknisk stack i både MASTER_CONTEXT och README, tabeller i `databasschema.md`, agentstatus i `agentkarta.md`, filhänvisningar i flera dokument). Efter varje ändring – särskilt när ett beslut ersätter ett tidigare (som B-018 ersatte B-014) – sök igenom repot efter referenser till det som ändrats och rätta inaktuella omnämnanden i samma commit-grupp. Om en drift upptäcks som inte hör till aktuell uppgift: flagga den, åtgärda inte utan godkännande.
- **Hemligheter aldrig i repot.** API-nycklar, lösenord och connection strings hör hemma i `.env` (gitignorerad). `.env.example` dokumenterar *vilka* variabler som behövs, aldrig deras värden. Detta täcks delvis av `.gitignore` men en explicit regel skyddar mot slarv. Om du ser något som ser ut som en hemlighet i en fil som ska committas – stoppa och flagga.
- **Git-skrivningar tillåtna på egen branch.** Claude Code får köra `add`, `commit` och `push` direkt på sin egen arbetsbranch utan att vänta på godkännande i förväg. Merge till `main` görs också av Claude Code själv, men bara efter ett explicit muntligt OK i chatten (t.ex. "mergea det") – inget manuellt `git`-kommando krävs av operatören. Force-push och historieomskrivning (`reset --hard`, `rebase` av redan pushad historia) körs ändå aldrig utan explicit instruktion för just den åtgärden. Om stale lockfiler, korrupt index eller annat miljöspecifikt gitproblem dyker upp – stoppa omedelbart, flagga det, och återställ inte den här regeln på eget bevåg.
