# Demo-anteckningar – ITP1 Administrationsplattform

> Löpande logg av material som ska användas när projektet ska demonstreras. Här samlas case att gå igenom, nyckelmoment i utvecklingen, tekniska höjdpunkter, anekdoter, lärdomar och frågor som troligen kommer upp.
>
> **Format:** Lägg till löpande. Nya poster överst inom varje sektion. Markera med datum när relevant. Inget kastas - även det som verkar småaktigt nu kan bli en bra demoanekdot senare.

---

## 1. Demoformatets bärande idé

*(Skissas på allteftersom - vad är historien? Varför är detta intressant?)*

**Pitch i en mening (utkast):** Ett komplett tjänstepensionsbolag, från regelverk till kundkommunikation, byggt och drivet av AI-agenter - som visar både vad som funkar och vad som inte funkar när man försöker automatisera en hårt reglerad verksamhet.

**Uppdatering 2026-10-11 (B-024):** Visionen har vidgats från att bygga produkten till att visa upp ett **AI-native tjänstepensionsbolag** – agentteam gör det löpande arbete som avdelningarna i ett riktigt bolag gör, och system och data är byggda så att vilken AI-agent som helst kan arbeta mot dem. Flaggskeppet: en ändring i ett nationellt regelverk (t.ex. ändrad pensionsålder) går hela vägen till produktionssatt produktregel och en insikt om hur beståndet påverkas.

**Tänkt demoflöde (utkast):**
1. Sätta scenen - vad är ITP1, varför är det rätt scope, varför är det här en simulering
2. Genomgång av arkitektur - master context, beslutslogg, agentkarta
3. Live-case 1: regelförändringsflödet (se nedan) – *2026-10-11: utökat till flaggskeppsscenariot, från regeländring till produktion och beståndsinsikt*
4. Live-case 2: kundärende från fråga till godkänt svar
5. Bakom kulisserna - hur är detta byggt (se nyckelmoment)
6. Lärdomar och vad som är nästa steg

---

## 2. Case att dema

Konkreta scenarier att visa upp. Varje case ska kunna gå igenom från start till mål.

- [ ] **Case: Flaggskeppsscenariot – ändrad pensionsålder** *(B-024, B-026)* – compliance-teamet tolkar ändringen (tolkning `T-ITP1-…`) och föreslår ändrad produktregel (`PR-ITP1-…`), utvecklingsteamet ändrar premiemotorns åldersfönster med tester, aktuarieteamet tar fram en beståndsinsikt (hur många berörs, effekt på premier och kapital) och kommunikationsteamet förbereder kundinformation. Operatören godkänner vid varje kritiskt steg. Visar orkestrerade flöden (B-016) och teamstrukturen (B-026) i praktiken.
- [ ] **Case: Byt AI-leverantör mitt i ett ärende** *(B-025)* – kan visas redan nu med `scripts/smoke_test_ai.py`: en verktygsloop påbörjas hos OpenAI och avslutas hos Anthropic (och tvärtom), med bolagets riktiga premiemotor som verktyg. Båda räknar fram 10 708,13 kr. Visar att modellagnostiken inte bara är en princip på papper.
- [ ] **Case: Lagändring som påverkar produktregelverket** – regelförändringsflödet i praktiken. Hur compliance-agenten plockar upp förändringen, hur den koordinerar med utvecklaragenten, hur styrdokument uppdateras och hur kundkommunikation förbereds. Bra för att visa multi-agent-undantaget i B-008. *(2026-10-11: utökat till flaggskeppsscenariot ovan.)*
- [ ] **Case: Inkommande kundärende** – en anställd hör av sig med fråga om sin ITP1-pension. Hela vägen från inkommande mail till godkänt utskick. Visar handläggaragenten, skills-biblioteket, och människa-i-loopen-principen (3.5).
- [ ] **Case: Complianceöversyn körs på begäran** – visar den proaktiva skillen som scannar regelverk mot styrdokument och flaggar diskrepanser.
- [ ] **Case: Kvartalsrapport till FI** *(om vi hinner)* – hur agenter sammanställer underlag, vad människan signerar av.

*(Lägg till fler allteftersom de visar sig vara bra demomaterial)*

---

## 3. Nyckelmoment i bygget

Milstolpar och insikter värda att lyfta i demon. Logga **när de händer**, inte i efterhand.

- **2026-10-11 – Agentekosystemet (B-026)**. Sju team där den ledande agenten är teamets orkestrerare – ingen pyramid av "chefsagenter". Skill-poddar är behörighetsenheten: vad en agent *kan* göra styrs av strukturen, inte av vad prompten säger. Externa handlingar blir alltid godkännandeärenden.
- **2026-10-11 – AI-abstraktionslagret byggt (B-025)**. LiteLLM, OpenRouter och egen wrapper utvärderades; valet blev en egen tunn wrapper (ca 1 000 rader) ovanpå leverantörernas egna SDK:er. Agenter väljer roll (`fast`/`standard`/`deep`) i stället för modellnamn, och varje roll har reservmodell hos den andra leverantören. Första riktiga körningen: 12 av 12 kontroller gröna för under 20 öre.
- **2026-10-11 – Från produkt till AI-native bolag (B-024)**. Visionen vidgad, arbetet uppdelat i åtta delprojekt plus ett tvärgående agentramverk, och ett flaggskeppsscenario att bygga mot.
- **2026-10-11 – Claude Code och Codex jobbar parallellt (B-023)**. Gemensam `AGENTS.md`, branch per uppgift, merge till main bara på operatörens muntliga OK. Samma dag byggde Codex produktregler för uttag och paus medan Claude Code byggde AI-lagret – två AI-verktyg, ett repo, en operatör.
- **2026-07-12 – Premiemotorn och försäkringsmodellen (Fas 1, B-021/B-022)**. Premietrappan som deterministisk skill med 17 tester mot handräknade exempel, försäkring → förmåner → tillståndsperioder som i riktiga försäkringssystem, och genererad premiehistorik 2023–2026.
- **2026-07-12 – Paper trading i stället för riktiga pengar (B-019)** och handläggar-UI före kundportal (B-020). Två exempel på att välja den väg som ger mest lärande med minst risk.
- **2026-07-08 – Databasbyte från Supabase till Databricks Lakebase (B-018)**. Tack vare SQLAlchemy behövde inga modeller skrivas om – ett konkret kvitto på att abstraktionslager lönar sig, samma tanke som bakom B-009.
- **2026-05-15/16 – Hybrid orkestrering (B-016) och människan som fullständig operatör (B-017)**. Deterministiska flöden för det som måste gå att granska, dynamisk samverkan för resten – och allt en agent kan göra ska operatören också kunna göra.
- **2026-05-14 – Beslut B-008 ("hellre fler skills än fler agenter")**. Det här är en av de viktigaste arkitekturprinciperna och kommer påverka allt som byggs. Värt att förklara *varför* i demon: agent-till-agent-kommunikation tappar kontext, är dyrare, svårare att felsöka.
- **2026-05-14 – Fyrlagermodellen för regelefterlevnad (B-010)**. Speglar verklig pensionsbolagsstruktur. Bra exempel på att vi inte uppfinner något - vi översätter etablerad praxis till kod och dokument.
- **2026-05-14 – Modellagnostisk arkitektur (B-009)**. Värt att lyfta som arkitektonisk mognad: att inte låsa sig vid en leverantör är en lärdom från riktiga produktionssystem.

*(Lägg till löpande - varje viktigt beslut är en potentiell demopunkt)*

---

## 4. Tekniska höjdpunkter

Konkreta tekniska val som är värda att visa upp och förklara.

- **Modellagnostiskt AI-lager i praktiken (B-025)** – visa `src/ai/ai_config.yaml`: byt modell för en roll med en rad (eller tillfälligt med `AI_ROLE_DEEP=…`) utan att röra agentkod. Leverantörens interna resonemang följer med i historiken och återskapas i neutral form när en annan leverantör tar över. Varje anrop loggas med team, agent, tokens och uppskattad kostnad.
- **Team-nycklar (B-025/B-026)** – `ANTHROPIC_API_KEY_<TEAM>` ger varje avdelning ett eget Workspace/Project hos leverantören med eget kostnadstak. Spärra en nyckel och bara det teamet stannar.
- **Sidoeffektsklasser (B-026)** – varje skill deklarerar `read`/`compute`/`write`/`external`. `external` (mail, rapportinlämning, transaktion) körs aldrig direkt av en agent utan blir ett godkännandeärende.
- **Skillsbiblioteket med behörighetsmodell (B-007/B-006)** – varför skills och inte funktioner, varför inte alla agenter har tillgång till allt. GDPR-vinkeln. Kan visas som tabell: agent × skill = ja/nej.
- **Markdown som primärformat (B-012)** – varför inte Word, varför inte PDF. Visa hur samma fil läses av människa, AI och Git diff på en gång.
- **Separation av dokumentation (svenska) och kod (engelska) (B-015)** – konkret exempel på hur abstrakta beslut blir praktiska kompromisser.
- **Databricks Lakebase + SQLAlchemy (B-018, ersatte Supabase/B-014)** – varför managed och inte lokal databas, varför ORM och inte rå SQL. Speglar samma princip som AI-abstraktionen – och bevisades i praktiken när databasen byttes från Supabase till Lakebase utan att modellerna behövde skrivas om.
- **Versionerade arbetsregler för AI-agenterna** – spelreglerna (externa konton hanteras manuellt, föreslå-men-logga-inte, konsistenskontroll, hemligheter aldrig i repot, etc.) ligger i `CLAUDE.md` för Claude Code/Cowork och i `AGENTS.md` för Codex plus de gemensamma reglerna för parallellt arbete (B-023). Reglerna har utvecklats från "diff före commit" till att agenten committar på egen branch och redovisar diffen i samma svar, med merge till main först på operatörens muntliga OK. Demonstrerar att "instruktioner till AI" är en artefakt värd att versionera tillsammans med koden – inte muntliga regler som upprepas varje session. Reglerna utvecklas också iterativt: nya regler tillkommer när nya situationer dyker upp och vi inser att vi behöver ett förhållningssätt.

---

## 5. Anekdoter och aha-moment

Småhistorier från bygget. Det här är **guldet** i en demo - publik kommer ihåg berättelser, inte arkitekturdiagram.

*(Logga när de händer. Ingen är för liten.)*

- **2026-10-11** – Supply chain-attacken mot LiteLLM i mars 2026 (komprometterade versioner på PyPI som stal hemligheter) avgjorde valet av AI-lager: lagret som hanterar bolagets API-nycklar ska ha så få beroenden som möjligt. En nyhet från verkligheten som blev ett arkitekturbeslut.
- **2026-10-11** – Första riktiga AI-körningen: en konversation påbörjades hos OpenAI och bytte till Anthropic mitt i ett verktygsanrop – och båda räknade fram exakt samma premie (10 708,13 kr) med bolagets egen premiemotor. Hela testet kostade under 20 öre.
- **2026-10-11** – Kommunikationsagenten blev ett eget team. Den är bolagets enda väg ut mot kunder, och därmed den naturliga platsen för människa-i-loopen.
- **2026-07** – Innan databasbytet strulade Supabase: direktanslutningen var IPv6-only på free-tier och föll på vanliga svenska hemnät. Problemet hann aldrig lösas – B-018 bytte databas först.
- **2026-05-14** – Tidigt insåg vi att Pythons modulnamn inte klarar svenska tecken. Det tvingade fram beslutet att separera dokumentation och kod (B-015). Liten teknisk detalj som blev en arkitekturprincip.

---

## 6. Lärdomar

Saker som visade sig svårare eller lättare än väntat. Brutalt ärligt - även (särskilt) misslyckanden.

*(Fylls på allteftersom)*

- **2026-10-11 – Dokumentationsdrift är verklig.** Efter några månader stod redan loggade beslut fortfarande som "förslag", färdiga filer som "(kommer)", och Supabase nämndes långt efter bytet. Konsistenskontrollen i `CLAUDE.md` finns av en anledning – och måste köras aktivt efter varje ändring.
- **2026-10-11 – Testa mot leverantörens riktiga typer, inte egna mockar.** Adaptertesterna byggs med SDK:ernas egna svarstyper, och det fångade direkt att OpenAI:s SDK lagt till ett nytt obligatoriskt fält. Samma lärdom fanns redan i det tidigare experimentet agent-factory ("mockar vs verklighet").
- **2026-10-11 – Parallella AI-agenter krockar tyst, inte högljutt.** Beslutsnummer, `MASTER_CONTEXT.md` och main är delade resurser – två agenter kan skapa motsägelser utan att git säger ifrån (AGENTS.md §4.3). Det som hjälper: branch per uppgift, synk mot main före merge, och merge snart efter att ett beslut fattats.
- **2026-10-11 – Modellerna byts ut snabbare än koden.** Mellan agent-factory och Fas 3 hann leverantörerna släppa nya modellgenerationer. Därför väljer agenterna roller, inte modellnamn.

---

## 7. Frågor att förbereda svar på

Saker publiken sannolikt frågar. Förbereda svar i förväg gör demon mycket smidigare.

- **"Är ni inlåsta hos OpenAI eller Anthropic?"** → Nej (B-025). Agenter väljer roll, varje roll har reserv hos den andra leverantören – visat med byte mitt i en verktygsloop.
- **"Vad kostar det att köra?"** → Varje anrop loggas med uppskattad kostnad per team och agent; hela röktestet kostade under 20 öre. Hård spärr via kostnadstak per team-nyckel hos leverantören.
- **"Kan en agent skicka mail till en kund på egen hand?"** → Nej. Utskick är sidoeffektsklass `external` och blir ett godkännandeärende (B-026, §3.5).
- **"Varför inte LiteLLM eller OpenRouter?"** → B-025: supply chain-risk, en tredje part i dataflödet, och två leverantörer motiverar inte ett stort ramverk. Båda kan läggas till senare som adapter bakom samma gränssnitt.
- **"Hur ser ni till att AI:n inte hallucinerar fram fel försäkringsbelopp?"** → människa-i-loopen (3.5), behörighetsmodellen, deterministiska beräkningsskills för känsliga belopp.
- **"Skulle det här få drivas på riktigt?"** → Nej, och det är hela poängen. Sandbox/simulering (B-003). Diskutera vad som hade krävts (FI-tillstånd, kapitalkrav, riktig kund- och kapitalförvaltning).
- **"Vad händer när modellen ni bygger på blir utdaterad?"** → modellagnostisk arkitektur (B-009).
- **"Varför ITP1 och inte hela tjänstepensionsmarknaden?"** → B-002, scope-disciplin.
- **"Är det här inte bara en chatbot med extra steg?"** → Nej, och kan förklaras med behörighetsmodell, persistent databas, regelverksspårbarhet, multi-agent-flöden.

---

## 8. Skärmdumpar och visualiseringar att samla

Lista över bilder/skärmdumpar/diagram att fånga in **medan** vi bygger - mycket lättare än att rekonstruera.

- [ ] Teamkarta: sju team, ledande agent och monterade skill-poddar (B-026)
- [ ] Röktestets utskrift med leverantörsbytet mitt i verktygsloopen (B-025)
- [ ] Kostnad per team och agent ur anropsloggen (`logs/ai_calls.jsonl`)
- [ ] Mappstrukturen i färdigt skick (träd-vy)
- [ ] Agentkarta (finns i `02_system/agentkarta.md` – komplettera med teamindelningen enligt B-026)
- [ ] Skillsbibliotek + behörighetsmatris
- [ ] Fyrlagermodellen visualiserad
- [ ] Live-flöde av ett kundärende (sekvensdiagram)
- [ ] Före/efter en regelförändring (vad uppdateras automatiskt, vad kräver mänsklig review)

---

## 9. Demo-tekniskt (när det börjar närma sig)

Praktiska saker att lösa när det är dags att faktiskt dema.

- [ ] Plattform: live i Cowork? Inspelad video? Hybrid?
- [ ] Backupplan om något kraschar live
- [ ] Tid: hur lång ska demon vara? (15 min / 30 min / 1h?)
- [ ] Publik: tekniska eller affärsfolk? Justera djup därefter.
