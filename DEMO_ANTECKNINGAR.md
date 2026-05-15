# Demo-anteckningar – ITP1 Administrationsplattform

> Löpande logg av material som ska användas när projektet ska demonstreras. Här samlas case att gå igenom, nyckelmoment i utvecklingen, tekniska höjdpunkter, anekdoter, lärdomar och frågor som troligen kommer upp.
>
> **Format:** Lägg till löpande. Nya poster överst inom varje sektion. Markera med datum när relevant. Inget kastas - även det som verkar småaktigt nu kan bli en bra demoanekdot senare.

---

## 1. Demoformatets bärande idé

*(Skissas på allteftersom - vad är historien? Varför är detta intressant?)*

**Pitch i en mening (utkast):** Ett komplett tjänstepensionsbolag, från regelverk till kundkommunikation, byggt och drivet av AI-agenter - som visar både vad som funkar och vad som inte funkar när man försöker automatisera en hårt reglerad verksamhet.

**Tänkt demoflöde (utkast):**
1. Sätta scenen - vad är ITP1, varför är det rätt scope, varför är det här en simulering
2. Genomgång av arkitektur - master context, beslutslogg, agentkarta
3. Live-case 1: regelförändringsflödet (se nedan)
4. Live-case 2: kundärende från fråga till godkänt svar
5. Bakom kulisserna - hur är detta byggt (se nyckelmoment)
6. Lärdomar och vad som är nästa steg

---

## 2. Case att dema

Konkreta scenarier att visa upp. Varje case ska kunna gå igenom från start till mål.

- [ ] **Case: Lagändring som påverkar produktregelverket** – regelförändringsflödet i praktiken. Hur compliance-agenten plockar upp förändringen, hur den koordinerar med utvecklaragenten, hur styrdokument uppdateras och hur kundkommunikation förbereds. Bra för att visa multi-agent-undantaget i B-008.
- [ ] **Case: Inkommande kundärende** – en anställd hör av sig med fråga om sin ITP1-pension. Hela vägen från inkommande mail till godkänt utskick. Visar handläggaragenten, skills-biblioteket, och människa-i-loopen-principen (3.5).
- [ ] **Case: Complianceöversyn körs på begäran** – visar den proaktiva skillen som scannar regelverk mot styrdokument och flaggar diskrepanser.
- [ ] **Case: Kvartalsrapport till FI** *(om vi hinner)* – hur agenter sammanställer underlag, vad människan signerar av.

*(Lägg till fler allteftersom de visar sig vara bra demomaterial)*

---

## 3. Nyckelmoment i bygget

Milstolpar och insikter värda att lyfta i demon. Logga **när de händer**, inte i efterhand.

- **2026-05-14 – Beslut B-008 ("hellre fler skills än fler agenter")**. Det här är en av de viktigaste arkitekturprinciperna och kommer påverka allt som byggs. Värt att förklara *varför* i demon: agent-till-agent-kommunikation tappar kontext, är dyrare, svårare att felsöka.
- **2026-05-14 – Fyrlagermodellen för regelefterlevnad (B-010)**. Speglar verklig pensionsbolagsstruktur. Bra exempel på att vi inte uppfinner något - vi översätter etablerad praxis till kod och dokument.
- **2026-05-14 – Modellagnostisk arkitektur (B-009)**. Värt att lyfta som arkitektonisk mognad: att inte låsa sig vid en leverantör är en lärdom från riktiga produktionssystem.

*(Lägg till löpande - varje viktigt beslut är en potentiell demopunkt)*

---

## 4. Tekniska höjdpunkter

Konkreta tekniska val som är värda att visa upp och förklara.

- **Skillsbiblioteket med behörighetsmodell (B-007/B-006)** – varför skills och inte funktioner, varför inte alla agenter har tillgång till allt. GDPR-vinkeln. Kan visas som tabell: agent × skill = ja/nej.
- **Markdown som primärformat (B-012)** – varför inte Word, varför inte PDF. Visa hur samma fil läses av människa, AI och Git diff på en gång.
- **Separation av dokumentation (svenska) och kod (engelska) (B-015)** – konkret exempel på hur abstrakta beslut blir praktiska kompromisser.
- **Supabase + SQLAlchemy (B-014)** – varför managed och inte lokal databas, varför ORM och inte rå SQL. Speglar samma princip som AI-abstraktionen.
- **Versionerade arbetsregler för AI-agenten** – Cowork-spelreglerna (diff-före-commit, externa konton hanteras manuellt, föreslå-men-logga-inte, etc.) flyttas på sikt till en `.cowork-instruktioner.md` i repo-roten. Demonstrerar att "instruktioner till AI" är en artefakt värd att versionera tillsammans med koden – inte muntliga regler som upprepas varje session. Reglerna utvecklas också iterativt: nya regler tillkommer när nya situationer dyker upp och vi inser att vi behöver ett förhållningssätt.

---

## 5. Anekdoter och aha-moment

Småhistorier från bygget. Det här är **guldet** i en demo - publik kommer ihåg berättelser, inte arkitekturdiagram.

*(Logga när de händer. Ingen är för liten.)*

- **2026-05-14** – Tidigt insåg vi att Pythons modulnamn inte klarar svenska tecken. Det tvingade fram beslutet att separera dokumentation och kod (B-015). Liten teknisk detalj som blev en arkitekturprincip.

---

## 6. Lärdomar

Saker som visade sig svårare eller lättare än väntat. Brutalt ärligt - även (särskilt) misslyckanden.

*(Fylls på allteftersom)*

---

## 7. Frågor att förbereda svar på

Saker publiken sannolikt frågar. Förbereda svar i förväg gör demon mycket smidigare.

- **"Hur ser ni till att AI:n inte hallucinerar fram fel försäkringsbelopp?"** → människa-i-loopen (3.5), behörighetsmodellen, deterministiska beräkningsskills för känsliga belopp.
- **"Skulle det här få drivas på riktigt?"** → Nej, och det är hela poängen. Sandbox/simulering (B-003). Diskutera vad som hade krävts (FI-tillstånd, kapitalkrav, riktig kund- och kapitalförvaltning).
- **"Vad händer när modellen ni bygger på blir utdaterad?"** → modellagnostisk arkitektur (B-009).
- **"Varför ITP1 och inte hela tjänstepensionsmarknaden?"** → B-002, scope-disciplin.
- **"Är det här inte bara en chatbot med extra steg?"** → Nej, och kan förklaras med behörighetsmodell, persistent databas, regelverksspårbarhet, multi-agent-flöden.

---

## 8. Skärmdumpar och visualiseringar att samla

Lista över bilder/skärmdumpar/diagram att fånga in **medan** vi bygger - mycket lättare än att rekonstruera.

- [ ] Mappstrukturen i färdigt skick (träd-vy)
- [ ] Agentkarta (när den finns)
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
