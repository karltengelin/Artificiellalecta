# Företagsöversikt – uppdatering 24 oktober 2026

Översikten i [foretagsoversikt.html](foretagsoversikt.html) har jämförts med den
bifogade äldre HTML-versionen och uppdaterats mot senaste hämtade `main`,
commit `fb38590`. Sidans upplägg och klickbara karta är bevarade.
Detta dokument är uppdateringens Markdown-underlag; HTML är den visuella leveransen.

## Vad som ändrats

- Handläggar-UI v1 visas som byggt, lokalt och verifierat i Lakebase. Inbyggd
  modellchatt, ärenden och autentisering återstår.
- Tjänstelagrets tabell visar samtliga 15 operationer, inklusive anslutning,
  stamdata, arbetsgivare, kö och händelselogg. Registrets nivå skiljs från
  effektiv nivå före och från 1 november och från harness ytterligare begränsningar.
- Harness 3b-1–4 visas som byggda: körpolicy, skill-register, profil, dispatcher,
  resursmandat och agentloop. En agentprofil och två poddar är konfigurerade.
  Loopen är testad med FakeProvider och stannar vid godkännande. Fortsättning
  efter godkännande, varaktig körjournal och modellröktest återstår.
- Rollen `agent_forsakring` är dokumenterat införd i Lakebase. Kunddata kräver
  dessutom `ExecutionScope` och att agentens tjänstelager använder teamets roll.
- Kapitalförvaltningen har styrdokumentshierarki och placeringsriktlinje som
  **beslutsutkast**, samt tre lokalt byggda/testade tabellmodeller. Modellerna
  är **inte skapade i Lakebase**. Gateway, marknadsdata, handelsfunktion,
  saldo-/innehavsberäkning och premiekoppling återstår.
- Företagsöversikten själv visas som i bruk. Byggordning, datamodell,
  moduldiagram, detaljrutor, skript och återstående arbete har rättats samtidigt.

## Kontrollerade fakta och källor

| Uppgift | Underlag |
|---|---|
| 32 beslut; 34 produktregler | `BESLUTSLOGG.md`, `01_domän/produktregler/README.md` |
| PR-ITP1 v1.0 gäller från 2026-11-01 | B-031; reglerna är fortfarande kommande den 24 oktober |
| 15 operationer: 7 read, 1 compute, 7 write | `02_system/tjänstelager_operationer.md`, `src/services/access_register.yaml`, operationskoden |
| 10 tabeller dokumenterade i Lakebase; 13 tabellmodeller i kod | `02_system/databasschema.md`, `src/models/`, kapitalprojektets plan |
| 20 arbetsgivare, 501 försäkrade, 499 försäkringar, 15 097 premier | Dokumenterade kontroller i `ATT_GORA.md`: UI-verifiering 12 oktober och rollverifiering 24 oktober |
| 39,0 Mkr i betalda premier i det genererade grundbeståndet | Återuppbyggnaden 11 oktober i `ATT_GORA.md`; detta är inte ett marknadsvärderat kapital |
| En körprofil, två poddar och återstående harnesssteg | `src/agents/ecosystem.yaml`, `src/agents/__init__.py`, `02_system/harness.md`, `ATT_GORA.md` |
| Kapitalets dokumentutkast och lokala modeller | `projekt/05_kapitalförvaltning/PROJEKTPLAN.md`, `05_styrdokument/`, modellkoden |
| BI och övriga projekt | Respektive `PROJEKTPLAN.md`, dashboarddesign och faktisk kod |

Inga livevärden har hämtats från Lakebase i detta uppdrag. Verifieringsposten
AL-000499 och journaler är manuella tillägg till det reproducerbara grundbeståndet
och ska säkerhetskopieras.

## Kod- och testinventering

Testantalet kommer från `python -m pytest --collect-only -q -p no:cacheprovider`
i projektets befintliga Pythonmiljö, körd från denna worktree den 24 oktober.
645 testfall samlades in i 32 filer utan insamlingsfel. Detta är en inventering;
hela testsviten har inte körts som del av dokumentuppdateringen. Agentloopens
21 tester kördes efter synk med den nya main-leveransen och passerade
(`python -m pytest tests/test_agents_loop.py -q -p no:cacheprovider`).

| Område | Insamlade testfall |
|---|---:|
| Tjänstelagret | 184 |
| Harness och agentroll | 134 |
| Kapitalmodeller | 100 |
| AI-lagret | 83 |
| Handläggar-UI | 77 |
| Analys | 21 |
| Skriptens ingångar | 20 |
| Premiemotorn | 17 |
| Backup och migration | 9 |
| **Summa** | **645** |

29 av dessa testfall kräver isolerad Postgres: 9 för tjänstelagret och 20 för
agentrollen. Inga anrop till delad Lakebase eller riktiga modell-API:er har gjorts
vid uppdateringen; agentloopens tester använder lokal testdatabas och FakeProvider.
Pythonradantal i HTML-tabellen omfattar `.py` rekursivt inklusive tomrader,
kommentarer och docstrings; HTML, CSS, YAML och testkod ingår inte.

## Avvikelse i underlaget att stämma av

B-025 dokumenterar godkänt röktest mot riktiga modell-API:er den 11 oktober.
`ATT_GORA.md` listar samtidigt API-nycklar och röktest som öppet. Översikten
redovisar båda uppgifterna och anger behovet av avstämning eller nytt test i
aktuell miljö. Källdokumenten har inte ändrats inom detta uppdrag.

## Verifiering av leveransen

HTML-struktur, 11 interna ankarlänkar, 8 SVG-diagram, kartans detaljdata och
källfilshänvisningar har kontrollerats lokalt. De 15 operationsradernas namn
stämmer med operationsförteckningen. Samtliga 18 kartknappar har provats i
webbläsare: varje knapp visar rätt detaljvy och markerar valt block.
Sidhuvud, bolagskarta och agentdiagram har granskats visuellt, liksom
sektionsnavigeringen. Vid skrivbordsvyn har sidan inget horisontellt överflöde.
Ingen ny produktregel, databasändring eller driftsättning ingår.
