# Cowork-instruktioner – Artificiellalecta

> Stående arbetsregler för Claude när den jobbar i detta projekt via Cowork. Versioneras tillsammans med övrig projektdokumentation så reglerna inte behöver upprepas vid varje session.
>
> **Användning:** Vid sessionsstart, säg: *"Läs `.cowork-instruktioner.md` och de tre filerna den hänvisar till. Bekräfta enligt instruktionen och säg när du är redo."*
>
> **Ändringar:** Föreslå nya regler eller justeringar via diff – godkänns och committas som vilken annan ändring som helst. Gör inte ändringar i denna fil på eget initiativ.

---

## 1. Innan du börjar

Läs dessa filer i ordning:

1. `MASTER_CONTEXT.md` – projektets fundament (vision, scope, arkitekturprinciper, mappstruktur)
2. `BESLUTSLOGG.md` – alla fattade beslut med motivering. Refereras med beteckningar som B-008, B-015 etc.
3. `ATT_GORA.md` – backlog och prioriteringar

Kontrollera även repo-tillståndet. Om det finns ocommittade ändringar, oväntade filer eller något som ser konstigt ut – fråga innan du fortsätter.

## 2. Bekräfta förståelse

Innan du börjar bygga eller skriva något, sammanfatta kort:

- Projektets syfte (en mening)
- De viktigaste arkitekturprinciperna (3–5 punkter)
- Vad som prioriteras närmast (ur ATT_GORA hög prioritet)

Steget är medvetet inlagt – fel som upptäcks här är billigare att rätta än fel som byggs in i kod eller dokument. När rutinen sitter och det är uppenbart att du har koll kan jag säga "skippa bekräftelsen den här gången".

## 3. Arbetsregler

- **Diff före commit.** Visa alltid vad du tänker ändra (diff eller filinnehåll) innan du committar. Jag godkänner aktivt. Samma princip som MASTER_CONTEXT §3.5 "människa-i-loopen", applicerad på repot.
- **Commit-meddelanden.** Kort rubrik som säger vad ändringen gör. Använd kategori-prefix där det passar – t.ex. `skelett:`, `dokumentation:`, `skill:`, `agent:`, `regelverk:`. Föreslå alltid commit-meddelandet tillsammans med diff:en.
- **Följ B-015 (mappstruktur).** Dokumentation på svenska i numrerade mappar i roten. Kod under `src/` med engelska namn. Inga svenska tecken i Python-modulnamn.
- **Följ B-012.** Allt skrivs som Markdown. PDF eller andra format genereras bara vid behov.
- **Föreslå – logga inte själv.** När du tycker att ett beslut bör in i `BESLUTSLOGG.md`, formulera förslaget och vänta på mitt godkännande. Skriv aldrig in nya poster där på eget bevåg.
- **`DEMO_ANTECKNINGAR.md` lever separat.** Uppdatera den filen bara om jag uttryckligen ber om det.
- **Externa konton sätter jag upp manuellt.** Om en uppgift kräver Supabase, Google Workspace eller liknande externa tjänster – avbryt och be mig göra den biten. Du kan inte skapa konton åt mig. Guiden för Supabase finns i `ATT_GORA.md`.
- **Hemligheter aldrig i repot.** API-nycklar, lösenord och connection strings hör hemma i `.env` (gitignorerad). `.env.example` dokumenterar *vilka* variabler som behövs, aldrig deras värden. Detta täcks delvis av `.gitignore` men en explicit regel skyddar mot slarv. Om du ser något som ser ut som en hemlighet i en fil som ska committas – stoppa och flagga.
- **Inga git-skrivningar från Cowork-sandboxen.** Cowork-sandboxen är en Linux-mount mot Windows-repot, och git-writes (`add`, `commit`, `mv`, `rm`, `reset`) lämnar stale `index.lock`/`HEAD.lock` och korrupta indexfiler som operatören får städa manuellt. Claude ska skapa och redigera filer fritt, validera dem genom att köra kod, men **alla `git`-kommandon som muterar repot körs av operatören från cmd**. Läsande kommandon (`git log`, `git rev-parse`, `git show <ref>:<fil>`) är OK när de fungerar. Claude föreslår commit-grupper och commit-meddelanden i konversationen som operatören klistrar in.
