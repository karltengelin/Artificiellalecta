# Harness – utredning och designförslag

> **Status:** Designinriktningen godkänd i chatten 2026-10-12: egen tunn motor och samlad konfiguration. Operatören preciserade att tjänstelagret endast hör till försäkringssystemet och överlät val av startgränser. Dokumentet beskriver den fortsatta designen; ingen harness eller produktionskod byggs genom det.
> **Implementation:** 3b-1–3b-7 byggda 2026-10-24 i `src/agents/`, röktestet i 3b-8 kört mot båda leverantörerna 2026-10-24 (`scripts/diagnostics/smoke_test_agent.py`); körning i ett ärende med mandat ur ärendet (`run_case`, `scope_for_case`) sedan Fas 5 F5-3, B-033 (körpolicy, `RunRequest`/`RunResult`, skill-register, effektiv profil, dispatcher och resursmandat `ExecutionScope`, agentloopen `run_agent`, länkad fortsättning `prepare_continuation` och körjournalen i `logs/agent_runs/`). Avvikelser från exemplet i §3.4: handläggarens gränser står på teamet och ärvs av agenten; poddarna `regelverk`, `dokument` och `bestand` är monterade på teamen `compliance` och `aktuarie` sedan Fas 3c 3c-T, med gatewayverktyg som skills, parametermandat (`ParameterChangeMandate`) och resultatscheman (`agents.results`); ärendemandatet byggs av betrodd kod ur `cases` i F5-3. För parameteruppdrag används i stället ett uttryckligt `ParameterChangeMandate`; dessa uppdrag ger ingen generell kundåtkomst. `cases` och agentrollens läsrätt finns i Lakebase sedan 2026-10-24; slutverifiering av ärendeflödet återstår från 2026-11-01 (F5-5–6). PII-verktyg visas bara när agentens tjänstelager ansluter med teamets begränsade roll (`agent_forsakring`, `services.db.agent_service_layer`); provkörning av förslag går via den betrodda anslutningen, eftersom den skriver och låser rader (§5.1). Rättigheter: `src/utils/agent_roles.py`, provade mot isolerad Postgres. Effektiv profil: `python scripts/documentation/show_agent_profile.py`.
> **Datum:** 2026-10-12. Kod och lokalt underlag granskat på `main` **0a8227c**, hämtad från origin samma dag.
> **Omfattning:** Fas 3b samt de kontrakt Fas 3c behöver från början. Byggordningen **1 → 1f → 4 → 3b → 5 → 3c** enligt B-028 består.
> **Grund:** B-024/B-026 (vision och team), B-025 (AI-lagret), B-028/B-030/B-031 (tjänstelager och produktregler).

## 1. Vad operatören får

**Rekommendation: bygg en egen tunn harness ovanpå `src/ai/` och tjänstelagret.** Använd en samlad `src/agents/ecosystem.yaml` för team, agentprofiler, poddar och begränsningar. Behåll agenternas Markdown-filer som läsbara arbetsinstruktioner. Befogenheterna avgörs av kod och granskad konfiguration.

En modell kan föreslå nästa steg. Harness avgör om steget är tillåtet, kör rätt verktyg och sparar vad som hände. Tjänstelagret avgör sedan om försäkringsoperationen får utföras, kräver godkännande eller är endast för handläggare. Modellen får ingen direkt databasanslutning, inget generellt filverktyg och ingen möjlighet att utnämna sig till människa.

**Tjänstelagrets gräns:** `src/services/` hanterar försäkringssystemets operationer och deras regler, godkännanden och affärslogg. Att andra områden också använder databasen gör dem inte till försäkringsoperationer. Dokument, kommunikation, kapitalförvaltning, ekonomi och utveckling har egna avgränsade verktygsadaptrar/gateways. Harness kontrollerar deras mandat, resurser och sidoeffekter; respektive gateway skyddar själva verkställigheten. Gemensamt är säkerhetsprinciperna och spårbarheten, inte ett allmänt bolagstjänstelager eller försäkringens åtkomstregister.

Ett vanligt uppdrag kan vara: ”Utred det nya löneunderlaget och förbered registrering.” Operatören ser då lästa underlag, beräkningen, agentens korta motivering och ett preciserat förslag. Statusen **väntar på godkännande** betyder att affärsändringen inte är gjord. Först operatörens beslut verkställer den.

Harness gör inte bolaget komplett. Ärenden, aktuariella motorer, aggregerade beståndstjänster, rapportering och utskick måste fortfarande byggas. Samma motor ska kunna använda dem när deras kontrakt och behörigheter är klara.

```mermaid
flowchart TD
    U[Operatör eller flöde ger ett avgränsat uppdrag] --> H[Harness: kontext, verktygsfilter, loop och journal]
    H <--> A[AI-lagret: roller, modeller, teamnycklar]
    H --> P[Kontrollerad verktygskörning]
    P --> S[Tjänstelager: aktör, åtkomstgolv och affärsregler]
    P --> D[Dokumentgateway: läsning och isolerade utkast]
    P --> X[Övriga domängateways: egna mandat och godkännanden]
    S --> DB[Lakebase och händelselogg]
    S --> Q[Godkännandekö]
    O[Autentiserad operatör] --> Q
    O --> X
    Q --> S
    H --> J[Körjournal med referenser till underlag och beslut]
```

**Läsordning:** §2 skiljer nuläge från förslag. §3–5 beskriver befogenheter och skydd. §6–8 visar körning och journal. §9 går igenom alla team. §10 avgränsar samverkan. §11–14 behandlar verifiering, ramverk och beslut.

## 2. Vad finns redan, och vad måste tillkomma?

Följande är verifierat i koden, inte antaget från målbilden:

| Befintlig kontaktpunkt | Vad harness använder den till | Begränsning som designen tar höjd för |
|---|---|---|
| `AIClient.bind(team=…, agent=…, run_id=…)` och `complete(…, step=…)` | Koppla anrop till team och körning; välja modellroll | Ingen agentloop, körbudget eller åtkomstkontroll ingår |
| `ToolSpec.from_model()` | Generera strikt verktygsschema ur Pydantic | Ett schema är validering, inte behörighet |
| `ModelResponse.to_message()` och `Message.from_tool_results()` | Bevara verktygshistorik och opakt leverantörstillstånd | Historiken måste bevaras oförändrad; tillståndet är inte en publik journal |
| `FakeProvider` | Skriptade svar, fel och fångade förfrågningar utan nätverk | Visar hur motorn reagerar; mäter inte verklig modellkvalitet |
| `ServiceLayer.registry` och `operations_for_agents()` | Upptäcka operationskontrakt och kandidater | Listan är bolagsövergripande, inte filtrerad per team eller kund |
| `ServiceLayer.decision(name)` | Effektiv nivå och skäl, enligt åtkomstregister och regelgolv | Regelkatalogen cachar filinnehåll; måste förnyas vid policy-/datumbyte |
| `execute(name, OperationContext, data)` | Utföra eller föreslå via samma affärslogik som UI | `Actor` är ett värdeobjekt, inte autentisering. `system` behandlas som människa vid utförande |
| `OperationResult.status`, `.pending`, `.approval_id` | Skilja klart från väntan | Returnerar inte händelse-id eller en generell idempotensnyckel |
| `approve/reject` och `approvals.get/list` | Människans beslut och avstämning av väntan | `approve` kör som människa mot aktuella data; räknar inte om agentens teammandat |
| `approval_requests` och `operation_events` | Varaktiga förslag och affärsspår | Ingen flödesmotor eller körjournal; PII-indata sparas i nuläget |

### 2.1 Operationsbild vid granskningen

Detta är en **daterad inventering**, inte en lista inbyggd i motorn. En parallell session utvecklar fler operationer. Vid implementation ska registret upptäckas på nytt och mappningen granskas.

| Operation på 0a8227c | Klass / PII | Register | Effektiv agentnivå 2026-10-12 | Från 2026-11-01, om regler och register består |
|---|---|---|---|---|
| `get_insured_overview` | read / ja | AGENT | AGENT | AGENT |
| `get_premium_history` | read / ja | AGENT | AGENT | AGENT |
| `get_salary_reports` | read / ja | AGENT | AGENT | AGENT |
| `calculate_premium_preview` | compute / nej enligt kontraktet | AGENT | AGENT | AGENT |
| `register_salary_report` | write / ja | APPROVAL | HUMAN_ONLY: kommande regler | APPROVAL |
| `set_policy_paid_up` | write / ja | APPROVAL | HUMAN_ONLY: kommande regel | APPROVAL |
| `correct_premium_transaction` | write / ja | HUMAN_ONLY | HUMAN_ONLY | HUMAN_ONLY |

`terminate_policy` finns inte. Uttag, paus, garanti och pensionsbelopp är inte implementerade på denna bas. Registrerat löneunderlag skapar ingen premie. Beräknad premie är inte bokförd eller mottagen premie.

### 2.2 Föreslagna delar i motorn

| Del | Ansvar | Ska inte äga |
|---|---|---|
| Konfigurationsläsare och policykompilator | Validera team, poddar, resursgränser; producera effektiv profil och förklaringar | Affärsregler eller modell-ID |
| Kontextbyggare | Välja versionerade instruktioner och minsta nödvändiga underlag | Fritt upptäckande av alla filer/kunder |
| Skill-register och dispatcher | Generera scheman, kontrollera varje anrop, anropa försäkringstjänstelagret eller rätt avgränsad gateway | Direkt SQL, mänsklig identitet eller egna försäkringsgodkännanden |
| Agentloop och budgetbok | Steg, väntan, fel, resultat och förbrukning | Teamens affärsberäkningar |
| `RunStore` och körjournal | Händelser, referenser, status och skyddade återstartspunkter | Ersätta tjänstelagrets händelselogg |
| Dokumentgateway | Säkra läshandtag och versionsbundna Markdown-utkast | Godkänna eller ändra gällande regler |
| Fas 3c: delegeringsadapter och flödesmotor | Avgränsade barnuppdrag och deterministiska processer | Fri agentstyrd ordning i kritiska flöden |

Namnen på nya komponenter och fält nedan är **föreslagna kontrakt**. De finns ännu inte i `src/`.

## 3. Befogenheter: vilka regler vinner?

**OC-0, B-038, 2026-10-26:** [Godkända val R–W i operatörscentralens underlag](operatörscentral_beslutsforslag.md#8-en-auktoritativ-modell-budgetpolicy--rw)
preciserar en gemensam lagring och aktiveringsväg för OC-5 och 3b-9, samt
gränsen mellan operativa modell-/budgetval och befogenheter. Designen är
godkänd men ännu inte införd. Källtabellen och YAML-arbetsgången nedan
beskriver dagens implementation; operativa gränser flyttar till gemensamt
PolicyStore först vid kontrollerad, verifierad migrering. OC-5 och 3b-9
använder då samma aktiveringsväg, medan befogenheter ligger kvar i Git.

### 3.1 En kedja av begränsningar

Teamets mandat har två delar. Texten förklarar ansvaret för människor och modellen. Den körbara delen är tillåtna poddar, handlingstyper, resurser och delegeringsmål. Ett mandat som bara står i en prompt är inte verkställt.

För ett verktyg gäller alla följande villkor:

1. Skillen är registrerad och hör till exakt en podd. Operationen eller den godkända lokala beräkningen finns och har ett validerat kontrakt.
2. Poddens monteringslista tillåter teamet. Teamet har monterat podden och agentens uttryckliga poddlista är en delmängd av teamets.
3. Skillen finns inte i någon nekandelista: globalt, team, agent eller aktuellt uppdrag/flödessteg. **Ett nej vinner alltid.** Ingen positiv skilllista får öppna en skill utanför poddarna.
4. Klass och data ryms inom poddens, teamets, agentens och uppdragets gränser. Resursåtkomst är deras **snitt**, inte deras union.
5. För en tjänsteoperation: `service.decision(name).effective` är inte `HUMAN_ONLY`.
6. Eventuellt godkännandekrav är uppfyllt på rätt plats innan handlingen verkställs.

Nivåerna ordnas **AGENT < APPROVAL < HUMAN_ONLY**. Tjänstelagrets nivå är den strängaste av registerraden och B-028:s golv:

- Saknad registerrad → HUMAN_ONLY.
- `external` → minst APPROVAL.
- `write`/`external` utan produktregel eller med någon regel som inte är godkänd och giltig → HUMAN_ONLY.

En monterad podd öppnar alltså aldrig en HUMAN_ONLY-operation. Ett mänskligt godkännande gör inte en sådan operation till ett agentverktyg. Handläggaren kan ta över och utföra en separat manuell åtgärd.

Sidoeffektsklasserna är **inte en enkel rangordning**. `read` kan läsa mycket känslig data och `compute` kan röja individer genom ett aggregat. Använd uttryckliga mängder av tillåtna klasser. ”Högst write” i den äldre målbilden översätts till `[read, compute, write]`; det ger ingen `external`.

```mermaid
flowchart LR
    R[Registrerade skills] --> P[Monterade och tillåtna poddar]
    P --> N[Nekanden och resursgränser]
    N --> G[Tjänstelagrets effektiva nivå]
    G --> X{Resultat}
    X --> B[Dolt och nekat]
    X --> E[Får utföras]
    X --> V[Får bara föreslås]
```

**Samma prövning görs vid varje verktygsanrop**, även om modellen redan sett verktyget. Modellen kan hitta på ett namn, skicka fel personnummer eller försöka återanvända ett tidigare tillåtet anrop. Listfiltrering ensam räcker inte.

### 3.2 Var definieras reglerna?

| Fråga | Auktoritativ källa | Verkställs av |
|---|---|---|
| Vad operationen gör, schema, klass, produktregler och PII | `Operation` i tjänstelagrets register | Tjänstelager och dispatcher |
| Försäkringsoperationernas agentnivå och golv | `access_register.yaml`, `services/access.py`, produktreglernas status | Försäkringstjänstelagret; harness använder `decision()` |
| Verkställighetsregler utanför försäkringssystemet | Respektive gateways granskade kontrakt, resursmandat och godkännandekrav | Dispatcher och respektive gateway; inte försäkringens register |
| Teammandat, poddmontering, nekade skills, resurser och budget | `ecosystem.yaml` i dagens implementation; operativa gränser flyttar till PolicyStore vid B-038:s införande | Policykompilator och dispatcher |
| Aktuellt kund-/ärendescope, mål och flödessteg | Betrodd `RunRequest` från UI/flöde | Dispatcher och datagateway |
| Hur agenten ska arbeta och uttrycka sig | Agentens MD-instruktion och skillinstruktioner | Modell; ger inga rättigheter |
| Faktisk data-/filåtkomst | Databasroller, resursgateway och isolerad körmiljö | Infrastruktur och betrodd kod |
| Människans beslut | Autentiserad beslutsväg och versionsbundet godkännande | Tjänstelager eller flödesgrind |

Här ska ingen andra kopia av registerraderna skapas i `ecosystem.yaml`. Den föreslagna sammanställningen av effektiva verktyg visar namn, podd, nivå, tillåtna resurser och samtliga avslagsskäl. Operatören ska kunna förklara även varför ett verktyg **saknas**.

### 3.3 Avgörande av formatfrågan i agentekosystemet §13

**Välj samlad `ecosystem.yaml`.** Sju team och tio agenter är tillräckligt litet för en gemensam, granskbar fil. Det gör det lättare att upptäcka att en specialist fått fler rättigheter än teamet eller att en PII-podd blivit allmänt monterbar. Körprofiler i MD-frontmatter skulle sprida samma samband över tio dokument och blanda instruktion med säkerhetspolicy.

MD-filerna behåller mandatbeskrivning, arbetsgång och exempel. De får inte överstyra körprofilen. Startvalideringen kontrollerar att rätt instruktion hör till rätt agent och att metadata inte motsäger teamtillhörigheten. En framtida uppdelning av YAML-filen är möjlig bakom samma schema; den kompilerade profilen ska fortfarande vara en enda ögonblicksbild.

Konfigurationen versionshanteras och ändras genom granskad merge. Ingen agent får skriva den, åtkomstregistret, sina instruktioner eller gällande produktregler i sin verksamhetskörning.

B-038 skiljer framöver denna befogenhetskonfiguration från operativa
modell-/budgetval. De senare aktiveras av autentiserad operatör via samma
versionssatta PolicyStore för OC-5/3b-9 när övergången är verifierad.
Inget driftval får vidga poddar, resurser eller domänbehörigheter.

### 3.4 Fullständigt konfigurationsexempel: första försäkringsprofilen

Detta är en komplett **föreslagen profil för ett team**, utan utelämnade rättigheter. Övriga team aktiveras först med egna granskade profiler enligt §9. Alla listor är uttryckliga; inga jokertecken för operationer eller automatiska nytilldelningar används.

`execution_scope` fylls inte med persondata i filen. Det ska komma från en autentiserad ärendebeställning vid körstart; dagens UI körs bara lokalt utan inloggning. Databasprofilerna i designexemplet är symboliska namn, utan hemligheter. Dokumentgatewayens läsverktyg är byggda sedan 3c-G (§5.2); det historiska exemplet nedan är inte den aktuella körpolicyn. Faktiska profiler och monteringar finns i `src/agents/ecosystem.yaml`.

```yaml
schema_version: 1
policy_id: harness-v1-example
defaults:
  unknown_skill: deny
  unmapped_operation: deny
  raw_sql: deny
  shell: deny
  generic_network: deny
  actor_from_model: deny
  require_execution_scope_for_pii: true
  deny_skills: []
  allowed_effects: [read, compute, write]
  limits:
    max_steps: 20
    max_tool_calls: 30
    max_cost_usd: 2.00
    max_output_tokens: 4000
    max_context_bytes: 120000
    max_wall_seconds: 600
  journal:
    mode: references
    log_provider_state: false

pods:
  kunddata:
    owner_team: forsakring
    mountable_by: [forsakring]
    pii: true
    allowed_effects: [read, write]
    database_profile: insurance_case_scoped
    resource_scope: assigned_case_subjects
    skills:
      get_insured_overview: {service_operation: get_insured_overview}
      get_premium_history: {service_operation: get_premium_history}
      get_salary_reports: {service_operation: get_salary_reports}
      register_salary_report: {service_operation: register_salary_report}
      set_policy_paid_up: {service_operation: set_policy_paid_up}
      correct_premium_transaction: {service_operation: correct_premium_transaction}
  berakning:
    owner_team: aktuarie
    mountable_by: [forsakring, aktuarie]
    pii: false
    allowed_effects: [compute]
    database_profile: base_amounts_readonly
    skills:
      calculate_premium_preview: {service_operation: calculate_premium_preview}
  regelverk:
    owner_team: compliance
    mountable_by: [forsakring, compliance]
    pii: false
    allowed_effects: [read]
    read_roots: [01_domän, 04_regulatoriskt, 05_styrdokument]
    skills:
      read_rule_document: {executor: document_read, kind: read}
  dokument:
    owner_team: utveckling
    mountable_by: [forsakring]
    pii: false
    allowed_effects: [write]
    write_roots: [logs/agent_artifacts/forsakring]
    file_types: [.md]
    overwrite_existing: false
    max_file_bytes: 102400
    max_files_per_run: 10
    max_total_artifact_bytes: 524288
    skills:
      write_markdown_draft: {executor: document_draft, kind: write}

teams:
  forsakring:
    lead: case_handler
    mandate: Utred tilldelade ITP1-ärenden och förbered administrativa åtgärder.
    pods: [kunddata, berakning, regelverk, dokument]
    allowed_effects: [read, compute, write]
    deny_skills: [correct_premium_transaction]
    require_human_review_for_effects: []
    delegates_to: [kommunikation]
    draft_classification: internal_no_pii

agents:
  case_handler:
    name: Handläggaragent
    team: forsakring
    instruction: 02_system/agenter/handlaggaragent.md
    model_role: standard
    pods: [kunddata, berakning, regelverk, dokument]
    allowed_effects: [read, compute, write]
    deny_skills: [set_policy_paid_up]
    delegates_to: [kommunikation]
    execution_scope: assigned_case_subjects
    limits:
      max_steps: 12
      max_tool_calls: 18
      max_cost_usd: 0.50
      max_output_tokens: 1500
      max_context_bytes: 40000
      max_wall_seconds: 180

delegation:
  enabled: false
  targets: [kommunikation, compliance]
  max_depth: 2
  max_children: 3
  compliance_escalation: always_route_or_queue
```

Ägarteam och framtida delegeringsmål är namn i B-026:s sju-teamregister; de behöver inte vara aktiverade i denna första profil. Med `enabled: false` startas inga barnagenter. Eskalering registreras för operatören tills compliance kan köras. Vid aktivering ska mottagarens ledande profil finnas.

Denna agent får per 12 oktober tre kundläsningar, premieförhandsberäkning, regelverksläsning och ett skyddat dokumentutkast. `register_salary_report` filtreras bort av regelgolvet. Från 1 november kan samma profil visa det som **föreslå**, utan YAML-ändring. `set_policy_paid_up` är fortfarande nekat på agentnivå. `correct_premium_transaction` är både teamnekat och HUMAN_ONLY. Exemplet visar att en bredare teamprofil inte automatiskt öppnar allt för agenten.

`calculate_premium_preview` har `pii=False`, men ett födelsedatum tillsammans med kundkontext är ändå personanknutet. Kontextens dataklass följer med beräkningen och dess svar; poddens flagga får inte tvätta bort PII. För fristående kalkyler används syntetiska underlag.

### 3.5 Nya operationer och ändrad policy under en körning

Motorn itererar kontrakten i tjänstelagrets register. Den bygger kandidater genom `operations_for_agents()`, förenar dem med den granskade skill→podd-mappningen och räknar ut profilen. En ny operation måste få både en uttrycklig registerrad och en poddmappning innan den kan bli verktyg. Ommappade operationer rapporteras som stängda; de stoppar inte redan giltiga profiler. En mappning till ett namn som inte finns, dubbla poddmedlemskap eller oförenlig PII/klass stoppar profilens start.

Schema, instruktion, register, regelpaket, konfiguration och kodversion får kontrollsummor i körningen. Ingen ny förmåga läggs till mitt i en körning. Vid policyändring avbryts eller pausas körningen för omprövning; en indragning ska gälla även redan visade verktyg. Tjänstelagret får en färsk register-/regelkatalog vid körstart och återupptagning. Vid datumskifte eller filändring förnyas den före nästa handling; att bara kalla `decision()` på ett gammalt objekt räcker inte, eftersom `ProductRuleCatalog` cachar status.

Granskade versioner ska publiceras atomiskt och vara oföränderliga under ett anrop. En global stoppfunktion ska kunna neka nya verktyg och nya godkännanden. Ändringar mellan kontroll och affärstransaktion behöver en policyversionskontroll i tjänstelagret innan säker automatisk återstart kan införas; detta är en kontraktsutökning, inte befintligt stöd.

## 4. Skill-kontrakt och godkännanden

### 4.1 Tunt omslag, samma affärslogik

En tjänsteskill tillför poddtillhörighet, resultatprojektion och resurskontroll. Den kopierar inte operationens beräkning, produktregel, PII-flagga eller åtkomstnivå. Dispatcher anropar alltid `service.execute`, aldrig `op.func`. `calculate_premium_preview` är den ordinarie premieingången. Den rena premiemotorn kan dessutom användas för tydligt märkta syntetiska scenarier, med granskad indata; detta får inte bli en alternativ väg till affärsskrivningar.

Ett verktygsanrop behöver en kort motivering när det ändrar något. Föreslaget modellformat är ett genererat omslag `{data: <operationens indata>, reason: <kort motivering eller null>}`. Indatamodellen återanvänds; aktör, run-id, session, behörighet och godkännare ingår aldrig i modellens schema. Extra nycklar nekas server-side även om en operations nuvarande Pydantic-modell skulle ignorera dem.

Illustration av befintliga API:er och föreslagen schemagenerering, **inte färdig harnesskod**:

```python
from pydantic import ConfigDict, create_model
from ai import ToolSpec
from services import Actor, OperationContext

op = service.registry.get("register_salary_report")
ActionInput = create_model(
    "RegisterSalaryAction",
    __config__=ConfigDict(extra="forbid"),
    data=(op.input_model, ...),
    reason=(str | None, None),
)
tool = ToolSpec.from_model(op.name, op.description, ActionInput)

# trusted_run och validated_action kommer från kontrollerad körning/validering.
# Behörighet, kundscope och färsk decision() prövas före denna punkt.
ctx = OperationContext(
    actor=Actor.agent("case_handler", team="forsakring"),
    run_id=trusted_run.run_id,
    case_id=trusted_run.case_id,
    reason=validated_action.reason,
)
result = service.execute(op.name, ctx, validated_action.data)
if result.pending:
    # Spara approval_id och avsluta segmentet som waiting_approval.
    # Affärsändringen är ännu inte utförd.
    record_wait(result.approval_id)
```

I exemplet måste den validerade `reason` vara icke-tom; tjänstelagret kontrollerar också detta. Den betrodda körningen bestämmer identiteten för varje agent, inte en hårdkodad identitet för alla team. `record_wait` och `trusted_run` är föreslagna harnessdelar.

Lokala skills får bara peka på godkända exekverartyper och implementationsregister. YAML får inte ange en godtycklig import, eval-funktion eller shellkommando. Skills som själva behöver en modell måste gå via samma bundna AI-klient och budgetbok; dolda modellanrop utanför budgeten tillåts inte.

### 4.2 Tre olika slags godkännande

| Slag | Exempel | Ägare och bevis |
|---|---|---|
| Affärsoperation | Registrera löneunderlag | Tjänstelagrets `approval_requests`; `approve` utför åtgärden och loggar den atomiskt |
| Process-/dokumentgrind | Godkänna en regeltolkning innan nästa steg | Flödesmotorns versionsbundna beslut; godkänner ett underlag, utför inte en försäkringsoperation |
| Extern verkställighet | Skicka brev, lämna rapport, driftsätta | Respektive domän-/kanalgateway med exakt mänskligt godkänt innehåll, mål och kvitto. För försäkringsoperationer gäller även tjänstelagrets external-golv |

En flödesgrind får aldrig ersätta godkännandet av en APPROVAL-operation. Om ett team/flöde kräver mänsklig granskning även för en AGENT-operation ska **föreslagen `pending_review`** stoppa innan `execute`; godkännandet gäller operation, indatahash, scope och version. Därefter körs den som ursprunglig **agent** och journalen länkar grinden. Dagens `execute` har ingen parameter som tvingar en annars AGENT-operation till kön. Första profilen använder därför inga sådana extra operationsgrindar. I Fas 3c visas grindarna och tjänstekön tillsammans i UI, men deras betydelse hålls isär.

Ett befintligt tjänsteärende innehåller sparade indata. Det ska inte ändras efter granskning. Om underlaget ändras avslås det gamla och ett nytt förslag skapas. Nuvarande lagring kopplar inte ärendet till kod-, schema- eller innehållshash. Det behöver tillkomma inför automatiserad återupptagning och externa handlingar. Vid mänskligt godkännande måste den betrodda beslutsvägen kontrollera att rätt version, teammandat och aktuellt resursmandat fortfarande gäller. `approve` gör affärsvalidering mot aktuella data men kan i dag godkänna ett gammalt förslag efter indragen agentåtkomst, eftersom den kör som människa.

### 4.3 Interna utkast och externa kanaler: undvik ett dolt kryphål

Nuvarande regelgolv stänger **försäkringstjänstelagrets** `write`/`external` utan godkänd produktregel. Det golvet består för försäkringsoperationer. Ett dokumentutkast, mailutskick, ekonomisk bokning eller en release är ett annat verksamhetsområdes handling och ska inte registreras där. Samma databas kan innehålla flera områdens tabeller; gränsen följer verksamhetsansvaret, inte var raderna lagras.

Designen för Fas 3b använder en separat, snävt avgränsad dokumentgateway som endast skriver **utkast i körningens arbetsyta** och har egen verkställd filpolicy (§5.2). Den kan inte ändra försäkringsdata, gällande dokument eller aktiva instruktioner. Dess writes journalförs även vid manuell användning.

Varje gateway utanför försäkringssystemet deklarerar ett eget litet kontrakt: in-/utdata, sidoeffektsklass, dataklass, tillåtna resurser och destinationer, ansvarigt team, eventuell versionsbunden policy och mänskligt godkännandesteg. Externa handlingar kräver alltid människa enligt §3.5, även om en intern policy medger handlingen. Interna utkast behöver den godkända fil-/körpolicyn; de behöver ingen påhittad produktregel. Ingen utökning med ett generellt policyregelverk krävs i `src/services/`.

Harness använder samma kontrollordning och journalformat men skickar handlingen till rätt adapter. Respektive adapter måste även neka otillåten verkställighet vid direkt användning. Föreslagna externa förslag och deras godkännandereferenser sparas varaktigt av gatewayen eller flödesmotorn enligt §10; försäkringens `approval_requests` används endast för försäkringsoperationer. Operatörens UI kan samla väntande beslut utan att flytta deras ägarskap. Fram till dess att respektive gateway är byggd förbereder agenten underlag och människan utför handlingen manuellt med dokumenterat kvitto.

## 5. Guardrails utöver verktygslistan

### 5.1 Data, personuppgifter och Lakebase

Modellen får strukturerade verktygsresultat. Den får varken databaslösenord, ORM-session, rå SQL, fri Python eller ett verktyg som kan hämta godtyckliga tabeller. Betrodd kod öppnar en anslutning utifrån poddens dataprofil.

| Dataprofil, föreslagen | Tillåten användning | Verkställd gräns |
|---|---|---|
| `base_amounts_readonly` | Premieförhandsberäkning | Bara nödvändiga basbelopp; ingen individtabell |
| `insurance_case_scoped` | Försäkringsteamets tilldelade ärenden | Ärendets personer/försäkringar, tillåtna fält och perioder; läsning/förslag via tjänstelagret |
| `recipient_scoped` | Kommunikation för ett bestämt utskick | Bara rätt mottagare och kontaktuppgifter, inte lön eller full historik |
| `aggregate_readonly` | Aktuarie, kapital, ekonomi och rapportering | Granskade aggregat/vyer; ingen rå individdata |
| Operatörens beslutsanslutning | Godkänna och utföra | Separat autentiserad väg, aldrig utlämnad till agentens exekverare |

Operatören sätter upp Lakebase-roller och eventuella vyer. Databasrättigheter och tester mot riktig Postgres måste finnas **före första PII-podden**, inte som ett generellt ”senare”. Detta flyttar en punkt i äldre §12/backlog; B-026:s konsekvenstext säger redan att rollen behövs när första PII-podden byggs.

En roll med SELECT på en hel individtabell säkrar inte kundscope. Betrodd resurskontroll måste verifiera att personnummer och försäkringsnummer hör till tilldelat ärende före anrop och innan resultat lämnas ut. För starkare isolering används en gateway med begränsad tjänsteidentitet och vid behov radnivåskydd/vyer. Varken detta scope eller rollerna finns i dagens `OperationContext`/operationer. Förslaget måste byggas och negativtestas; en YAML-rad skapar inga databasrättigheter.

Tjänstelagret behöver skriva godkännande- och händelserader även vid vissa läsningar. En helt skrivskyddad anslutning räcker alltså inte för hela `ServiceLayer`. Separera affärsläsrättigheter från snäva rättigheter att lägga till förslag/auditrader; hindra uppdatering/radering av äldre logg och direkt affärs-DML från agentprocessen. Förslag till writes provkörs och rullas tillbaka med betrodd tjänsteidentitet, utan att agenten får anslutningen. Olika dataprofilers tjänstelager ska använda **samma varaktiga godkännandekö** och operatörens beslutsväg, inte isolerade minnesköer.

`bestand` får inte implementeras som ”hämta alla individer och be modellen summera”. Aggregatet beräknas i betrodd kod. Startskyddet är att dölja celler med färre än **10** individer, grova segment och förbud mot upprepade överlappande urval som kan avslöja en person genom differenser. Talet 10 är en vald försiktig startgräns, ingen garanti för anonymitet. Tills en kontrollerad aggregattjänst finns saknar dessa team beståndsverktyg.

**Första aggregattjänsten byggd i 3c-B (2026-10-25, B-035):** `estimate_parameter_change_impact` (`tjänstelager.md` §9.5) döljer celler med 1–9 individer, döljer vid behov fler så att en dold cell inte kan räknas fram ur totalen, och avrundar belopp till hela tusental kronor. Den skyddar varje enskilt svar. Skyddet mot differenser mellan upprepade anrop ligger i parametermandatet sedan 3c-T: i podden `bestand` får aktuarieagenten bara anropa den med exakt den parameter, det värde, den giltighetsdag och den horisont som uppdragets godkända förslag anger.

**Aktuarieteamets roll (3c-V, förberett 2026-10-26):** `agent_aktuarie` (`AKTUARIE` i `src/utils/agent_roles.py`) får `SELECT` på `base_amounts`, `insured_persons`, `policies`, `policy_states` och `product_parameters` och `INSERT` på `operation_events` (för nekade försök), men inga löner, premier, ärenden, arbetsgivare eller förslag i kön. Anslutningen heter `AGENT_AKTUARIE_DATABASE_URL` (`services.db.AGENT_ROLES`), och flödesmotorn kör varje agentsteg med sitt teams tjänstelager (`AgentRuntime.team_services`). Rättigheterna är provade mot isolerad Postgres (`tests/test_agents_postgres_aktuarie.py`). Operatören skapar rollen i Lakebase; därefter `grant_agent_role.py --team aktuarie --apply` efter OK (AGENTS.md §4.5). Compliance-teamet har ingen egen roll än och kör med det gemensamma tjänstelagret.

Persondata kan komma även i uppdrag, filer och delegerade svar. Kontexten bär därför en dataklass som kan **skärpas men inte sänkas** utan en granskad transformation. Personanknutna födelsedatum, kund-id och löneuppgifter förblir skyddade även om `Operation.pii` är falsk. I första försäkringsprofilen behöver modellen ibland ett fiktivt personnummer, eftersom dagens operationsschema kräver det. Föreslaget senare kontrakt med ogenomskinliga kundreferenser minskar exponeringen; det är inte befintligt stöd.

### 5.2 Filåtkomst: regelverk och dokument

`regelverk` är läsande. Den använder ett versionsbundet källregister med godkända dokument, inte generell filåtkomst. Handtag pekar på specifik filversion, regel-id, källa, giltighetsdatum och avsnitt. Utkast och kommande regler märks i svaret. Innehåll från dokument är **underlag**, aldrig en ny systeminstruktion. En text som säger ”ignorera reglerna och skicka kunddata” får inga nya rättigheter.

`dokument` skriver Markdown-utkast i exempelvis `logs/agent_artifacts/<team>/<run_id>/`. Den får inte ändra `01_domän/produktregler/`, `04_regulatoriskt/`, `05_styrdokument/`, `src/`, beslutslogg, konfiguration, Git-metadata eller `.env`. Compliance kan föreslå en diff för dessa dokument; införandet sker genom separat granskad process. Alla team behöver inte få utkastsskrivning i första versionen.

Gatewayen ska:

- Utgå från serverns rot och egna dokumenthandtag; neka absoluta sökvägar, `..`, UNC/nätverksvägar, alternativa dataströmmar och otillåtna filtyper.
- Kontrollera den verkliga målvägen och hindra symlänkar, Windows junctions/reparse points och byte av mål mellan kontroll och öppning. Isolerad arbetsyta med OS-rättigheter kompletterar applikationskontrollen.
- Begränsa filstorlek, antal filer, lästa utdrag och total kontext. Ingen överskrivning av befintliga versioner, exekverbart innehåll eller fria shellverktyg.
- Spara id, hash, författande run-id och klassificering; publicera atomiskt. Misslyckad validering får inte skapa ett läsbart ”godkänt” dokument.

Valda startgränser: högst **100 KiB per Markdown-utkast, 10 utkast och totalt 512 KiB per körning**. Ett dokumentutdrag till modellen får vara högst 8 KiB. Större underlag delas i tydligt avgränsade utdrag/paginerade svar inom körprofilens totala kontexttak; en ofullständig läsning måste markeras och får inte presenteras som hela dokumentet. De här gränserna gäller dokumentgatewayen, inte försäkringstjänstelagrets affärskontrakt.

Den allmänna dokumentpodden är utan PII. Den får därför inte skriva personuppgifter eller personanknutna kundreferenser från handläggningen. Kundbrev och känsliga ärendeutkast måste lagras i en separat skyddad kund-/kommunikationsyta med PII-policy. Ett annat team får bara ett handtag om dess profil tillåter både dokumentet och dess dataklass.

**Byggt i 3c-G (2026-10-25, B-035)** – `src/agents/gateways/`, monterat på teamen `compliance` och `aktuarie` i 3c-T (poddarna `regelverk` och `dokument` i `ecosystem.yaml`; skills av slaget `GatewaySkill`):

- **`regelverk`** (`RegulatoryGateway`, verktygen `list_regulatory_documents` och `read_regulatory_document`): en katalog över en fast lista godkända platser – källregistret, regelverkskartan, regelverksunderlagen, bevakningen, tolkningarna, produktreglerna, produktregelpaketet, parameterregistret, villkoren, den aktuariella grunden och ITP1-regelverket (65 dokument). Handtag i stället för sökvägar (`PR-ITP1-013`, `T-ITP1-006`, `K-SIM-ITP-2027`). Varje svar har version, statusrad och kontrollsumma, fiktiva källor märks, och texten följs av anteckningen att den är underlag och inte instruktioner. Utdrag är högst 8 KiB, kan börja vid en rubrik och läses vidare med `next_offset`; ett ofullständigt utdrag är märkt. Filer över 512 KiB läses inte.
- **`dokument`** (`DraftGateway`, verktyget `write_draft`): utkast i `logs/agent_artifacts/<team>/<run_id>/` med gränserna ovan. Team och run-id kommer från betrodd kontext; modellen anger bara ett filnamn ur mallen `^[a-z0-9][a-z0-9_-]{0,58}\.md$`. Publicering via tillfällig fil och hårdlänk, som misslyckas om namnet finns – ingen överskrivning. Exekverbart innehåll (skript, inbäddningar, händelseattribut, `javascript:`), kontrolltecken och personnummer stoppas. Id, kontrollsumma, författande körning och dataklass sparas i `manifest.jsonl`.
- Båda kontrollerar varje led i sökvägen mot symlänkar och Windows junctions/reparse points, och att den verkliga sökvägen ligger under gatewayens rot (`checked_path`). Testerna (`tests/test_agents_gateways.py`) prövar junctions på riktigt i Windows.

### 5.3 Utdata, eskalering och externa handlingar

Kontroller görs innan verktygsresultat går in i modellen, innan ett dokument sparas, innan ett svar lämnas till ett annat team och innan operatören får ett färdigt resultat. Ett schema kontrollerar struktur; det bevisar inte att en regeltolkning är riktig.

Föreslaget resultatschema innehåller `status`, `summary`, `evidence_refs`, `assumptions`, `uncertainties`, `proposals` och `pending_approvals`. Kontrollerna verifierar att källreferenser finns och är tillåtna, att belopp stöds av en faktisk beräkning och att ”utfört” har ett DONE-resultat/verkställighetsspår. Oväntad persondata eller hemligheter spärrar publicering. Regex/DLP och modellgranskning är kompletterande skydd; säkerhetsgränsen är kontrollerade fält och resurser.

Juridisk osäkerhet, motstridiga giltigheter, negativ rättighetsändring och otillräckligt underlag ska kunna ge `needs_compliance` eller `needs_human`, inte ett gissat sakbeslut. Alla agenter, även specialister, får en smal **eskaleringskanal till compliance** enligt B-011. Den överför bara behöriga referenser och en kort fråga. Om compliance saknas, budgeten är slut eller djupgränsen nås registreras eskaleringen och lämnas till operatören. ”Alltid tillåten” är en rätt att eskalera, inte obegränsade modellanrop eller automatisk delning av PII.

En extern handling godkänns för exakt mottagare, innehåll/version, kanal, bilagor och eventuell summa. Ändring efter beslut kräver nytt godkännande. Inget nätverksverktyg får kringgå kanalgatewayen. Kommunikationsagenten äger kundbrev och allmänna meddelandekanaler; domänteam äger sina rapport-/transaktions-/releasevägar (§9.4). Modellens sluttext till operatören är intern. Kundportal/chattbot får inte automatiskt skicka samma svar till kund: deras externa svarsmodell behöver ett separat beslut förenligt med §3.5.

Nuvarande databastransaktion kan inte göra mail, mäklaranrop eller driftsättning atomiskt med en loggrad. Före sådana operationer krävs beständig utsändningspost (**outbox**), idempotensnyckel, kvitto och status för ”utfall okänt”. Ett timeout-anrop skickas inte om utan avstämning. Första versionen förbereder utkast och överlämnar till människan.

## 6. Motorn: från uppdrag till slutresultat

### 6.1 Kontextbygge

Betrodd `RunRequest` anger uppdragstyp, teamets ledande agent, case-id när det finns, resursmandat, förväntat resultatschema och eventuella `parent_run_id`, `root_run_id`, `flow_id` och `flow_step_id`. Uppdragstext får inte överstyra de fälten.

Kontextbyggaren lägger samman en kort stabil bolagskontext (sandbox, ITP1-scope, principer), agentens versionsbundna MD-instruktion, tillåtna skillinstruktioner, aktuellt datum/giltighetsläge och det avgränsade uppdraget. Kundhistorik och hela bolagsmappen förladdas inte. Relevant underlag hämtas genom verktygen med mängdgränser. Föreslagen v1 har inget tvärgående minne; ett nytt uppdrag börjar med nya behörighetskontroller.

Historiken hålls append-only och använder `response.to_message()`. `provider_state` går tillbaka oförändrat genom AI-lagret; harness tolkar inte modellens interna tänkande. Når kontexten taket stoppas körningen med en kontrollerad överlämning. Senare komprimering startar ett nytt länkat segment med sammanfattning och källreferenser, i stället för att redigera den gamla historiken.

### 6.2 Loopens ordning

1. Validera profil, instruktion och betrott uppdrag. Skapa run-id, versionsbild, budget och `run_started` innan modellen anropas.
2. Bygg och journalför effektiv verktygslista. Förnya policy om versions-/datumkontrollen kräver det.
3. Kontrollera steg-, tids-, kontext- och kostnadsutrymme. Bind `ai` till rätt team, agent, run-id och steg. Anropa `complete()` med modellroll och outputtak.
4. Journalför modellmetadatans kostnad, svarstyp och referenser; append:a hela assistantmeddelandet till den skyddade historiken.
5. Vid `tool_use`: validera hela anropsgruppen först. Neka okända/otillåtna namn, extra fält, falska identiteter, fel scope och dubbletter av call-id. Ett säkerhetsbrott stoppar gruppen före verkställighet.
6. Kör giltiga anrop **sekventiellt** i v1. Kontrollera rättigheter och budget igen före vart och ett. Journalför avsikten före `execute` och utfallet efteråt. Återför projekterade JSON-resultat som `ToolResult`.
7. Första `pending_approval` stoppar vidare verkställighet. Kvarvarande anrop i samma modellsvar får resultat `not_executed_waiting` i historiken. Alla call-id får ett svar, även när ett anrop inte kördes. Journalför väntan och returnera ett deterministiskt väntesvar; inget extra modellanrop krävs.
8. Vid `end_turn` utan verktyg: validera slutresultatet och källorna, publicera, avsluta som `completed`. Ett svar som innehåller verktyg trots motsägande stop_reason är ett protokollfel. `max_tokens`, `refusal` och `other` räknas inte som lyckat slutförande.

En grupp av verktyg är **inte en affärstransaktion**. Ett tidigare DONE-resultat kan redan vara sparat när ett senare anrop väntar eller fallerar. Journalen visar detta per anrop. Affärsåtgärder som måste ske tillsammans behöver en samlad tjänsteoperation med egen transaktionsgräns.

### 6.3 Tak och kostnader

Ett **steg** är ett anrop till `complete`; varje verktygsanrop räknas dessutom separat. Klassificering, slutlig strukturering och eventuella granskarmodeller räknas också. Tak är minimum av globala, team-, agent-, uppdrags- och rotbudgetgränser. Modellen får inte höja dem. Vid uppnått tak görs inget ytterligare ”bara sammanfatta”-anrop.

Operatören har överlåtit val av startgränser. Följande värden väljs för första sandbox-implementationen; de ändras genom granskad konfiguration efter mätning. De öppnar inga nya poddar eller externa handlingar.

| Körprofil | Modellsteg | Verktygsanrop | Kostnadsbudget, USD | Utdata per modellanrop, tokens | Total modellkontext, UTF-8-byte | Aktiv tid, sekunder |
|---|---:|---:|---:|---:|---:|---:|
| Handläggare (`forsakring`) | 12 | 18 | 0,50 | 1 500 | 40 000 | 180 |
| Kommunikation | 8 | 12 | 0,50 | 2 000 | 40 000 | 180 |
| Kapital | 12 | 18 | 1,00 | 2 000 | 60 000 | 300 |
| Aktuarie och compliance | 20 | 30 | 2,00 | 12 000 | 120 000 | 600 |
| Ekonomi och inköp | 12 | 18 | 0,75 | 2 000 | 60 000 | 300 |
| Utveckling | 20 | 30 | 2,00 | 3 000 | 120 000 | 600 |

Globala tak för en enskild agent är 20 steg, 30 verktygsanrop, 2 USD, 12 000 utdatatokens, 120 000 kontextbyte och 600 sekunders aktiv tid. En specialist ärver högst teamets profil; uppdrag får bara sänka gränserna. En sammanhängande delegerad rotkörning får totalt högst **5 USD, 60 modellsteg, 90 verktygsanrop och 900 sekunders aktiv tid**, högst 3 barn och djup 2 (§10.2). Barn och fortsättningar använder samma budgetbok. Manuellt godkänd budgethöjning kräver ett nytt, journalfört uppdragsmandat; modellen kan inte höja taket.

**Justerat efter röktestet 3c-V (2026-10-26, operatörens beslut):** utdatataket höjdes från 4 000 till 12 000 tokens globalt och för compliance och aktuarie, eftersom en tolkning med `claude-opus-5` klipptes vid 4 000 (resonemang och svar delar taket). Compliance-teamets verktygstak höjdes från 24 till 30 efter att `gpt-6-astra` nått taket under läsningen. Kostnadstaken i `ecosystem.yaml` (compliance 1,50 USD, aktuarie 1,00 USD per körning) är oförändrade och begränsar fortfarande förbrukningen.

En lång godkännandeväntan använder ingen modell och ingen aktiv worker; tidsgränsen gäller aktivt arbete. Återupptagning nollställer inte förbrukningen. För första handläggaren är arbetsenheten **en tilldelad försäkrad och ett löneunderlag per körning**, med högst 24 månaders relevant historik. Masshantering kräver en separat granskad profil.

Vid aktiv tidsgräns tar motorn inte emot nya handlingar från ett försenat modellsvar. Dagens synkrona `complete()` kan vara upptaget av SDK-omförsök; deadline kräver avgränsad worker/anropsavbokning i implementationen, inte bara en klockkontroll mellan varven. Ett avbrutet leverantörsanrop kan ändå debiteras, så dess kostnadsreservation behålls tills utfallet stämts av. Ingen verktygsskrivning får starta från ett svar efter deadline.

Att summera `response.cost_usd` efter anrop hindrar fortsatt förbrukning men kan redan ha överskridit budgeten. Före anrop reserveras därför en konservativ uppskattning för indata, högsta utdata, cachekostnad och hela tillåtna reserv-/omförsökskedjan. Pristabellen och kontextstorleken versionsbinds. Saknad kostnad eller osäker indatauppskattning stoppar eller använder full konservativ reserv, aldrig noll.

Dagens AI-lager kan göra SDK-omförsök och leverantörsbyte inom ett `complete`. Felloggarna innehåller inte alltid tokens/kostnad. Föreslagen budgetbok tar emot AI-lagrets logg via en kompletterande `TraceSink` och håller reservationen för försök med okänd debitering. **Ett exakt monetärt hårdtak kan inte garanteras av dagens kontrakt.** Fas 3b kan ge konservativ admission och stopp; exakt attempt-budget/avbokning kräver en utökning inne i `src/ai/`, inte nya SDK-anrop från harness. Leverantörens faktura är facit. Anta inte att en projektbudget är en hård spärr utan att dess faktiska beteende verifierats.

### 6.4 Fel, stopp och återstart

| Händelse | Motorns svar | Omförsök |
|---|---|---|
| `InvalidInputError`, saknad motivering | Maskerat strukturerat verktygsfel; modellen får rätta inom återstående tak | Högst två korrigeringar av samma felklass i v1 |
| `NotFoundError` | Be om komplettering/korrekt referens | Ingen bred kundsökning som reserv |
| `BlockedError` | `needs_human` med skäl och produktregel | Ingen omtolkning av operationen |
| `ConflictError` | Ny läsning och bedömning av aktuellt läge | Ingen blind upprepning av skrivning |
| Nekat namn/scope, identitetsförfalskning | `blocked`, avvisningshändelse och överlämning | Ingen reservmodell för att kringgå gränsen |
| Leverantörens 429/timeout/5xx | AI-lagrets befintliga begränsade reservkedja | Ingen ytterligare obegränsad harness-retry |
| Autentiserings-/konfigurationsfel eller slut på reservkedja | `failed` med sanerat fel och felsökningsreferens | Operatören behöver rätta orsaken |
| `refusal`, avklippt/ogiltigt slutresultat | `needs_human` eller `failed`; ingen publicering som färdig | Högst avgränsad rättning, aldrig säkerhetsfilterjakt |
| Steg-, kostnads- eller tidstak | `limit_reached` med redan utförda/väntande handlingar | Inga nya verktyg eller modellanrop |
| Journal/återstartspunkt kan inte sparas | Stoppa före nästa handling | Avstämning mot tjänstelagrets spår krävs |
| Timeout/krasch efter möjlig skrivning | `reconciliation_required` | Ingen automatisk återspelning |

Skrivning och affärslogg är atomiska i tjänstelagret, men JSONL-journalen är inte i samma transaktion. Krasch efter tjänstens commit kan lämna en avsikt utan dokumenterat utfall i körjournalen. Dagens tjänst saknar generell idempotensnyckel och exakt koppling från tool-call till event-id. V1 tillåter därför **inte automatisk återspelning av writes efter krasch**. Operatören stämmer av händelseloggen och kön innan fortsatt arbete. Idempotens/correlation-kontrakt är ett krav före automatisk Fas 3c-återhämtning.

När en vanlig väntan avgjorts behöver harness hämta förslagets status och verkställighetsspår; den får inte kalla ursprungsoperationen igen. Ett avslag ska inte följas av ett nytt likadant förslag utan ändrat underlag eller nytt uppdrag. Fas 3b kan avsluta körsegmentet i väntan och starta en **länkad fortsättning** på operatörens initiativ. Fas 3c kopplar samma kontrakt till varaktig återupptagning. Nytt segment har eget run-id samt `continuation_of`; rotbudgeten och förslagets ursprungliga run-id består.

## 7. Komplett körexempel: ett nytt löneunderlag

Exemplet visar den föreslagna motorn med **befintliga tjänsteoperationer**. Det körs i ett syntetiskt testläge med datum **2026-11-02**; inga affärsskrivningar görs genom denna utredning. Både regelkatalogens datum och operationernas datumkälla måste styras i testet. Att bara ange ”2 november” i prompten öppnar inga rättigheter.

Testunderlaget är en aktiv försäkrad hos nuvarande arbetsgivare, med ITP1-tillhörighet före oktober, inga lönerapporter eller premier för oktober och IBB 2026 = 83 400 kr. Alla identifierare är fiktiva fixtures. Ett tilldelat testärende `CASE-DEMO-001` är en referens; någon `cases`-tabell finns inte på bascommitten.

**Uppdrag:** ”Arbetsgivaren har rapporterat 60 000 kr pensionsmedförande oktoberlön. Kontrollera underlaget, visa premieförhandsberäkning och förbered registrering. Ingen premierättelse eller kundkommunikation.”

| Steg | Vad sker | Bevis och status |
|---|---|---|
| 0 | Betrodd beställare väljer `case_handler`, tilldelat kundscope och max 0,50 USD. Harness skapar `run-demo-001` | Versionsbild, scope-referens och sju effektiva verktyg enligt §3.4; löneoperationen är APPROVAL |
| 1 | `ai.bind(team="forsakring", agent="case_handler", run_id="run-demo-001").complete(…, model="standard", step="1")` föreslår `get_insured_overview` | Dispatcher kontrollerar fixture-personnumret mot ärendet, skapar `Actor.agent`, läser via tjänsten. PII-läsningen loggas; modellen får bara nödvändiga anställnings-/försäkringsfält |
| 2 | Modellen begär `get_salary_reports` för oktober | Samma scope; inget befintligt underlag. Saknat löneunderlag betyder inte noll. Resultatet append:as som verktygssvar |
| 3 | Modellen begär `get_premium_history` för den tilldelade försäkringen, oktober | Inga premier. Därmed undviks det byggda blocket mot ny rapport för en redan premierad månad |
| 4 | `calculate_premium_preview` med lön 60 000, premiemånad 2026-10-01, födelsedatum null | Förhandsbelopp **4 708,13 kr**: 52 125 × 4,5 % + 7 875 × 30 %. Åldersfönstret är inte kontrollerat av denna kalkyl; anställning/ålder kommer från ärendeunderlaget. Ingen premie sparas |
| 5 | Modellen föreslår `register_salary_report` med indata nedan och kort källbunden motivering | Dispatcher prövar aktuell nivå och kundscope. Tjänsten provkör och rullar tillbaka affärsskrivningen, sparar förslag + `proposed`-händelse och returnerar `pending_approval`, id `approval-demo-001` |
| 6 | Harness stoppar och returnerar väntesvar utan ytterligare modellanrop | ”Väntar på godkännande av löneunderlag för oktober. Ingen lönerapport eller premie har sparats. Förhandsberäknad premie: 4 708,13 kr.” Förslags-id och underlagsreferenser visas |
| 7 | Autentiserad operatör granskar oförändrade indata och väljer godkänn | `service.approve(approval_id, OperationContext(actor=Actor.human("karl")))`. Tjänsten validerar mot aktuellt läge och sparar lönerapport, ärendestatus approved och executed-händelse i samma transaktion. Inget modellanrop |
| 8 | Operatörsstartad fortsättning `run-demo-002`, `continuation_of="run-demo-001"`, hämtar avgjort förslag och verkställighet | Ingen återregistrering. Ett slutresultat kontrolleras: löneunderlag version 1 registrerat; premie/fakturering återstår. Samlad förbrukning ligger kvar på rotkörningen |

Föreslaget verktygsformat i steg 5, med uttryckligen fiktiva testvärden:

```json
{
  "data": {
    "personal_id_number": "199001010000",
    "employer_org_number": "5590000000",
    "period_month": "2026-10-01",
    "pensionable_salary_sek": "60000.00",
    "kind": "new",
    "corrects_version": null,
    "source": "employer",
    "source_reference": "DEMO-SALARY-OCT-001",
    "received_date": "2026-11-02"
  },
  "reason": "Arbetsgivarunderlag DEMO-SALARY-OCT-001; ingen tidigare oktoberrapport eller premie."
}
```

**Alternativa utfall ingår i samma process:** före 1 november syns inte registreringsverktyget och ärendet lämnas till handläggaren. Om ny data skapar konflikt under väntan rullas godkännandet tillbaka och förslaget står kvar som pending; det måste stämmas av och eventuellt avslås. Om operatören avslår blir fortsättningens resultat ”avslaget, ingen registrering”. Modellen får inte kalla `correct_premium_transaction` som alternativ.

## 8. Körjournal: vad agenten gjorde och varför

### 8.1 Format och skydd

JSONL betyder en JSON-händelse per rad. Föreslagen plats är `logs/agent_runs/<run_id>.jsonl`, redan under gitignorerade `logs/`. Varje händelse har `schema_version`, `event_id`, löpande `seq`, UTC-tid, run-id, root-/parent-/fortsättnings-id när relevant, team, agent, steg och typ. En ensam journalskrivare per run hindrar sammanblandning. En avbruten sista rad markeras som skadad; historiken skrivs inte om för att gömma felet.

Händelsetyper: `run_started`, `policy_resolved`, `model_returned`, `tool_intent`, `tool_completed`, `tool_denied`, `approval_wait`, `approval_observed`, `artifact_created`, `escalation_requested`, `run_ended`. Fas 3c kan lägga till delegations-/flödeshändelser med samma gemensamma fält.

Journalen sparar en **kort beslutsmotivering**, källor och verifierbart utfall. Den försöker inte återskapa modellens dolda tankegång. En förklaring är agentens uppgivna skäl, inte ett bevis för dess interna resonemang.

Full PII-indata och verktygsresultat sparas som referenser till skyddat underlag, med hash och lagringsklass. Pseudonyma kund-/försäkrings-id är fortfarande personanknutna och kräver åtkomstskydd. Den öppna journalvyn visar sanerade sammanfattningar. Skyddad historik/återstartspunkt lagras separat med begränsade OS-rättigheter och kryptering där persondata eller leverantörstillstånd ingår. Nycklar och `provider_state` hör aldrig hemma i den publika journalen.

`AI_LOG_CONTENT` ska vara av i verksamhetsprofiler även om en miljövariabel försöker aktivera den. Dagens AI-lager maskerar inte data. Harness måste därför kontrollera konfigurationen vid start, sanera fel innan publicering och förhindra att en PII-profil kör med rå innehållsloggning.

**Befintlig begränsning:** `ServiceLayer._record` sparar PII-indata och skrivresultat; `approval_requests.input` innehåller utförbara rådata. Harnessjournalens maskering tar inte bort detta. Åtkomst, retention, backup och eventuell fältmaskering för dessa försäkringstabeller måste hanteras i tjänstelagerprojektet. Audit ska vara append-only för applikationsroller, men kontrollerad gallring enligt beslutad lagringspolicy måste kunna ske.

Vald startgräns för harnessens råa konversationshistorik och återstartspunkter är **30 dagar efter att uppdraget avslutats**. Allmän körjournal innehåller inga råa personuppgifter; skyddad historik är tillgänglig endast för operatören och motorns betrodda lagring. Väntande uppdrag får inte hålla rå konversation obegränsat: efter 30 dagars väntan gallras råhistoriken och fortsatt arbete behöver nytt kontextbygge och förnyad granskning. Godkännandeärende och affärsspår gallras inte av harness. Detta är vald sandboxpolicy för harnessdata; försäkringssystemets journaler, kö och backuper behåller sin egen lagringspolicy tills den fastställts i det projektet.

### 8.2 Exempelrader från körningen

Detta är representativa, giltiga JSONL-rader; en verklig journal innehåller samtliga modell-/verktygssteg. Hashsträngarna är illustrativa. Uppskattad kostnad i exemplet är påhittad testtelemetri, inte en offert eller uppmätt modellkostnad.

```jsonl
{"schema_version":1,"event_id":"evt-01","seq":1,"timestamp":"2026-11-02T09:00:00Z","run_id":"run-demo-001","root_run_id":"run-demo-001","parent_run_id":null,"team":"forsakring","agent":"case_handler","step":0,"type":"run_started","goal":"Kontrollera och förbered oktoberunderlag","scope_ref":"scope-demo-001","versions":{"git":"0a8227c","ecosystem_hash":"example-policy-hash","rule_package":"PR-ITP1 v1.0","valid_from":"2026-11-01"},"limits":{"max_steps":12,"max_cost_usd":0.5}}
{"schema_version":1,"event_id":"evt-20","seq":20,"timestamp":"2026-11-02T09:00:30Z","run_id":"run-demo-001","root_run_id":"run-demo-001","team":"forsakring","agent":"case_handler","step":5,"type":"tool_intent","tool_call_id":"call-05","operation":"register_salary_report","input_ref":"protected-demo-input-05","input_hash":"example-input-hash","decision":{"effective":"APPROVAL","policy_ref":"example-policy-hash"},"reason":"Verifierat arbetsgivarunderlag; inga tidigare oktoberposter","evidence_refs":["read-demo-01","read-demo-02","read-demo-03"]}
{"schema_version":1,"event_id":"evt-21","seq":21,"timestamp":"2026-11-02T09:00:31Z","run_id":"run-demo-001","root_run_id":"run-demo-001","team":"forsakring","agent":"case_handler","step":5,"type":"approval_wait","tool_call_id":"call-05","approval_id":"approval-demo-001","status":"waiting_approval","business_change_executed":false}
{"schema_version":1,"event_id":"evt-22","seq":22,"timestamp":"2026-11-02T09:00:31Z","run_id":"run-demo-001","root_run_id":"run-demo-001","team":"forsakring","agent":"case_handler","step":5,"type":"run_ended","status":"waiting_approval","cost_estimated_usd":0.012,"cost_unknown_attempts":0,"pending_approvals":["approval-demo-001"]}
{"schema_version":1,"event_id":"evt-23","seq":23,"timestamp":"2026-11-02T09:10:00Z","run_id":"run-demo-001","root_run_id":"run-demo-001","team":"forsakring","agent":"case_handler","step":5,"type":"approval_observed","approval_id":"approval-demo-001","decision":"approved","decided_by":"karl","operation_event_ref":"verified-service-event-demo","result_ref":"protected-salary-result-demo"}
```

AI-anropsloggen länkas via `run_id` och `step`; affärsloggen via run-id och approval-id. `OperationResult` returnerar i dag inget event-id. Exempelradens `operation_event_ref` kan därför bara skrivas efter en betrodd sökning/avstämning, inte tas från `execute`-svaret. Föreslagen utökning är att bära `invocation_id`/tool-call-id och händelse-id genom tjänstelagret. Det gör kopplingen entydig även vid flera likadana operationer i samma körning.

`RunStore` ska från början erbjuda append av händelser, läsning av status och skyddad återstartspunkt. V1 har filimplementation och manuell återstart. Fas 3c kan använda tabeller `agent_runs`/`agent_steps` och unika sekvens-/invokationsnycklar utan att loopens affärslogik ändras. Tabellen `approval_requests` dupliceras inte.

## 9. Alla sju team: mandat, första arbete och luckor

Poddarna här är en målbild att aktivera stegvis. Även en planerad podd kräver verkliga tjänster, resursgränser och granskad montering. **Ledande agent får inte automatiskt specialistens samtliga rättigheter.** Specialister får egna delmängder och uppdrag; ingen självregistrering av nya agenter tillåts.

### 9.1 `forsakring` – börja med handläggaragenten i Fas 5

**Mandat:** utreda tilldelade ITP1-ärenden, förbereda stödjande administrativa åtgärder och sakunderlag till svar. Handläggaragenten beslutar inte om godtyckliga rättighetsändringar och skickar inte kundmail.

**Vald första arbetsuppgift i designen:** kontrollera ett nytt löneunderlag för en tilldelad försäkrad, läsa relevant försäkrings-/premiehistorik, visa förhandsberäknad premie och förbereda registrering för människans godkännande, enligt §7. Det är detta ”första handläggaruppdrag” betyder: ett avgränsat användningsfall att bygga och verifiera agenten för, inte ett nytt mandat för hela avdelningen. Fribrevförslag och rättade underlag kommer som efterföljande användningsfall när respektive profil och tester öppnats. En första agent ska kunna avsluta korrekt även när inget skrivverktyg är öppet.

**Poddar:** `kunddata`, `berakning`, `regelverk`; senare kontrollerad ärendehantering, skyddade ärendeutkast och delegering. Allmän `dokument` endast för material utan PII. `bestand` behöver inte monteras på första handläggaren.

**Befintligt som räcker:** `get_insured_overview`, `get_premium_history`, `get_salary_reports`, `calculate_premium_preview`; från giltighetsdagen registrerings-/fribrevförslag enligt tjänstens begränsningar. `correct_premium_transaction` är endast människa. Fribrevspodden måste öppnas uttryckligen i agentprofilen; exemplet i §3.4 nekar den.

**Saknas:** ärendeintag och `cases`-operationer, bilage-/källreferenser, kundscope, mottagarhandtag, fakturering från löneunderlag samt pensions-/betalningsoperationer. En anmäld död eller pågående pension ska inte ”lösas” genom att återanvända en fribrevslägesändring. Förmånstagare/efterlevandeskydd i gamla mandattexter ligger utanför aktuell produkt; första agenten får inga sådana verktyg.

**Guardrails och godkännanden:** tilldelad person/försäkring och period; inga massuttag; inga slutavräkningar eller negativ rättighetsändring via modell. APPROVAL-förslag går till handläggaren. Tveksam regel eskaleras till compliance, utgående kundsvar till kommunikation. Ärendets status ”väntar” hålls skild från sakbeslut och från verkställighet.

### 9.2 `aktuarie` – beräkningsunderlag och flaggskeppets insikt

**Mandat:** aktuariella underlag, risk-/känslighetsanalys och beståndsinsikter. Aktuarieagenten är ledande; data scientist är specialist för analytiskt underlag och datakvalitet. Ingen agent får anta en ny tariff eller skriva om historiska garantigrunder på egen hand.

**Första uppgifter:** förklara och jämföra syntetiska premiescenarier; identifiera vilka granskade mått och data som behövs för en regeländring; senare beräkna beståndseffekt med versionsbundna bas-/scenarioresultat. Första insikten kan handla om hypotetiskt IBB. Ett ändrat uttags-/garantiscenario väntar på motsvarande motor.

**Poddar:** `berakning`, `regelverk`, `bestand`, `dokument`; senare `marknadsdata` och en föreslagen `aktuariell` podd för granskade aktuariella motorer. Data scientist får aggregat och kontrollerade scenarioverktyg, inte full `kunddata`, fri SQL eller generell notebookexekvering. Specifika individuella aktuariella uppdrag kräver separat PII-mandat; det ingår inte i första profilen.

**Befintligt som räcker:** `calculate_premium_preview` för en enskild förhandskalkyl; rena premiemotorn för syntetiska scenarier. `src/analytics/` och IBB-analysen är återanvändbart beräkningsunderlag, **inte ännu en registrerad beståndstjänst eller en driftsatt Genie-integration**.

**Saknas:** kontrollerade aggregat-/snapshotoperationer, gemensamma BI-mått enligt B-029, scenariooperation med låsta antaganden och versionsreferenser; tariff/annuitets-, garanti-, FTA-/reserv- och ALM-motorer. En ny tjänst kan använda dessa beräkningar utan ändring av harnessens loop.

**Guardrails och godkännanden:** belopp beräknas i verifierad kod, inte genom modellens huvudräkning. Källperiod, regel-/parameter-/kodversion, antaganden och datakvalitet följer med varje resultat. Ej beräknat visas som ej beräknat, aldrig noll. Analysutkast behöver ingen extern handlingsgrind, men nya grunder, införande och formell rapportering granskas/godkänns av människa. Second opinion är en kvalitetskontroll och ersätter inte metodvalidering.

### 9.3 `compliance` – tolkning, produktregel och rapportunderlag

**Mandat:** compliance-agenten äger regeltolkning, styrdokumentsstruktur, gap-analys och eskaleringar. Den planerade Rapporteringsagenten samordnar tillämpliga rapporter; kontrakt och arbetsdelning för risk- och solvensbedömning preciseras i projekt 2/6 mot regelverkskartan. Teamledaren är ingång till teamet, inte en ersättning för specialistens ansvar.

**Första uppgifter:** läs och jämför en daterad källa med nuvarande tolkning; ta fram källbunden konsekvensanalys; föreslå PR-/villkorsdiff i flaggskeppets steg 1–2; gör en avgränsad complianceöversyn. Rapporteringen börjar med intern sammanställning av verifierade underlag och en lista över luckor.

**Poddar:** `regelverk`, `dokument`, `bestand`; senare föreslagen `rapportunderlag` för periodlåsta underlag och verifiering. Compliance får som standard inga kundpersonuppgifter. Vid ett eskalerat individfall överförs minimerad fråga; om individdata verkligen krävs behövs tidsbegränsat, uttryckligt PII-scope. Rapporteringsagenten får inte automatiskt samma dokumentinförandemandat som ledaren.

**Befintligt som räcker:** filunderlaget i `04_regulatoriskt/`, produktreglerna, aktuariell grund och parameterregister finns; de kan bli kontrollerad läskontext via dokumentgateway. Ingen av de sju tjänsteoperationerna räcker för regelinförande eller myndighetsrapport. En premieförhandskalkyl kan illustrera en konsekvens men utgör inte ett rapportunderlag för hela beståndet.

**Saknas:** dokument-/tolkningsdiff med källkedja, versionsbundna granskningsgrindar, rätt styrdokument, period-/mottagarspecifika rapportscheman och underlag, tillämplighetskontroll samt kontrollerad extern inlämning. Agentbeskrivningens exempel på QRT/trafikljus är planerade exempel, inte fastställt rapporteringskrav för detta ITP1-sandboxbolag. Tillämpning behöver utredas inom rapportprojektet.

**Guardrails och godkännanden:** varje slutsats har källa, avsnitt, kontrollerad version och osäkerhet. Källändring, tolkning, produktregelbeslut och teknisk release är olika saker. Tolkning och produktregelpaket kräver mänsklig grind före nästa kritiska steg. En agent får inte skriva ett nytt införandebeslut/B-nummer. Rapporteringsagenten äger sammanställning och myndighetsinlämning genom en smal rapporteringsgateway; operatören godkänner exakt rapport, mottagare och period före verkställighet (§9.4).

### 9.4 `kommunikation` – kundbrev och utgående leveranser

**Mandat:** formulera och leverera godkända meddelanden på uppdrag av andra team. Ärendelösning och rapporternas sakkontent ägs av beställande team.

**Första uppgifter:** skriv ett kundbrevutkast från verifierade sakuppgifter; kontrollera rätt mall, mottagare och sakbeslut; visa förhandsvisning för operatören. Senare en godkänd sändning med kvitto. I flaggskeppet förklarar teamet vad en antagen regeländring innebär och från när.

**Poddar:** `regelverk`, `kommunikation` och en smal föreslagen `mottagare`-podd. Mottagare ska inte innebära att hela `kunddata` monteras. Känsliga brev lagras i skyddad kommunikationsyta, inte allmän dokumentpodd. Rapporteringsagentens myndighetsinlämning använder sin egen rapporteringsgateway. Gemensam transportkod får återanvändas utan att teamen får varandras destinationer eller verktyg.

**Befintligt som räcker:** inget utskicks-/mottagarverktyg finns på bascommitten. En text kan bli ett utkast efter harnessens outputkontroll; v1 överlämnar till operatören. Individöversikten är för bred för att bli kommunikationens kontaktuppslag.

**Saknas:** mottagarhandtag, versionsbundna mallar, draft-/sändningskontrakt, granskad kanalpolicy, godkännande, outbox, idempotens och leveranskvitto. Kommunikationsgatewayen i §4.3 byggs separat från försäkringstjänstelagret.

**Guardrails och godkännanden:** rätt ärende och behörig mottagare; inget löne-/personinnehåll om det inte behövs; inga obekräftade löften eller formuleringar som antyder ett utfört sakbeslut. Godkänn exakt brev/rapport, adress, bilaga och kanal. Mallgodkännande är inte godkännande av varje utskick.

**Rekommenderad ansvarsfördelning efter operatörens avstämning:** kommunikation äger kundbrev, mail och allmän intressentkommunikation. Rapporteringsagenten äger myndighetsrapportens innehåll, validering och inlämningsprocess. Kapitalteamet äger sina order och utveckling sina releaser. Varje område har en smal gateway och mänskligt godkännande av extern handling; ingen får en allmän sänd-/verkställighetsrätt. ”Bolagets enda väg ut” i B-026 föreslås därför preciseras till **enda väg för kund- och allmän intressentkommunikation**. En sådan precisering bevarar domänansvaret och undviker en extra agentöverlämning för myndighetsrapporter, kapitalorder och releaser. Den föreslås till de gemensamma dokumenten; ingen beslutslogg ändras här.

### 9.5 `kapital` – placeringsuppföljning och paper trading

**Mandat:** analysera den simulerade portföljen mot antagen placeringsriktlinje och förbereda ombalansering. Portföljförvaltningsagenten får inga individuppgifter och ingen verklig mäklaranslutning enligt B-003/B-019.

**Första uppgifter:** förklara en avvikelse från riktlinjen; sammanställa kurser med tidsstämpel; förbereda en simulerad order med belopps-/allokeringskontroll. Första versionen väntar på Fas 2:s riktlinje och data.

**Poddar:** `regelverk`, `marknadsdata`, `portfolj`, `bestand`, `dokument`; eventuellt syntetiska beräkningar. De andra teamen får inte montera orderförmågan genom att få läsning av marknadsdata.

**Befintligt som räcker:** ingen portfölj-, kurs- eller orderoperation finns på bascommitten. Premiekalkylen är ingen investeringsmotor. Ett kontrollerat regel-/riktlinjeunderlag kan förklara mandatet när riktlinjen antagits.

**Saknas:** portfölj-/trade-modell och operationskontrakt, riktlinjelimiter, kurskälla och färskhetskontroll, premier till portföljinsättningar, värdering och orderförslag. Mappningar till poddar läggs till när tjänsterna finns.

**Guardrails och godkännanden:** kontrollerade instrument, kassa, belopps- och allokeringslimiter; inaktuella kurser stoppar förslaget. **Även simulerade portföljändringar kräver mänskligt godkännande** enligt agentens mandat; paper trade kan tekniskt vara `write`, men klassningen tar inte bort detta krav. Riktiga transaktioner är utanför scope och kan inte öppnas med en poddändring.

### 9.6 `ekonomi` – avstämning och avtal

**Mandat:** ekonomiagenten förbereder bokföring, budget, likviditetsuppföljning och finansiellt underlag. Inköpsagenten är specialist för leverantörsavtal och tredjepartsrisk. Båda förbereder beslut, utan fri betal-/signeringsrätt.

**Första uppgifter:** stäm av aggregerade premiemedel mot ekonomiskt underlag; visa dataluckor; granska ett tilldelat leverantörsavtal och föreslå frågor eller avvikelser. Inköp börjar med dokumentgranskning, inte inköpstransaktioner.

**Poddar:** `regelverk`, `dokument`, `bestand`; senare föreslagna `ekonomidata` och `avtal`, uppdelade när data-/sidoeffektsgränser skiljer sig. Inköp får tilldelade avtal och nödvändigt budgetunderlag, inte hela huvudboken. Kontaktpersoner i avtal är PII och kräver egen klassificerad avtalsyta.

**Befintligt som räcker:** ingen bokförings-, betalnings-, budget- eller avtalsoperation finns. Individernas premiehistorik är ingen ekonomisk huvudbok och är inte tillåten ersättning för ett saknat aggregat. Dokumentläsning räcker för första avtalsutredningen när gatewayen finns.

**Saknas:** dubbel bokföring/avstämningsunderlag, definierade ekonomiska mått, förslags-/bokföringsoperationer, leverantörsregister, kontraktsversioner och godkänd styrgrund. Ingen modell ska ”balansera” luckor med påhittade bokningar.

**Guardrails och godkännanden:** ingen direkt SQL eller godtycklig journalpost; verifierade källreferenser och perioder. Bokföringsändringar föreslås för mänsklig prövning i första profilen; betalning och avtalssignering kräver alltid uttryckligt godkännande. Regel-/avtalsosäkerhet eskaleras till compliance även från inköpsspecialisten.

### 9.7 `utveckling` – avgränsat ändringsförslag och releaseunderlag

**Mandat:** identifiera teknisk påverkan och förbereda testade ändringsförslag. Utvecklaragenten ansvarar även för datapipelineförslag; den får inte genom sitt utvecklingsmandat bli administratör över verksamhetens data eller sin egen säkerhetspolicy.

**Första uppgifter:** koppla godkänd PR-diff till berörd beräkning/operation och tester; leverera teknisk åtgärdslista och verifieringsunderlag. I flaggskeppet ska ett senare avgränsat kodverktyg kunna skapa patch i isolerad arbetsyta. Att den här utredningen innehåller ett kodexempel ger ingen sådan förmåga.

**Poddar:** `regelverk`, `dokument`; senare föreslagen `utvecklingsarbete` för kontrollerad källkodsläsning, patch och testkörning. Den är en ny säkerhetsgräns och kan inte gömmas i den vanliga Markdown-podden. Generella shell-/filverktyg behövs inte för de andra sex teamen.

**Befintligt som räcker:** inget agentverktyg för patch, tester eller release finns. `ServiceLayer.registry` ger operationsmetadata som kan kopplas till godkända produktregler i en kontrollerad katalog. Projektets vanliga utvecklingsverktyg är inte automatiskt monterade på verksamhetsagenten.

**Saknas:** kod-/regelspårning, isolerad ändringsyta utan hemligheter eller produktionsanslutning, testadapter med granskade kommandon, release-/migrationskontrakt, teknisk aktiveringsmarkör och kvitto. Modellskapat kodarbete måste isoleras från tjänstelagrets process och credentials.

**Guardrails och godkännanden:** agenten kan inte ändra aktiva åtkomstregister, policyfiler eller instruktioner genom en körning. Sådana ändringar lämnas som diff för mänsklig granskning. Tester körs i isolerad miljö, aldrig mot beståndet; migrationer kräver operatörens databaskoordinering enligt AGENTS.md §4.5. Driftsättning, main-merge och extern effekt kräver avsett mänskligt beslut och en låst releaseversion. Utveckling kan inte själv godkänna sitt förslag.

## 10. Delegering och flöden: det Fas 3b behöver bära från start

### 10.1 Kontraktet för ett uppdrag

Fas 3b behöver fälten och resultatmodellen, **inte en komplett multi-agentmotor**. Betrodd beställare fyller identitet, scope och budget. Modellen kan föreslå mål och bakgrund, men inte utfärda nya rättigheter.

```json
{
  "schema_version": 1,
  "task_id": "task-demo-001",
  "target_team": "aktuarie",
  "goal": "Beräkna premieeffekten av en hypotetisk IBB-ändring",
  "background": "Ett scenarioförslag; ingen antagen produktregel ändras",
  "constraints": ["Endast kontrollerade aggregat", "Ingen affärsskrivning"],
  "expected_output": "PremiumScenarioResultV1",
  "references": ["scenario-demo-001", "snapshot-demo-001"],
  "execution_scope_ref": "aggregate-scope-demo-001",
  "root_run_id": "root-demo-001",
  "parent_run_id": "compliance-demo-001",
  "flow_id": null,
  "flow_step_id": null,
  "depth": 1,
  "budget_reservation_usd": 0.05
}
```

Resultatet returnerar samma task-id, barnets run-id, `completed`/`waiting_approval`/`needs_compliance`/`needs_human`/`blocked`/`failed`/`limit_reached`/`reconciliation_required`, strukturerat underlag, osäkerheter, artifact-/evidence-referenser, väntande approval-id och kostnad. Texten är inte en beslutstoken.

### 10.2 Delegeringsregler för Fas 3c

`delegate_to_team` startar mottagarteamets **ledande agent**. Inom teamet kan ledaren beställa arbete från en uttryckligen konfigurerad specialist. Inga andra team hoppar direkt till data scientist, rapportering eller inköp. Compliance-eskaleringen är det smala undantaget i §5.3.

Barnet använder **sin egen identitet, teamnyckel och profil**; det ärver inte förälderns poddar. Dess resursmandat är det uppdraget får överföra, begränsat av mottagarens profil. Kontexten är en sammanfattning och kontrollerade referenser, inte hela historiken. Barnet får inte läsa en referens bara för att föräldern kunde det, och föräldern får inte läsa barnets känsliga resultat bara för att den beställde uppgiften. Båda riktningarna prövas. Ett team får beställa en tydligt tillåten förmåga hos ett annat team, men aldrig använda delegering för att kringgå ett globalt/uppdragsspecifikt förbud, PII-gräns eller mänsklig grind.

Valda startgränser: djup högst 2, högst 3 barn totalt per rot, ingen återgång till ett redan aktivt team i samma kedja och sekventiell körning. Varje barn får en reservation från **samma rotbudgetbok**, med de samlade taken i §6.3. Budget delas inte genom att kopiera ett maxvärde; reserverad plus förbrukad summa för alla barn/förälder får inte överstiga roten. Ej använd reservation frigörs, okänd förbrukning hålls kvar. Parallella barn kräver atomiska reservationer och är inte första leveransen.

Ett väntande barn returnerar run-/approval-referenser och propagagerar väntan till föräldern/flödet. Inga öppna modellkonversationer står och pollar medan människan granskar. Dubbel beställning med samma task-id ska hitta samma barn eller stoppas för avstämning, inte skapa ett nytt.

### 10.3 Flödesmotor och regeländringshantering

**Operatörens förtydligande 2026-10-25:** flödesmotorn byggs för återanvändbara
verksamhetsflöden i det hypotetiska AI-native företaget (MASTER_CONTEXT §1).
Regeländringen nedan är en målbild för sådan verksamhet; berörda steg avgörs av
ändringens konsekvenser. B-035:s avgränsade parameterändring och demostöd beskriver
bara en del av förmågan. Demonstrationer väljs senare bland byggda förmågor och
får ingen hårdkodad demo-knapp i bolagets ordinarie arbetsytor. Äldre hänvisningar
till flaggskeppet och dess byggsteg i denna utredning ska läsas mot den avgränsningen.

Flödesdefinitionen bestämmer ordning, in-/utdatascheman, villkor och grindar. Modellen får lösa en avgränsad uppgift inom ett steg. En grind binder käll-, underlags-, regel-, parameter- och kodversion där de är relevanta; ändrat underlag gör tidigare grind inaktuell.

```mermaid
flowchart TD
    K[Daterad regelverksändring] --> C1[1. Compliance: tolkning och konsekvens]
    C1 --> G1{Människan godkänner tolkningen}
    G1 --> C2[2. Compliance: PR- och villkorsförslag]
    C2 --> G2{Människan antar version och giltighet}
    G2 --> U[3. Utveckling: patch, tester och releaseunderlag]
    U --> G3{Människan godkänner och aktiverar låst release}
    G3 --> A[4. Aktuarie: beståndsinsikt på låst bas och scenario]
    A --> I[Intern insikt med antaganden och beräkningsbevis]
    I --> V{Behövs kundinformation?}
    V -->|Ja| C3[5. Kommunikation: utkast och mottagarurval]
    C3 --> G4{Människan godkänner exakt utskick}
    G4 --> S[Kontrollerad sändning och kvitto]
    V -->|Nej| F[Flödet slutfört]
    S --> F
```

Detta behåller agentekosystemets fem steg. Aktuariell/metodmässig förhandsvalidering är del av releaseunderlaget före steg 3:s godkännande; den senare beståndsinsikten ersätter inte den granskningen. Ingen release markeras ”i produktion” enbart för att en PR-fil fått ett B-nummer. Flödet måste skilja **antagen specifikation**, **giltighet för händelsen** och **tekniskt aktiverad implementation**.

Föreslagna stegresultat är `InterpretationProposal`, `ProductRuleProposal`, `ReleaseEvidence`, `PortfolioImpactResult` och `CommunicationDraft`. De bär versioner och referenser, inte gissade nya operationer. Exempelvis behöver insikten låst basbestånd, definierat scenario, beräkningsmotor/-version och saknade mått. Framtida regelversion per affärshändelse och release-/aktiveringsmarkör saknas på 0a8227c; det är tjänste-/domänberoenden till flaggskeppet.

I Fas 3c behövs persisterade flöden, steg och **grindbeslut** (`flows`, `flow_steps`, `flow_gate_decisions`, byggda i 3c-2: `src/agents/flows/`, `databasschema.md` §9i). För försäkringsförslag länkas befintliga `approval_requests`; övriga gateways har egna versionsbundna handlingsförslag och kvitton, med godkännandet knutet till deras handling. UI och körjournal använder ett gemensamt referensformat med område, förslags-id och status. Det ger en samlad beslutsvy utan en extra kö för löne-/fribrevförslag och utan att myndighetsrapporter eller releaser registreras i försäkringstjänstelagret. Tabeller dokumenteras och databaskörningar samordnas innan de byggs.

### 10.4 Återstart utan dubbel handling

Fas 3b:s `RunStore`, task-/run-/flow-id, statuses, budgetreservationer och versionsreferenser ska vara stabila kontrakt. Ett godkännande leder till avstämning och fortsättning, inte återspelning av hela loopen. Fas 3c lägger till en beständig tillståndsmaskin med versionsnummer, atomiskt anspråk på steg och idempotens för beställningar/handlingar. Den behöver hantera krasch före/efter proposal, godkännande, verkställighet och nästa steg.

En deterministisk ordning gör processen granskningsbar, men gör inte nätverksoperationer ”exakt en gång”. Verifierade tjänstekvitton, idempotens och manuell avstämning vid okänt utfall är fortfarande nödvändiga. Automatisk återstart är blockerad tills dessa kontrakt är byggda och testade. Ingen full minnesmotor, dynamisk agentskapning, generell MCP-klient eller parallell agentplanering behövs i Fas 3b.

## 11. Verifiering: bevisa gränserna och utvärdera modellerna

### 11.1 Motortester med FakeProvider

Tester ska injicera `AIClient(provider_overrides={"anthropic": fake, "openai": fake})`, en testkonfiguration och testlogg. `fake.requests` visar exakt vilka verktyg och underlag modellen fick. Separata FakeProvider-instanser för primär/reserv används när leverantörsbytet ska prövas. Ingen nätverksåtkomst och inga riktiga nycklar krävs.

Testerna ska inte bara kontrollera att ett verktyg saknas i listan: fejkleverantören ska ändå **försöka anropa det**. Ett räknande testverktyg/registrerad testoperation visar att implementationen inte nåddes. Databassnapshot före/efter visar att affärsdata inte ändrades.

| Fall | Förväntat bevis |
|---|---|
| Lyckad läsning och beräkning | Bara rätt data/resultat, rätt `Actor.agent`, team, run-id och steg; komplett journal |
| Okänt eller omonterat verktyg, agentnekat/teamnekat namn | Dispatcher nekar även ett påhittat call; ingen exekvering |
| Specialist försöker utöka till teamets alla poddar | Profil avvisas eller verktyget nekas; ingen rättighetsunion |
| Ny registeroperation utan poddmappning | Oupptaget verktyg är stängt; motorn behöver ingen kodändring för granskad ny mappning |
| Saknad registerrad, HUMAN_ONLY, saknad/ersatt/kommande regel | Ingen verktygsexponering eller exekvering; prövas även direkt med agentaktör mot tjänstelagret |
| Försäkrings-external satt AGENT, eller försäkrings-write utan godkänd produktregel | Tjänstelagrets golv vinner; ingen falsk rule-id eller systemidentitet som reserv |
| Dokument-, kanal- eller domänhandling försöker kringgå sin gateway | Harness och gateway nekar, extern verkställighet saknar giltigt mänskligt godkännande; handlingen flyttas inte till försäkringstjänstelagret |
| Datum 2026-10-31 respektive 2026-11-01, cachad regelstatus och indragen policy | Färsk prövning; redan visat verktyg ger inte gammal rättighet |
| Modellen skickar actor=human/system, team, run-id, session eller godkännare | Förbjudna extrafält nekas; betrodd identitet kan inte överstyras |
| Annan kund/policy/mottagare, period utanför uppdrag | Nej före dataläsning; inget otillåtet resultat lämnas till modellen |
| PII via födelsedatum i compute, dokument eller delegerat svar | Dataklassen kvarstår; ingen export till icke-PII-yta |
| Promptinjektion i kundbilaga/regeltext | Inga nya verktyg, identiteter eller destinationsrättigheter; inga hemligheter lämnas ut |
| Relativ traversal, absolut sökväg, UNC, junction/symlänk, otillåten extension | Inga läsningar/skrivningar utanför tilldelad arbetsyta eller källregister |
| Aggregat med litet urval och differensförfrågningar | Suppression/begränsning i betrodd tjänst; ingen individdata i modellförfrågan |
| APPROVAL och flera tool-calls i samma svar | Endast ett förslag före stopp, ingen affärsskrivning, resterande calls får ej-utfört-resultat |
| Agent/system försöker approve/reject | Tjänstelagret nekar; ingen godkännare spoofas |
| Mänskligt avslag, ändrad payload/version eller inaktuellt data efter väntan | Ingen blind återregistrering; nytt underlag/granskning krävs |
| Krasch vid intent, tjänstecommit, proposal eller journalappend | Ingen automatisk write-replay; status/kvittoreferenser stäms av |
| Steg-/tool-/kontext-/kostnads-/tidstak | Inget ytterligare anrop efter stopp; även felrättningar och slutstrukturering räknas |
| Reservleverantör och okänd felkostnad | Oförändrad historik, rätt team, budgetreservation kvar; okänd kostnad räknas inte som noll |
| Barn använder högre rättigheter eller budget; cykel/djupgräns | Egna profiler och gemensam rotbudget verkställs; eskalering kan överlämnas utan nytt modellanrop |
| Felaktigt slutstatus, saknad källa, obekräftat belopp, PII i publikt svar | Ingen färdigpublicering; kontrollerad överlämning och journal |
| `AI_LOG_CONTENT=true` i PII-profil, sanerings-/journalsfel | Profil/start eller publicering stoppas; inga råvärden i allmän journal |

Befintliga `tests/test_services_access.py`, `test_services_service.py`, `test_services_transactions.py`, `test_services_persistence.py`, `test_ai_client.py`, `test_ai_schema.py` och `test_ai_boundaries.py` ger en grund. Nya motortester ska koppla dessa gränser hela vägen från modellsvar till verklig testoperation. Skydd mot förbjudna SDK-importer ska utökas till eventuella agentramverk som annars kan göra egna modellanrop; det nuvarande testet kontrollerar bara paketen `openai` och `anthropic`.

**Acceptans för Fas 3b:** samtliga negativa fall inom aktiverat scope ger noll otillåten exekvering/datautlämning; löneflödet visar både godkännande och avslag; budget-/journalstopp fungerar; inga affärsskrivningar efter okänt utfall. En profil utan implementerat data-/filskydd får inte aktiveras bara för att looptesterna går grönt.

### 11.2 Databas, infrastruktur och röktest

SQLite-/FakeProvider-tester bevisar inte Lakebase-roller, Postgres-radlås eller OS-filgränser. Behörighetsprov ska därför köras med faktiska minimala testroller mot **isolerad Postgres**, inklusive förbjuden rå individläsning, affärs-DML och auditändring. Godkännandets samtidighet återanvänder `tests/test_services_postgres.py`; nya recovery-/idempotensprov tillkommer i Fas 3c. Operatören koordinerar roller och databaskörningar enligt AGENTS.md §4.5.

Ett litet verkligt modellröktest per leverantör använder syntetiska data, bara read/compute och en testkö, begränsat outputtak och budget. Det verifierar genererade scheman, verktygsloop, leverantörstillstånd, reservkedja och väntesvar. Inga externa utskick eller beståndsskrivningar ingår. Denna utredning kör inga nya modellanrop eller databasskript. Röktestet är framtida implementationstest, inte ett villkor för att leverera designen.

### 11.3 Utvärdera modellval med samma uppgifter

Starta med rollerna `fast` för klassificering, `standard` för handläggning/utkast och `deep` för regeltolkning/aktuariell granskning. Detta är arbetshypoteser. Modellnamn, priser och reserver stannar i `ai_config.yaml`; ingen modell rekommenderas här utifrån en allmän topplista.

Bygg ett versionshanterat facit med syntetiska eller granskade underlag: premiekalkyler mot verifierad motor, ofullständiga löneärenden, kommande/ersatta regler, motstridiga dokument, otillåtna anrop och flera steg med mänsklig väntan. Första jämförelsen fokuserar på försäkring och compliance/aktuarie; senare team tillför egna uppgifter.

Föreslagna startkriterier: minst 50 varierade uppgifter för handläggning och 30 för regel-/scenarioarbete, minst två körningar per modellmappning, samma verktyg/policy/underlag och separat låst sluttest. Operatören granskar modellblinda resultat. Rapportera antal fall, feltyper, variation och osäkerhet; små testmängder bevisar inte generell säkerhet.

| Dimension | Bedömning |
|---|---|
| Säkerhet och status | Noll verkställda förbjudna handlingar/utlämningar. Ett försök kan stoppas av motorn och ändå räknas som modellens kvalitetsfel. Noll felaktiga påståenden om verkställd ändring |
| Saklighet och källor | Alla kritiska belopp/status-/giltighetspåståenden verifierade; källor korrekta och täcker slutsatsen. Ingen kritisk felaktig regeltolkning får passera som säker |
| Uppgiftslösning | Föreslaget mål minst 95 % godkända handläggningsresultat och minst 90 % godkända analysutkast; osäkra fall eskaleras korrekt |
| Robusthet | Klarar saknat underlag, schemafel, reservmodell, promptinjektion och längre verktygshistorik |
| Kostnad och tid | Kostnad per **godkänt** resultat, p50/p95 tid, steg-/verktygsantal, andel reservanrop och mänsklig efterbearbetning |

Trösklarna beslutas före testet och kan skärpas för kritiska processer. En billigare modell accepteras bara om den klarar kvalitetsgolven. Leverantörsbyte ska prövas även mitt i en verktygsloop. En oberoende modellbedömning kan flagga skillnader men är inte ensam facit för en produktregel. Ändrad modell, prompt, schema, regelpaket eller policy utlöser relevanta regressioner.

## 12. Egen harness eller etablerat ramverk?

Dokumentation nedan **läst 2026-10-12**. Jämförelsen gäller den dokumenterade arkitekturen, inte genomförda integrationstester eller en utlovad paketversion. Paketversioner och beroenden ska låsas och verifieras om något ramverk väljs.

| Alternativ | Vad det ger | Passning mot B-025 och våra kontrakt | Bedömning |
|---|---|---|---|
| **Egen tunn harness** | Precis loop, profil, dispatcher, journal och väntestatus runt de två befintliga lagren | Använder `ai.bind/complete`, kanonisk historik, FakeProvider och befintlig tjänstekö direkt | Rekommenderas för Fas 3b. Vi måste själva underhålla stopp, fel och journal; håll scope smalt |
| **Claude Agent SDK** | Claude Codes loop, verktyg, sessions-/kontexthantering, hooks och MCP; Python/TypeScript | Kör Claude Code-binära runtime och dess modellanrop. Den dokumenterade vägen använder inte vår `AIClient`; skulle bryta B-025:s enda modellväg om den införs som gemensam motor | Passar bättre för isolerat utvecklingsarbete än alla bolagsteam. Separat lösning kräver uttryckligt arkitekturbeslut. [Officiell översikt](https://code.claude.com/docs/en/agent-sdk/overview) |
| **OpenAI Agents SDK** | Runner-loop, agentverktyg, handoffs, sessioner, guardrails och pauser för mänskliga beslut | Stöder provider-/adapterytor för andra modeller. En adapter mot vår `AIClient` måste ändå bevara state, teamnycklar, reservkedja, schema och kostnadslogg; försäkringens tjänstekö måste fortsatt äga försäkringsgodkännanden | Starkaste SDK-alternativet för gemensam agentmotor, men mer integration än att ansluta våra tre befintliga API-krokar. [SDK-översikt](https://developers.openai.com/api/docs/guides/agents/sdk), [modeller/providers](https://developers.openai.com/api/docs/guides/agents/models) |
| **LangGraph** | Beständig tillståndsbaserad orkestrering, mix av kod-/agentsteg och mänsklig väntan; kräver inte LangChain | Kan låta noden anropa vår AI-klient och dispatcher. Ersätter då främst delar av Fas 3c, inte mandat eller tjänstelager | Relevant vid mer omfattande flödes-/återstartsbehov. Utvärdera mot det faktiska flaggskeppsflödet innan egen komplex workflowmotor växer. [Officiell översikt](https://docs.langchain.com/oss/python/langgraph/overview) |

Två detaljer påverkar säkerhetsbedömningen. I Claude Agent SDK är `allowed_tools` en regel för automatiskt godkännande, inte en fullständig lista över vilka verktyg som finns. Tidigare allow-/permissionbeslut kan göra att `canUseTool` inte anropas. Därför räcker inte en callback ensam som bolagets säkerhetsgräns. Detta är en slutsats för vår användning av den dokumenterade prioritetsordningen. [Anthropics permissions-dokumentation](https://code.claude.com/docs/en/agent-sdk/permissions)

OpenAI skiljer på input-, output- och tool-guardrails och kan pausa med serialiserbart run-state. Agentnivåns inputkontroller körs vid första agenten och outputkontroller vid den slutliga agenten; toolkontroller gäller de function tools där de monterats. Varje affärsverktyg måste därför fortsatt skyddas vid verkställigheten. SDK-pausen får inte skapa en konkurrerande kö runt `ServiceLayer.approve`. [OpenAI guardrails och human review](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals)

**Tydlig rekommendation:** bygg den avgränsade Fas 3b-motorn själv och behåll modellagnostiken. Vi har redan provideradaptrar, schema, verktygsmeddelanden, logg och affärsgodkännande; ett ramverk tar inte över de mest verksamhetsspecifika skydden. Detta är en projektbedömning, inte ett påstående att egen kod generellt är säkrare eller billigare.

Om komplexitet i återstart, många parallella flöden eller långvarigt tillstånd börjar dominera, gör en avgränsad Fas 3c-prototyp med LangGraph bakom `RunStore`/flödeskontraktet. Om motorns loop behöver omfattande SDK-funktioner, jämför OpenAI Agents SDK med en verifierad adapter mot `src/ai/`. Båda vägarna måste klara samma negativa tester och kunna behålla tjänstelagrets godkännanden och lokala spår. Claude Agent SDK ska inte bli standardharness utan ett nytt beslut om dess leverantörsbundna modellväg.

## 13. Spårbarhet: från vision till design

| Vision/princip | Täcks av designen | Vad återstår för faktisk uppfyllelse |
|---|---|---|
| Agentteam speglar avdelningar, B-024/B-026 | Sju team, en ledande agent och tre avgränsade specialister (§9) | Byggda agenter och domänförmågor; ingen internrevision ännu |
| Specialiserade, avgränsade uppgifter | Maskinellt podd-/resursmandat, uppdrags-/resultatschema och tak | Specifika processer och första verksamhetsuppdrag måste godkännas |
| Befogenheter ligger i strukturen | Nekanden, tjänstegolv, betrodd identitet, data-/filgateway (§3–5) | Roller, scopes, filer och negativa prov måste implementeras; prompten ger ingen garanti |
| Följ vad agenten gjorde och varför | Körjournal, kort motivering, evidens, AI-/affärslogglänkar (§8) | Entydigt invocation-/event-id, skyddad lagring och retention; ingen åtkomst till dolt resonemang |
| Externa handlingar godkänns av människa, §3.5 | Stopp, exakt versionsbundet förslag och mänsklig beslutsväg | Externa gateways, styrgrund, outbox och kvitton; v1 har inga externa agentverktyg |
| Modelloberoende, B-025 | Alla modellanrop via AI-lagret; roller och gemensamma tester | Empirisk utvärdering av modeller och bättre attempt-/budgetkontrakt |
| Flaggskepp: regel till implementation och insikt | Fem deterministiska steg, versionskedja och grindar (§10) | Regelversion per händelse, releasebevis, beräkningsmotorer, beståndssnapshot och kommunikation |
| Operatören kan ta över, B-017 | Samma tjänsteoperationer och mänsklig beslutsväg; nya gateways ska ge samma manuella förmåga | UI för journal, väntan, avstämning och manuella gatewayoperationer |
| Andra AI-verktyg kan använda bolagets förmågor | Samma skill-/dispatchergräns kan senare exponeras genom MCP | Autentiserad MCP-exponering och avgränsad extern aktör; en kopplad AI-klient får inte räknas som human |

Målbilden innebär inte full autonomi. Operatören fattar införande- och verkställighetsbeslut, och internrevision behöver oberoende mandat. Harness kan bevisa att ett otillåtet verktyg inte kördes; den kan inte ensam bevisa att en juridisk tolkning eller aktuariell metod är korrekt.

## 14. Beslutsunderlag och föreslagen genomförandeordning

### 14.1 Beslutsförslag – utan nytt B-nummer

**Anta en gemensam tunn harness ovanpå `src/ai/` och tjänstelagret, med samlad `ecosystem.yaml` som körbar team-/agent-/poddpolicy.** MD-filerna är instruktioner. Effektiva förmågor är snittet av tillåtna poddar, mandat och resursgränser, med alla nekanden och tjänstelagrets golv som överordnade begränsningar. Tjänstelagret äger försäkringsgodkännanden; harness äger körning, väntan och journal. Interna isolerade dokumentutkast tillåts genom en snäv gateway; införande av gällande dokument och externa handlingar kräver människa. Data-/filskydd krävs före aktivering av berörd podd. Fas 3b inför stabila kontrakt för Fas 3c men ingen generell workflowmotor. Automatisk återspelning av skrivningar tillåts först efter verifierad idempotens och avstämning. Byggordningen enligt B-028 består.

Operatören godkände designinriktningen i chatten 2026-10-12 och preciserade avgränsningen: **försäkringstjänstelagret förblir strikt kopplat till försäkringssystemet**. Ingen generell utökning med dokument-, ekonomi-, kommunikations- eller utvecklingsoperationer ska göras där. De områdena får egna avgränsade gateways; harness förenar deras kontroller och spårbarhet. Godkännandeärenden ägs av rätt område och kan samlas i en gemensam UI-vy.

Operatören överlät val av startgränser, vilka nu är angivna i §5.1–5.2, §6.3, §8.1 och §10.2. Första planerade handläggaruppgiften är nytt löneunderlag enligt §7 och §9.1. Rekommenderad kanal-/domänfördelning i §9.4 låter rapporteringsagenten äga myndighetsinlämning och kommunikation äga kund-/allmänna meddelanden. Detta preciserar B-026 och genomför B-025/B-028; produktpaket, tjänsteregister, produktregler och beslutslogg ändras inte genom dokumentuppdateringen.

### 14.2 Föreslagna textändringar i andra dokument

Inga av dessa ändringar är genomförda i denna leverans; delade dokument och parallellt tjänstelagerarbete lämnas som förslag enligt uppdraget.

| Dokument | Föreslagen ändring |
|---|---|
| `agentekosystem.md` §4.1 och §13 | Ange samlad `ecosystem.yaml` som vald körprofil enligt operatörens godkända inriktning; hänvisa till denna design för nekanden, scopes och versionering. MD-instruktioner ger inga befogenheter |
| `agentekosystem.md` §5.2–5.4 | Skilj tjänsteoperation, ren beräkning och isolerat dokumentutkast. Visa full policykedja, smal mottagarpodd och att klass/PII aldrig kan nedklassas av ett omslag |
| `agentekosystem.md` §4.2–4.3 och §6 | Lägg till explicit väntestatus, ingen automatisk write-replay, RunStore-kontrakt, gemensam rotbudget och versionsbundna flödesgrindar. Försäkringens godkännandekö förblir tjänstelagrets; andra gateways äger sina handlingar |
| `agentekosystem.md` §8 och §12 | Flytta dataroller och resurskontroll till före första PII-podden. Försäkringsprofiler delar försäkringens kö. Precisera kommunikationens ”enda väg ut” till kund-/allmänna meddelanden; rapportering, kapital och utveckling har egna avgränsade verkställighetsvägar |
| `agentkarta.md` §1, §3 och §5 | Länka `harness.md`, skriv initialt ”design utredd, implementation återstår”; behåll alla agenter som ej byggda. Beskriv teamingång/specialistgräns och femstegsflaggskeppet |
| `agentkarta.md` §2 | Begränsa första handläggarmandatet till nytt löneunderlag inom ITP1-scope utan efterlevandeskydd. Rapportering äger myndighetsinlämning; kommunikation äger kund-/allmänna meddelanden. Planerade rapporttyper är inte beslutade skyldigheter |
| `MASTER_CONTEXT.md` §3.8, §4b och §7 | Förtydliga att det gemensamma tjänstelagret gäller försäkringssystemet. Lägg till `02_system/harness.md` för den godkända designinriktningen om gemensam motor, policy och journal; övriga verksamhetsområden har egna gateways. Runtime är ännu inte byggd och byggordningen består |

Förslag för **ATT_GORA Fas 3b/3c**, med befintliga id kvar:

| Punkt | Föreslagen precisering och klart-kriterium |
|---|---|
| 3b-1 | Schema för samlad ecosystem-policy, strikt validering, effektiva profiler/förklaringar, versionsbild, RunRequest/RunResult. Formatfrågan är avgjord i chatten; implementation är fortsatt öppen. Använd startgränserna i harness.md §6.3 |
| 3b-2 | Upptäck operationer via registry/decision, explicit poddmappning utan jokertecken; generera action-schema med operationens modell och reason, använd execute. Nya operationer öppnas först efter mappning och registerbeslut |
| 3b-3 | Dispatcherprövning av namn, identitet, scope, klass och PII; OS-/datagränser före poddaktivering; negativa tester även när modellen hittar på ett anrop |
| 3b-4 | Kontextbygge, append-only kanonisk historik, definierade modell-/verktygssteg, begränsad felrättning, budgetreservation och okänd kostnad; inga extra anrop efter stopp |
| 3b-5 | Hantera pending_approval, återstående tool-calls, väntesvar och länkad manuell fortsättning; återanropa inte redan godkänd operation. Förbered separata review-/flödesgrindar utan dubbel tjänstekö |
| 3b-6 | Versionssatt JSONL och RunStore, skyddad historik/återstartspunkt, PII-policy, krasch-/avstämningsstatus och länkar till befintliga loggar |
| 3b-7 | Premieförhandsberäkning och tillåtna tjänsteläsningar först; kunddata kräver roller/scope. Kontrollerad regelverksläsning och isolerade dokumentutkast när gateways byggts. Pod-kolumn i skillkatalogen |
| 3b-8 | FakeProvider-flöden, negativa fall, datum-/policybyte, budget-/journalfel och godkännande/avslag. Isolerade Postgres-/filbehörighetsprov och avgränsat verkligt modellröktest |
| 3c-1 | Strukturerad delegering via teamledare, egen barnidentitet, dubbelriktad dataprövning, globalt bevarade förbud, task-id, gemensam rotbudget, djup-/antal-/cykeltak och propagagerad väntan |
| 3c-2 | Persisterad flödes-/stegtillståndsmaskin och versionsbundna grindbeslut; länka försäkringens befintliga tjänstekö och övriga gateways separata handlingsreferenser. Samlad UI-vy utan generellt bolagstjänstelager. Före automatisk recovery: invocation-/idempotenskontrakt, policyversion, kvitton och kraschprov. Dokumentera schema före samordnad databasändring |
| 3c-3 | Femstegsflaggskeppet med godkänd käll-/PR-version, testad och låst release, aktiveringsbevis, reproducerbar beståndsinsikt och godkänt utskick. Lista saknade domän-/kanaltjänster som beroenden |

Flytta raden ”egen Lakebase-roll för PII-poddar” från **Senare** till beroende för 3b-3/3b-7. Lägg till ”modellutvärdering med facit för försäkring och compliance/aktuarie” och ”avgränsade gateways för dokument och senare respektive verksamhetsområde” som separata uppgifter. Första handläggarflödet är ett nytt löneunderlag; fribrevförslag kommer senare. Utredningen har levererat designunderlag och inriktningen är godkänd; implementeringspunkterna ska inte bockas av av detta dokument.

### 14.3 Kvarstående frågor inför senare implementation

1. Vilken lagringstid och åtkomst ska gälla för försäkringssystemets PII i tjänstekö, affärslogg och backup? Harnessens råhistorik har fått gränsen 30 dagar; den gallrar inte försäkringsspår.
2. När ska oberoende internrevision få egen läsprofil och team? Den ingår inte bland de sju och kan inte granskas oberoende av en agent som även äger förändringarna.

Motor-/formatvalet och delegeringen av startgränser är redan avstämda. Förslaget att utöka försäkringstjänstelagret till andra verksamhetsområden är borttaget enligt operatörens instruktion. De kvarstående frågorna hindrar inte nästa steg i harnessdesignen.

### 14.4 Upptäckt dokumentdrift utanför denna leverans

`BESLUTSLOGG.md` B-025 anger att AI-röktestet godkändes 2026-10-11. `ATT_GORA.md` och företagsöversikten beskriver det fortfarande som kvarstående/ännu inte kört. Det är motstridiga statusuppgifter som bör stämmas av med operatören, inte rättas genom antagande här. Denna design använder därför FakeProvider som verifierad testmöjlighet och lovar inget om statusen för ett nytt riktigt röktest.

## 15. Underlag och källor

Lokalt underlag på bascommitten: `MASTER_CONTEXT.md`, `BESLUTSLOGG.md`, `ATT_GORA.md`, `02_system/agentekosystem.md`, `agentkarta.md`, samtliga tio filer i `02_system/agenter/`, `ai_abstraktion.md`, `tjänstelager.md`, `02_system/Agentsystem/regelförändringsflöde.md`, `03_skills/skillkatalog.md` och `projekt/08_företagsöversikt/foretagsoversikt.html`.

Kontrollerade kodkontrakt: `src/ai/client.py`, `types.py`, `config.py`, `tracing.py`, `providers/fake.py`; `src/services/contract.py`, `access.py`, `service.py`, `approvals.py`, `events.py`, `rules.py`, `errors.py` och operationsmodellerna. Gränstester och databas-/transaktionsprov lästes som verifieringsunderlag. Ingen databas eller extern tjänst ändrades.

Externa primärkällor är länkade vid respektive jämförelse i §12 och lästa 2026-10-12. Alla rekommenderade nya kontrakt, gränser och byggsteg är projektets designförslag; de ska inte läsas som redan implementerade ramverksfunktioner.

**Leveranskontroll 2026-10-12:** YAML-exemplet lästes med kontroll av dubbla nycklar, podd-/team-/agentsamband och gränser. Operationsmappningarna och genererade ToolSpec-scheman kontrollerades mot bascommitten; den exempelprofilen ger sex verktyg 12 oktober och sju 2 november, inklusive de två uttryckligen föreslagna dokumentverktygen. Löneindata validerades mot `SalaryReportInput`, JSON/JSONL lästes och Pythonexemplet syntaxkontrollerades. Premiemotorn bekräftade 4 708,13 kr. De tre Mermaid-diagrammen granskades som text. **35 befintliga tester passerade** i `test_services_access.py`, `test_ai_boundaries.py` och `test_ai_schema.py`, utan nätverk/databas. Pytest använde en separat temporär katalog under worktreens gitignorerade `logs/`. Detta verifierar designens underlag och exempel; den framtida harnessens negativa tester och aktiva guardrails är ännu inte byggda eller körda.

**Avstämningsuppdatering 2026-10-12:** tjänstelagrets försäkringsgräns, första arbetsuppgiften, områdenas verkställighetsansvar och konkreta startgränser är införda i designen enligt operatörens återkoppling. YAML-/JSON-/JSONL-exemplen och Pythonexemplets syntax kontrollerades på nytt; kostnadsgränserna överensstämmer mellan profil, journalexempel och text. Operationsscheman och verktygsantalet sex/sju är oförändrade. Endast detta dokument ändrades.
