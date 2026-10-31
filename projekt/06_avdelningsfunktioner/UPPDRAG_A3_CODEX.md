# Uppdrag till Codex: A3 – aktuariens teamyta v1

> **Datum:** 2026-10-31 | **Beslut:** B-042 (val M, N), B-036, B-041 | **Branch:** `codex/aktuarie-teamyta-a3` från senaste main
> **Beställare:** operatören. **Samordning:** Claude bygger samtidigt A5 (beräkningsmotor och startbestånd)
> i `src/skills/calculation/`, `src/services/` och `01_domän/parametrar/` på en egen branch. Uppdragen
> delar inga filer.

## 1. Mål

Gör `/team/aktuarie` till aktuariens arbetsplats på befintliga data, enligt
[skissen](aktuarie-arbetsyta.html) och [planen](AKTUARIETEAM_PLAN.md) §5. En människa ska kunna
beställa, granska och hämta produktrapporten, läsa antagandebiblioteket och anta eller avslå
förslag till grunder. Hen ska också kunna ge aktuarieagenten uppdrag som i dag. Allt sker genom
samma adaptrar och tjänsteoperationer som agenten använder (B-017, B-028).

## 2. Sidor i v1

| Sida | Adress (förslag) | Innehåll | Källa |
|---|---|---|---|
| Översikt | `/team/aktuarie` | Gällande grunder per familj, senaste produktrapporter och uppdrag med status, väntande granskningar. FI-frister som statisk lista ur planen §2.4, märkt som plan | `list_valuation_bases`, `ProductReportConsole.list()`, `QuestionConsole.list("aktuarie")` |
| Rapporter | `/team/aktuarie/rapporter` och `/…/rapporter/<flow_id>` | Lista, beställ (år och precisering), detalj med steg, granskning (godkänn/avslå med anteckning), nedladdning av `rapport.md`/`rapport.pdf`, spåret *Så togs rapporten fram* | `ProductReportConsole` (`start`, `flow`, `decide`, `delivery`, `trace`) |
| Antaganden | `/team/aktuarie/antaganden` och `/…/antaganden/<kod>` | Grunder och kurvor med status, giltighet, beslut och kontrollsumma; detalj med antagandena i läsbar form (kurvan som tabell) | `list_valuation_bases`, `get_valuation_basis` |
| Antagande och avslag | formulär på detaljsidan för ett förslag | Anta med giltighetsdag och beslutsreferens, eller avslå med anteckning | `adopt_valuation_basis`, `reject_valuation_basis` (HUMAN_ONLY) |
| Uppdrag | befintliga sidor för bolagsfrågan | Flytta under `/team/aktuarie/uppdrag` eller behåll adressen; centralens sidor ändras inte | `QuestionConsole` |

Skissens övriga sidor (Värderingar, FTA-analys, Bokföringsunderlag, Scenarier, Data och kvalitet)
visas i menyn som inaktiva med orsaken *kräver värderingsmotorn (A6)*. De får inga påhittade tal
och ingen demoknapp (B-037).

## 3. Gränser

- **Webben anropar bara adaptrar och tjänstelagret.** Inga modeller, sessioner eller SQL i
  routerna. `ProductReportConsole` byggs i `src/web/__main__.py` på samma sätt som
  `QuestionConsole`: aktuariens tjänstelager, uttrycklig AI-klient och `reporting.render_report`.
- **Identitet:** beställning, granskning, antagande och avslag kräver verifierad operatörssession,
  sessionsbunden CSRF-token och engångstoken mot dubbelklick, som i `routes/questions.py`
  (B-041 val H–I). Aktören kommer ur sessionen, aldrig ur formuläret.
- **Bara teamets agent** nås i teamytan (B-036). Ingen styrfunktion för modell eller budget här.
- **Antagande är en människas beslut:** formuläret visar förslagets innehåll och kontrollsumma
  innan beslutet. Beslutsreferensen är obligatorisk. En garantigrund kan inte antas med
  retroaktiv giltighet; operationen stoppar, och felet visas som det är.
- **Design:** Digital klarhet (B-034), samma layout som handläggar-UI:t. Skissens tal är
  påhittade och ska inte återanvändas.

## 4. Filer

**Codex äger:** `src/web/**` (routes, templates, static, `__main__.py`, `app.py`) och
`tests/test_web_*` samt webbdokumentationen (`02_system/handläggar-ui.md`,
`02_system/fragekedja_webb.md` eller en ny `02_system/aktuarie_teamyta.md`).

**Ändras inte i uppdraget:** `src/agents/**`, `src/services/**`, `src/models/**`,
`src/skills/**`, `src/utils/agent_roles.py`. Behövs en ändring i en adapter eller operation
beskrivs den i slutrapporten, och Claude gör den. Delade dokument (MASTER_CONTEXT, ATT_GORA,
BESLUTSLOGG, AKTUARIETEAM_PLAN) redigeras inte; föreslagna ändringar hör till slutrapporten
(AGENTS.md §4.3).

## 5. Acceptans

1. Med demodatabasen och testleverantören kan en inloggad operatör:
   - beställa produktrapporten för 2025,
   - se rapporten i granskning och godkänna den,
   - ladda ner PDF:en.

   Webbtester mot FakeProvider visar flödet, som `tests/test_web_questions.py`.
2. Antagandesidan visar de sex startgrunderna med rätt status. Ett förslag som skapats i testet
   via tjänstelagret kan antas och avslås genom formulären. Utan session, med fel CSRF-token
   eller med en återanvänd engångstoken stoppas försöket och ingenting ändras.
3. Inga personuppgifter visas i teamytan. Talen kommer bara från operationerna.
4. Sidorna är kontrollerade i webbläsaren mot demodatabasen, även på smal skärm (375 px) utan
   sidledsrullning. Skärmbild bifogas i rapporten.
5. Testverktyget används enligt AGENTS.md §4.7: `--changed` under arbetet och hela den lokala
   sviten före leverans. Postgres-prov behövs inte, eftersom webben inte rör databasroller.

## 6. Slutrapport

Redovisa ändrade filer, nya adresser, testresultat och skärmbilder. Lista föreslagna ändringar i
delade dokument och eventuella behov i adaptrar eller operationer. Merge till main görs efter
operatörens OK.
