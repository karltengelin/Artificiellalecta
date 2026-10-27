# AGENTS.md – Arbetsregler för Codex och gemensamma regler för parallellt AI-arbete

> Stående arbetsregler för Codex när den jobbar i detta projekt, plus de gemensamma reglerna som gäller
> när flera AI-verktyg (Claude Code/Cowork, Codex m.fl.) jobbar i repot samtidigt. Codex läser denna fil
> automatiskt vid sessionsstart. Claude Code läses in till den via `CLAUDE.md` §1.
>
> **Användning:** Vid sessionsstart, säg: *"Läs `AGENTS.md` och de tre filerna den hänvisar till. Bekräfta enligt instruktionen och säg när du är redo."*
>
> **Ändringar:** Föreslå nya regler eller justeringar via diff – godkänns och committas som vilken annan ändring som helst. Gör inte ändringar i denna fil på eget initiativ.

---

## 1. Innan du börjar

Läs dessa filer i ordning:

1. `MASTER_CONTEXT.md` – projektets fundament (vision, scope, arkitekturprinciper, mappstruktur)
2. `BESLUTSLOGG.md` – alla fattade beslut med motivering. Refereras med beteckningar som B-008, B-015 etc.
3. `ATT_GORA.md` – backlog och prioriteringar

Kontrollera även repo-tillståndet. Om det finns ocommittade ändringar, oväntade filer, andra aktiva
worktrees/branches eller något som ser konstigt ut – fråga innan du fortsätter.

## 2. Bekräfta förståelse

Innan du börjar bygga eller skriva något, sammanfatta kort:

- Projektets syfte (en mening)
- De viktigaste arkitekturprinciperna (3–5 punkter)
- Vad som prioriteras närmast (ur ATT_GORA hög prioritet)

Steget är medvetet inlagt – fel som upptäcks här är billigare att rätta än fel som byggs in i kod eller dokument. När rutinen sitter och det är uppenbart att du har koll kan operatören säga "skippa bekräftelsen den här gången".

## 3. Arbetsregler (Codex-specifika, motsvarar CLAUDE.md §3)

- **Redovisa ändringar vid commit.** Inom den överenskomna uppgiften får Codex ändra filer, committa och pusha på sin egen arbetsbranch utan ett separat godkännandesteg. Redovisa ändringarna med diff eller sammanfattning och commit-meddelande i rapporten efter committen. Merge till `main` kräver däremot operatörens uttryckliga OK i chatten för just den mergen (§4.6).
- **Commit-meddelanden.** Kort rubrik som säger vad ändringen gör. Använd kategori-prefix där det passar – t.ex. `skelett:`, `dokumentation:`, `skill:`, `agent:`, `regelverk:`. Ange det använda commit-meddelandet tillsammans med diffen eller sammanfattningen i rapporten.
- **Följ B-015 (mappstruktur).** Dokumentation på svenska i numrerade mappar i roten. Kod under `src/` med engelska namn. Inga svenska tecken i Python-modulnamn.
- **Följ B-012.** Allt skrivs som Markdown. PDF eller andra format genereras bara vid behov.
- **Föreslå – logga inte själv.** När du tycker att ett beslut bör in i `BESLUTSLOGG.md`, formulera förslaget och vänta på operatörens godkännande. Skriv aldrig in nya poster där på eget bevåg.
- **`DEMO_ANTECKNINGAR.md` lever separat.** Uppdatera den filen bara om operatören uttryckligen ber om det.
- **Externa konton sätts upp manuellt av operatören.** Om en uppgift kräver Supabase, Databricks, Google Workspace eller liknande externa tjänster – avbryt och be operatören göra den biten. Du kan inte skapa konton åt operatören.
- **Konsistenskontroll efter ändringar.** Många fakta beskrivs på flera ställen (teknisk stack i både MASTER_CONTEXT och README, tabeller i `databasschema.md`, agentstatus i `agentkarta.md`, filhänvisningar i flera dokument). Efter varje ändring – särskilt när ett beslut ersätter ett tidigare (som B-018 ersatte B-014) – sök igenom repot efter referenser till det som ändrats och rätta inaktuella omnämnanden i samma commit-grupp. Om en drift upptäcks som inte hör till aktuell uppgift: flagga den, åtgärda inte utan godkännande.
- **Hemligheter aldrig i repot.** API-nycklar, lösenord och connection strings hör hemma i `.env` (gitignorerad). `.env.example` dokumenterar *vilka* variabler som behövs, aldrig deras värden. Om du ser något som ser ut som en hemlighet i en fil som ska committas – stoppa och flagga.
- **Git-skrivningar tillåtna på egen branch.** Codex får köra `add`, `commit` och `push` direkt på sin egen arbetsbranch utan att vänta på godkännande i förväg. Merge till `main` görs också av Codex själv, men bara efter ett explicit muntligt OK i chatten (t.ex. "mergea det") – inget manuellt `git`-kommando krävs av operatören. Force-push och historieomskrivning (`reset --hard`, `rebase` av redan pushad historia) körs ändå aldrig utan explicit instruktion för just den åtgärden. Om stale lockfiler, korrupt index eller annat miljöspecifikt gitproblem dyker upp – stoppa omedelbart, flagga det till operatören, och återställ inte den här regeln på eget bevåg.

---

## 4. Parallellt arbete med flera AI-verktyg (gemensamt för Claude Code och Codex)

Gäller när Claude Code/Cowork och Codex (eller fler AI-verktyg) jobbar i repot samtidigt, i separata
worktrees mot samma GitHub-repo (`karltengelin/Artificiellalecta`).

### 4.1 Branch per uppgift
Varje agent jobbar på en egen namngiven branch (`claude/<uppgift>`, `codex/<uppgift>`), aldrig direkt
mot `main`. Detached HEAD är okej under själva arbetet om verktyget föredrar det (Codex gör detta som
standard), men branchen ska namnges innan arbetet lämnas över till operatören för integration – annars
riskerar commits att bli svåra att hitta tillbaka till.

### 4.2 Uppdelning efter beroenden, inte bara filer/mappar
Innan två agenter sätts på parallella uppgifter: kontrollera om uppgifterna delar datamodeller,
API-kontrakt eller andra funktionella beroenden – inte bara om de råkar redigera samma mappar. Två
ändringar kan vara textmässigt oberoende men funktionellt oförenliga (t.ex. kapitalförvaltning och
handläggar-UI som båda rör samma datamodeller). Respektera fasplanens egna beroenden – t.ex. blockerar
Fas 3 (AI-abstraktionslagret) all agentkod, så ingen agent ska sättas på Fas 5 innan Fas 3 är klar.
Vid osäkerhet, fråga operatören innan start.

### 4.3 Delade dokument (MASTER_CONTEXT.md, BESLUTSLOGG.md, ATT_GORA.md)
Simultan redigering av samma fil ger inte garanterat en git-konflikt, men risken är tyst motsägande
innehåll eller dubbla beslutsnummer. Om en annan agent samtidigt har ett öppet uppdrag som rör samma
område: redigera inte filen direkt – lägg föreslagna ändringar i din slutrapport till operatören istället.
Nya poster i `BESLUTSLOGG.md` loggas, som alltid, aldrig av en agent själv.

### 4.4 Synk innan beroende uppgift
En agent som påbörjar en uppgift som bygger vidare på en nyligen mergad branch ska själv hämta in den
uppdaterade `main` i sin worktree innan den börjar, inte anta att worktreen redan är ikapp. Kör relevanta
tester/kontroller även på det sammanslagna resultatet, inte bara på den egna branchen isolerat.

### 4.5 Databaskoordinering (Lakebase)
Migrationer, `create_tables`-körningar och seed-/genereringsskript mot den delade Lakebase-instansen
körs aldrig av två agenter samtidigt. Innan ett sådant skript körs: flagga det till operatören och
bekräfta att ingen annan agent kör mot samma databas just nu.

### 4.6 Integration till main
Egen branch sköts helt av agenten – commit och push kräver inget godkännande i förväg. Merge till `main`
görs också av agenten själv, men bara efter operatörens explicita muntliga OK i chatten för just den
mergen (t.ex. "mergea det"). Operatören behöver aldrig skriva eller klistra in `git`-kommandon själv.
Innan en merge: kontrollera att branchen är uppdaterad mot senaste `main` (§4.4) och att inget annat
pågående arbete i en annan agents branch berör samma filer på ett sätt som inte redan är känt.

### 4.7 Tester
Följ `02_system/teststrategi.md`. Kör tester med `scripts/testing/run_tests.py`, inte `pytest` direkt:
`--changed` under arbetet, berörda grupper med beroenden före leverans och hela den lokala sviten
inför integration när koden ändrats. När verktyget varnar att ändringen berör Postgres-prov körs de med
`--postgres` före leverans (B-040). En helkörning upprepas inte på samma redan verifierade kodläge.
Redovisa urval och resultat, och skilj bortvalda eller överhoppade prov från godkända.
