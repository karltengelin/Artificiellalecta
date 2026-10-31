# OC-3a – rapportexport och uppdragsvyer

**Datum:** 2026-10-28. **Grund:** B-041, designstoppets §7, §9, §10 och §12.
Codex steg 2–3: lokal implementation. Riktig modell, riktiga teamrättigheter
i Postgres och Lakebase-aktivering verifieras i det samordnade röktestet.

## Ansluta frågefunktionen

Den vanliga webbstarten behåller läsvyerna och visar ett tydligt meddelande
om bolagsfrågornas adapter inte har anslutits. För en uttrycklig anslutning:

```powershell
python scripts/web/start_ui.py --db demo --company-questions --report-font-dir C:/lokala-typsnitt/dm-sans
```

Sökvägen ska innehålla de tre statiska DM Sans-filer som anges i
[rapportmallen](../06_design/rapportmall.md). Saknat typsnitt stoppar starten;
ingen nedladdning eller tyst reservfont används. Modeller och teamnycklar
kommer från det befintliga AI-lagret. Serverstarten gör inget modellanrop.
Operatörsinloggningen behöver redan vara konfigurerad enligt
[inloggningsdriften](operator_inloggning.md).

`web.database.build_question_services(settings, ai=..., renderer=...)` binder
en `QuestionConsole` till samma databas som arbetsytan och till dess betrodda
miljö-/datasetreferens. `create_app(..., question_console=...)` kan också ta
emot en uttryckligt byggd adapter, exempelvis i integrationstester. Ingen
testmodell väljs av verksamhetskoden.

Demo och webbens `svc_test` följer det befintliga handläggar-UI:ts konvention
med simulerad agentroll och särskild valideringsanslutning. Det anges i vyn;
det är inget prov av Postgres-rättigheterna. Mot Lakebase byggs aktuariens
tjänstelager med den riktiga begränsade rollen `agent_aktuarie`. Ingen betrodd
anslutning används som reserv för ett misslyckat agentanrop. Konton och
kolumnrättigheter skapas inte från webben. De samordnade rollproven och
Lakebase-rättigheterna återstår enligt designstoppet §11.

## Adresser och förlopp

| Yta | Adress |
|---|---|
| Fråga bolaget, team och uppdragslista | `/central/fragor` |
| Aktuariens uppdrag | `/team/aktuarie` |
| Samma detaljsida i centralen | `/central/fragor/<flow_id>` |
| Samma detaljsida i teamytan | `/team/aktuarie/<flow_id>` |
| Kontrollerad leverans | `<detaljadress>/leverans/1/rapport.pdf` eller `rapport.md` |

Båda arbetsytorna visar harnessens `AssignmentView`: beställare, skapad,
status, aktuellt steg, kostnad (okänd när den saknas), rapportversion och
granskningsstatus. Detaljens projektion och granskningshash byggs ur samma
lästa flödesversion. Svar och PDF visas sida vid sida på bred skärm och efter
varandra på smal. PDF kan också öppnas separat och Markdown hämtas.
Förhandsvisningen använder lokalt paketerad PDF.js med sidbläddring, zoom
och breddanpassning. Den läser samma kontrollsummeverifierade PDF genom
leveransrouten och behöver ingen inbyggd PDF-läsare i webbläsaren.
Inga rapportdata eller läsarfiler hämtas från en extern CDN.
JavaScript krävs för förhandsvisningen; länkarna till PDF och Markdown finns kvar
även om visningen inte kan laddas. Version, licens och kontrollsummor finns i
`src/web/static/PDFJS_README.md`.
Tidigare sparade PDF-leveranser skrivs inte om när renderaren ändras. En ny
beställning använder den aktuella layouten; befintliga rapporter behåller
sina bundna kontrollsummor och visas med sitt ursprungliga innehåll.

Endast `portfolio_overview` till `aktuarie` är tillgängligt. Formuläret erbjuder
de elva avslutade månaderna från adaptern och högst 500 tecken precisering.
Övriga konfigurerade team visas med adapterns tillgänglighet och skäl.
Frågan körs synkront till granskningsgrinden. Under tiden visas ett
arbetsmeddelande och startknappen spärras. Ett sessionsbundet engångs-id
stoppar också upprepad POST av samma formulär på servern; en slutförd
upprepning hänvisar till samma uppdrag. Nytt formulär ger en ny beställning.
Vid förlorat svar ska uppdragslistan kontrolleras före ny beställning.

Alla skrivvägar använder `operator_action`: verifierad serversession,
sessionsbunden CSRF och ursprungskontroll innan adaptern anropas. Aktören
kommer aldrig från formulär, `HANDLAGGARE_ID` eller en läsvy. Extra formulärfält,
exempelvis aktör eller miljö, avvisas. Läsning kräver ingen inloggning.

Granskning skickar flödesversion och `seen_hash` för det visade underlaget.
Ett gammalt eller ändrat underlag stoppas av motorn. Godkännande kör
leveranssteget; avslag kräver skäl och avslutar uppdraget. En ny beställning
kan hänvisa till det avslagna uppdraget. Avbrott och avstämning av
`reconciliation_required` går genom samma adapter och sessionskontroll.
Ingen automatisk omkörning införs i webbvyerna.

**Kvarstående integrationspunkt i harness:** `QuestionConsole` saknar i dag
en publik motsvarighet till `FlowConsole.mark_interrupted`. Vyn hanterar
`reconciliation_required` när harness har satt den statusen, men den nya
startvägen markerar inte själv kvarhängande `running`-steg efter processkrasch.
Den omstartskopplingen behöver samordnas med harnessägaren före drift;
webben går inte förbi adaptern till motorn. `src/agents` ändras inte här.

Leveranser läses endast genom `QuestionConsole.delivery`; webben öppnar inga
leveranssökvägar. Version och filnamn begränsas i routen. Båda filerna
kontrolleras innan granskningskontroller visas, och varje nedladdning
kontrolleras på nytt. Ändrad/saknad fil ger fel och spärrar granskningsvyn.
Motorns leveranskontroll skyddar även ett redan öppet granskningsformulär.
Sidor och filer har `Cache-Control: no-store`. Råa konversationer och
databasfel återges inte.

## Rapportens gräns och verifiering

[`render_report`](../src/reporting/report.py) är en ren export av den Markdown
som harness byggt. Struktur, sidbrytning, fontkrav och determinism beskrivs i
[rapportmallen](../06_design/rapportmall.md#oc-3a-deterministisk-markdown-till-pdf).
Lagring, kontrollsummor och godkännandestatus ägs fortsatt av harness.
PDF:en ändras inte efter beslut; granskare, tid och accepterad version visas
i uppdraget. En gammal rapport är sparat underlag från den tidigare läsningen.

`tests/test_web_questions.py` använder en testmodell, SQLite och den riktiga
PDF-renderaren med uttryckligt Helvetica. Fallen ur P2-FRAGA-001 omfattar
normalfallet (35 registrerade och 145 971,41 SEK i november 2025), tillgänglig
nolla, småcellsskydd, ogiltigt betaldatum, nekad åtkomst, källfel,
fråga utanför stödet och misslyckad export. Därutöver prövas identitet,
CSRF/ursprung, stängda team/månader, dubbla inskick, gammalt underlag,
avslag/ersättning, filändring, avbrott och samma projektion i båda ytorna.

`tests/test_reporting_report.py` prövar identiska bytes även vid samtidiga
exporter, automatisk sidbrytning utan förlorad text, långa tabellrader,
avvisade format och saknade typsnitt. Befintliga rapport-, webb-, mått- och
flödesprov används som regression via `scripts/testing/run_tests.py`.

Den visuella kontrollen använder syntetiskt underlag: formulär och granskning
i Edge, bred och smal skärm, samt renderade A4-sidor i Helvetica. Det är
en teknisk kontroll; riktig modell och DM Sans/Lakebase verifieras separat.

Slutkontroll på senaste hämtade `origin/main` (`4c404dd`) plus denna ändring:

| Urval | Resultat |
|---|---|
| `--changed --base origin/main --run` | 1 308 godkända, 82 bortvalda, 168,54 sekunder |
| `git diff --check` | Utan anmärkning |

Ändringen av testkatalogen väljer hela den befintliga lokala sviten, inklusive
berörda grupper och deras beroenden. Postgres-proven är bortvalda med
`not postgres`, inte godkända; ändringsplanen pekar inte ut något berört
Postgres-prov. Ingen databasroll, migration eller Lakebase-data har ändrats.
Kodläget är omtestat efter rättningen av sidbrytningen. Delade statusdokument
och ännu otestade målområden blir inte verifierade av detta resultat.

## Samordnad statusuppdatering

De delade filerna `MASTER_CONTEXT.md`, `BESLUTSLOGG.md` och `ATT_GORA.md`
redigeras inte i detta uppdrag (AGENTS.md §4.3). Förslag till samordningen:
markera Codex rendering och vyer som lokalt byggda/verifierade i ATT_GORA:s
rad *Närmast* och OC-3. Nästa steg är gemensamt röktest med riktig modell i
demo och `svc_test`, inklusive DM Sans, sedan Lakebase-rättigheter och
verifiering efter backup och operatörens OK. Inget nytt beslut föreslås.

## Röktest av webb och PDF 2026-10-31

Kört från den ordinarie webbstarten med `--db demo --company-questions`, de
tre lokala statiska DM Sans-filerna och konfigurerad riktig modell
`anthropic:claude-opus-5`. Aktuariens databasroll var simulerad.

Beståndsfrågan för december 2025 skapade **FLOW-000003**, körning
`run-18ef7c67922b`: ett anrop till `get_company_metrics`, två modellanrop,
35 registrerade försäkrade och 145 971,41 SEK. Kostnaden var 0,075955 USD.
Samma uppdrag följdes i centralens och aktuariens uppdragslistor, detaljvyer
och granskningsvy. Rapport v1 godkändes genom teamytan med den verifierade
operatörssessionen och visades därefter som *Levererad / Godkänd* i båda
listorna. Den kunde öppnas igen från centralen. PDF och Markdown från båda
arbetsytorna gav HTTP 200, `no-store` och samma kontrollsummor som manifestet.

Alla tre A4-sidor granskades visuellt mot rapportmallen. DM Sans var inbäddat;
tabell, radbrytning, marginaler och sidfot var läsbara utan överlappning.
Rapporttiteln förekom bara på första sidan. Den lokala PDF.js-visningen
fungerade i appens webbläsare, inklusive sidbläddring och zoom.

Röktestet hittade och rättade den svarta inbyggda PDF-vyn, den upprepade
rapporttiteln och ett klientfel när HTMX skickade textnoder till
förhandsvisningens städning. Sidbyte och återöppning verifierades därefter
utan nya konsolfel. Ett första modellanrop stoppades av exekveringssandboxens
nätverksskydd; demo-servern behövde uttrycklig nätverksåtkomst.

Regressionen kördes med `scripts/testing/run_tests.py --changed --base origin/main --run`.
Resultat: **389 godkända**, 103,27 sekunder, inklusive klientprovet för HTMX:s
textnoder. Ruff, JavaScript-syntax och `git diff --check` utan anmärkning.
Postgres-prov var bortvalda, inte godkända. Ingen körning mot `svc_test` eller
Lakebase ingick i denna webbkontroll. Delade statusfiler ändrades inte.
