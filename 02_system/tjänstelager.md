# Tjänstelagret

> **Status:** 🟡 Beslutat (**B-028**), byggs i Fas 1f – **T1, T2 och T4 klara**. **T3 klart** för den överenskomna omfattningen: transaktionsgräns, `register_salary_report`, `set_policy_paid_up` och `correct_premium_transaction`, medan `terminate_policy` är uppskjuten (§9.1). Verifierat mot isolerad Postgres och migrerat i Lakebase 2026-10-11. **Fas 4 (handläggar-UI:t):** läsoperationer för godkännandekön och händelseloggen, samt anslutning, stamdata och arbetsgivare (§9.2). Kod: `src/services/`, register: `src/services/access_register.yaml`, förteckning: [tjänstelager_operationer.md](tjänstelager_operationer.md).
> **Bygger på:** B-017 (människa som fullständig operatör), B-020 (backend för två klienter), B-022 (försäkringsmodellen), B-026 (agentekosystem). Operationer: B-030 (T3), B-032 (anslutning och stamdata, Fas 4)
> **Relaterat:** `02_system/agentekosystem.md` (harness, skill-poddar), `01_domän/produktregler/` (reglerna operationerna implementerar), `02_system/databasschema.md`

---

## 1. Syfte

Alla operationer mot försäkringssystemet – att läsa och ändra försäkrade, försäkringar, förmåner, lägen och premier – går genom **ett gemensamt tjänstelager**. Samma operation används av:

- **handläggaren** via handläggar-UI:t (Fas 4),
- **agenter** via harness, där operationen blir ett verktyg i en skill-pod,
- **skript och batchkörningar** som operatören startar.

Det ger fyra saker på en gång:

1. **En implementation per affärsregel** – samma validering oavsett vem som anropar.
2. **Samma spår för människor och agenter** – varje ändring loggas med vem som gjorde den och varför (B-017).
3. **En plats att sätta gränser för agenter** – inklusive flaggan *endast handläggare* (§4).
4. **Data för BI** – händelseloggen blir historik att analysera (delprojekt 2).

---

## 2. Placering i arkitekturen

```
 Handläggar-UI (Fas 4)      Agenter (harness)        Skript / batch
        │ FastAPI                │ skill-poddar           │
        └───────────────┬────────┴────────────────────────┘
                        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ Tjänstelagret  src/services/                                  │
 │   operationskontrakt · aktörskontroll · agentåtkomst ·        │
 │   godkännandekö · händelselogg                                │
 └──────────────┬───────────────────────────────┬───────────────┘
                ▼                               ▼
 Beräkningar (rena funktioner)          Databas (Lakebase via
 src/skills/calculation/ m.fl.          SQLAlchemy, src/models/)
 ← produktregler i 01_domän/produktregler/
```

**Regel:** ingenting utom tjänstelagret skriver till försäkringstabellerna. Befintliga engångsskript för schema, seed och genererad historik får fortsätta under uppbyggnaden och flyttas över efter hand.

Beräkningar som premiemotorn förblir rena funktioner utan databasåtkomst; tjänstelagret anropar dem. Agentverktyg byggs ovanpå tjänstelagrets operationer – inte direkt på beräkningarna eller databasen.

---

## 3. Operationskontrakt

Varje operation deklarerar:

| Fält | Innehåll |
|------|----------|
| `name` | Engelska `snake_case`, t.ex. `register_salary_report`. Blir verktygsnamnet för agenter |
| `description` | Vad operationen gör och när den används (svenska) |
| `input` / `output` | Pydantic-modeller – indatamodellen blir direkt verktygsdefinitionen för agenter (`ToolSpec.from_model`) |
| `kind` | `read` / `compute` / `write` / `external` – samma klasser som sidoeffektsklasserna i B-026 |
| `rules` | Produktregler som operationen implementerar, t.ex. `["PR-ITP1-001"]` – spårbarhet regel → kod |
| `pii` | Om operationen läser eller exponerar personuppgifter |

Vad agenter får göra med operationen står **inte** i operationen utan i registret (§4) – så att gränserna kan ändras på ett ställe.

Skiss:

```python
@operation(
    name="register_salary_report",
    description="Registrerar pensionsmedförande lön för en utbetalningsmånad (ny rapport eller rättelse).",
    kind="write",
    rules=["PR-ITP1-013", "PR-ITP1-014", "PR-ITP1-017"],
    pii=True,
)
def register_salary_report(ctx: OperationContext, data: SalaryReportInput) -> SalaryReportResult:
    ...
```

---

## 4. Agentåtkomst – registret och flaggan *endast handläggare*

Vad agenter får göra bestäms i **registret** `src/services/access_register.yaml` – en fil med en rad per operation. Vill du ändra vad agenter får göra ändrar du nivån på raden; ändringen går via commit och merge som allt annat. Handläggare får utföra alla operationer (B-017); registret kan senare utökas med handläggarroller om bolaget får fler personer.

```yaml
operations:
  get_insured_overview: AGENT
  register_salary_report: APPROVAL
  correct_premium_transaction: HUMAN_ONLY
```

Varje operation har en av tre nivåer:

| Nivå | Kod | Vad en agent kan göra | Exempel |
|------|-----|------------------------|---------|
| **Agent** | `AGENT` | Utföra direkt – om operationen ingår i agentens skill-poddar | Läsa försäkringsöversikt, förhandsberäkna premie |
| **Agent med godkännande** | `APPROVAL` | Förbereda. Operationen utförs först när en handläggare har godkänt (§6) | Registrera lönändring, sätta försäkring i fribrev |
| **Endast handläggare** | `HUMAN_ONLY` | Ingenting. Operationen syns inte som verktyg; agenten kan bara lämna över ärendet till en handläggare | Avsluta försäkring, rätta historiska premietransaktioner, ändra identitetsuppgifter |

**Effektiv nivå** är den strängaste av registrets nivå och tre golv:

| Golv | Effekt |
|------|--------|
| Operationen saknas i registret | `HUMAN_ONLY` – agentåtkomst måste öppnas uttryckligen |
| Operationen är `external` (påverkar omvärlden, §3.5) | Minst `APPROVAL` |
| Operationen är `write`/`external` och någon av dess produktregler har inte granskningsstatus `godkänd` (eller saknar regel) | `HUMAN_ONLY` – agenter rör bara det som vilar på en godkänd produktregel |

Registret kan alltså öppna för agenter, men aldrig förbi ett golv. Statusen läses ur `01_domän/produktregler/` (`services/rules.py`). Regelpaketet PR-ITP1 v1.0 antas **som helhet** genom ett samlat införandebeslut; utan det har varje regel status *specificerad* och räknas som ej godkänd. Paketet infördes genom **B-031** med giltighet från 2026-11-01, så reglerna är *kommande* till dess. Paketet räknas som infört när paketets `README.md` har raden `**Införandebeslut:** B-nnn` (överenskommelse med delprojekt 4). Står där också `**Gäller från:** ÅÅÅÅ-MM-DD` och dagen inte har kommit är reglerna *kommande* och räknas fortfarande som ej godkända – agenter rör inte framtida produktregler. En regel märkt *ersatt* är alltid ej godkänd, och det äldre formatet `**Granskningsstatus:** utkast/godkänd/ersatt` stöds fortfarande. Allt som inte går att läsa räknas som ej godkänt. En registerrad för en operation som inte finns ger fel vid start, så att stavfel inte tyst lämnar en operation stängd.

Tre saker hålls isär: **godkänd specifikation** (regelstatus och införandebeslut), **giltighet för en händelse** (`Gäller från`, och för beräkningar periodens parametrar – t.ex. premiemånadens inkomstbasbelopp) och **teknisk implementation** (vilka operationer som anger regeln, se förteckningen). Ett B-nummer i README bevisar bara det första. Varje utförd ändring loggar därför regelstatus och filversion vid verkställigheten i händelseloggens `detail`, t.ex. *Regelstatus: PR-ITP1-014 v1.0 kommande, gäller från 2026-11-01; paket PR-ITP1 v1.0 infört B-031, gäller från 2026-11-01*. Handläggare kan utföra operationerna före giltighetsdagen (B-017); loggen visar då att regeln inte gällde än.

**Regler:**

1. **Strängast som standard.** Saknas operationen i registret blir den `HUMAN_ONLY`.
2. **Kan bara skärpas förbi golven.** Team och poddar kan neka ytterligare operationer men aldrig öppna en `HUMAN_ONLY`.
3. **Verkställs i två lager:**
   - **Tjänstelagret** kontrollerar aktören vid varje anrop. En agent som anropar en `HUMAN_ONLY`-operation får ett fel – oavsett hur anropet kom dit. Det här är det egentliga skyddet.
   - **Harness** visar aldrig `HUMAN_ONLY`-operationer som verktyg, så agenten försöker inte ens.
4. **Bara en människa kan godkänna** ett agentförslag, och godkännandet loggas med både förslagsställare och godkännare.
5. **Registret är versionerat.** Varje ändring syns i en diff och godkänns vid merge. Den genererade förteckningen **[tjänstelager_operationer.md](tjänstelager_operationer.md)** (T4) visar för varje operation typ, produktregler och deras status, PII, registrets nivå, effektiv nivå och varför – t.ex. *APPROVAL i registret men HUMAN_ONLY eftersom PR-ITP1-014 är specificerad*. Den skapas med `python scripts/documentation/list_operations.py` (utan databas och utan modellanrop) och hämtar effektiv nivå från `ServiceLayer.decision()`; ett test fallerar om filen inte stämmer med koden, registret och regelstatusen.

---

## 5. Aktörer och kontext

Varje anrop bär ett `OperationContext`:

| Fält | Innehåll |
|------|----------|
| `actor` | Vem som anropar: `human` (handläggare, t.ex. operatören), `agent` (agent-id + team) eller `system` (skript/batch som operatören startar) |
| `reason` | Motivering – obligatorisk för `write` och `external` |
| `run_id` | Agentkörningen (för agenter) – kopplar till körjournal och AI-lagrets anropslogg |
| `case_id` | Ärendet operationen hör till (`CASE-NNNNNN`, §9.3). Sätts av tjänstelagret ur indatans `case_number` om anroparen inte anger det |

`system` behandlas som handläggare i åtkomstkontrollen – i v1 är det alltid operatören som startar skripten – men loggas separat.

---

## 6. Godkännande

1. En agent anropar en `APPROVAL`-operation.
2. Tjänstelagret validerar indata och regler – förslaget ska vara giltigt redan när det läggs. En `write`-operation **provkörs** mot aktuellt databasläge och rullas tillbaka; ett förslag som inte går att genomföra (saknat underlag, fel läge, dubblett) avvisas direkt i stället för att hamna i kön. `external` provkörs aldrig.
3. Ett **godkännandeärende** sparas (operation, indata, motivering, föreslagen av, `run_id`) med status `pending`, och agenten får svaret *väntar på godkännande* med ärende-id.
4. Handläggaren ser kön i handläggar-UI:t (`/godkannanden`, [handläggar-ui.md](handläggar-ui.md)), granskar och godkänner eller avslår. Det planerade CLI:t byggdes inte; kön läses med `list_approval_requests`. Bara en människa (`human`) kan godkänna eller avslå – inte en agent och inte ett skript.
5. Vid godkännande körs operationen **på nytt mot aktuellt läge** (data kan ha ändrats), utförd av handläggaren, med agenten angiven som förslagsställare.

Kön ligger i tjänstelagret – inte i harness – så att människor ser alla förslag på ett ställe oavsett vilken agent eller vilket flöde som lade dem. Det justerar B-026, där harness skapade godkännandeärenden; harness tar nu bara emot svaret *väntar på godkännande*.

### 6.1 Transaktionsgräns

Varje anrop till tjänstelagret är **en databastransaktion** (`services/transaction.py`). Det som hör ihop sparas tillsammans eller inte alls:

| Anrop | Sparas i samma transaktion |
|-------|----------------------------|
| Utförd operation | Affärsändringen + loggraden `executed` |
| Agentförslag | Godkännandeärendet + loggraden `proposed` |
| Godkännande | Ärendets status `approved` + affärsändringen + loggraden `executed` (med förslagsställare och godkännande-id) |
| Avslag | Ärendets status `rejected` + loggraden `rejected` |
| Nekat agentförsök | Loggraden `denied` |

Fallerar något steg – operationen, loggraden eller själva commit – rullas allt tillbaka. Ett godkännande som fallerar lämnar alltså ärendet som `pending`; det kan avslås eller godkännas på nytt, och ändringen kan aldrig ha sparats utan sin loggrad eller sin status.

**Samtidiga godkännanden.** Godkännandet börjar med ett atomiskt anspråk på ärendet: `UPDATE approval_requests SET status = 'approved' … WHERE id = … AND status = 'pending'`. I Postgres (Lakebase) tar uppdateringen radlås: ett andra samtidigt godkännande väntar tills det första har gjort commit, prövar sedan villkoret på nytt och får ”redan approved”. Rullas det första tillbaka tar det andra över. Samma ärende kan därför aldrig verkställas två gånger, varken vid upprepade eller samtidiga anrop.

**Operationerna äger inte transaktionen.** De får sessionen via `ctx.session` men får inte göra `commit`, `rollback` eller stänga den – tjänstelagret stoppar en commit och avbryter anropet om transaktionen avslutats. Utan databas (tester) finns ingen rollback; kön i minnet återställer då själv sina ändringar om anropet fallerar.

---

## 7. Händelselogg

Varje utförd `write`- eller `external`-operation ger en rad i en append-only händelselogg:

| Fält | Innehåll |
|------|----------|
| tid, operation, regler | Vad som gjordes, enligt vilka produktregler |
| aktör, förslagsställare, godkännande-id | Vem som utförde, vem som föreslog, vilket godkännande |
| `run_id`, `case_id`, motivering | Koppling till agentkörning och ärende, och varför |
| berörda objekt | Försäkrad, försäkring, förmån – för att kunna visa historik per kund |
| indata, resultat | Enligt operationens PII-policy |

Läsningar av personuppgifter (`pii=True`) loggas också – vem tittade på vem – i linje med GDPR:s krav på spårbar åtkomst.

---

## 8. Relation till harness och skill-poddar

- En skill-pod listar operationer (och vid behov rena beräkningar).
- Harness bygger verktygsdefinitioner ur operationernas indatamodeller och **filtrerar bort `HUMAN_ONLY`**.
- Harness anropar tjänstelagret med agentens aktör och `run_id`. Ett `APPROVAL`-anrop ger *väntar på godkännande*, som agenten rapporterar vidare.
- Skill-kontraktets `side_effect` i B-026 motsvaras av operationens `kind`. Den nya flaggan `agent_access` kompletterar.

---

## 9. Byggordning (Fas 1f)

| Steg | Innehåll |
|------|----------|
| **T1** | Operationskontrakt, operationsregister, åtkomstregistret med golv och regelstatus, aktörer, åtkomstkontroll (§4–5), godkännandemekanism och händelselogg (i minnet/fil – databastabellerna i T3) – med tester som visar att en agent inte kan utföra `HUMAN_ONLY` |
| **T2** | Första läsoperationerna: försäkringsöversikt per försäkrad, premiehistorik, förhandsberäkning av premie (premiemotorn, PR-ITP1-001) |
| **T3** | Godkännandekön och transaktionsgränsen (§6.1) samt de första skrivoperationerna: `register_salary_report` och `set_policy_paid_up` (`APPROVAL`), `correct_premium_transaction` (`HUMAN_ONLY`). `terminate_policy` är uppskjuten (§9.1). Planerades som `register_salary_change` – namn och betydelse ändrades när modellen stämdes av (§9.1) |
| **T4** | Genererad förteckning över alla operationer med registrets nivå, effektiv nivå och skäl, typ, regler och PII |

Regelspecifika operationer (uttag, paus, återupptagande, garanti, pensionsbelopp) byggs på produktreglerna från delprojekt 4, antagna genom B-031 (gäller från 2026-11-01), tillsammans med pensions- och betalningsmotorn. Handläggar-UI:t (Fas 4) är byggt ovanpå tjänstelagret (v1 2026-10-12, [handläggar-ui.md](handläggar-ui.md)); sist kommer agentlagret (harness, Fas 3b, och handläggaragenten, Fas 5).

**Tabellerna** `operation_events` och `approval_requests` (`databasschema.md` §9b–9c) används automatiskt när tjänstelagret har en databasanslutning: händelsen skrivs i samma transaktion som ändringen, och godkännandekön överlever omstarter. Utan databas hamnar loggen i fil och kön i minnet.

**Tester:** tjänstelagret testas mot en SQLite-databas i minnet med samma modeller som Lakebase (`tests/conftest.py`, fixturen `insurance_db`). Modellerna är portabla utan att Postgres-DDL:en ändrats (`databasschema.md` §12). I produktion används `services.db.database_session_factory()` mot Lakebase via `DATABASE_URL`. Transaktionsgränsen och samtidiga godkännanden testas i `tests/test_services_transactions.py`; samtidigheten mot en SQLite-fil (`insurance_file_db`) där databasen köar transaktionerna. Det bevisar inte Postgres radlås – samma scenarier, samtidiga anrop till skrivoperationerna och T3-migrationen finns i `tests/test_services_postgres.py` och körs när `SERVICES_TEST_POSTGRES_URL` pekar på en **isolerad** Postgres (aldrig Lakebase-beståndet; `DATABASE_URL` vägras). Verifierat 2026-10-11 mot databasen `svc_test` i Lakebase-projektet (Postgres 17, READ COMMITTED): alla 7 passerar. Varje test skapar och tar bort ett eget schema.

**Byggda operationer** – med registrets nivå. Effektiv nivå och skäl (t.ex. att skrivningarna är `HUMAN_ONLY` för agenter till 2026-11-01, då PR-ITP1 v1.0 börjar gälla) står i den genererade förteckningen [tjänstelager_operationer.md](tjänstelager_operationer.md).

| Operation | Typ | Produktregler | PII | Register |
|-----------|-----|---------------|-----|----------|
| `get_insured_overview` | `read` | – | Ja | `AGENT` |
| `get_premium_history` | `read` | – | Ja | `AGENT` |
| `get_salary_reports` | `read` | – | Ja | `AGENT` |
| `calculate_premium_preview` | `compute` | PR-ITP1-001 | Nej | `AGENT` |
| `register_salary_report` | `write` | PR-ITP1-013, -014, -017 | Ja | `APPROVAL` |
| `set_policy_paid_up` | `write` | PR-ITP1-013 | Ja | `APPROVAL` |
| `correct_premium_transaction` | `write` | PR-ITP1-001, -014, -017, -019, -032 | Ja | `HUMAN_ONLY` |
| `list_approval_requests` | `read` | – | Ja | `HUMAN_ONLY` |
| `count_approval_requests` | `read` | – | Nej | `HUMAN_ONLY` |
| `get_operation_events` | `read` | – | Ja | `HUMAN_ONLY` |

| `enroll_insured_person` | `write` | PR-ITP1-012, -013 | Ja | `APPROVAL` |
| `update_current_salary` | `write` | – | Ja | `HUMAN_ONLY` |
| `update_contact_details` | `write` | PR-ITP1-031 | Ja | `HUMAN_ONLY` |
| `register_employer` | `write` | PR-ITP1-012 | Ja | `HUMAN_ONLY` |
| `list_employers` | `read` | – | Nej | `AGENT` |

`list_approval_requests`, `count_approval_requests` och `get_operation_events` byggdes för handläggar-UI:t (Fas 4). De läser godkännandekön och händelseloggen som operationer, så att även läsningen av dem loggas. De är `HUMAN_ONLY`: kön och loggen är handläggarens kontrollyta, och agenter ska inte se andras ärenden (B-006). Händelseloggen per försäkrad väljs på indata och resultat (personnummer, försäkringsnummer, premieradens id), eftersom loggen saknar en egen kolumn för berörda objekt (§7).

### 9.1 Skrivoperationerna i T3 – vad som stöds och vad som blockeras

Modellbehov och avgränsning stämdes av med operatören 2026-10-11 (**B-030**). En operation stöder bara de fall som står här. Övriga fall ger `BlockedError` med skäl och regel (manuell prövning) eller `ConflictError` vid dubblett eller inaktuellt läge, och ändrar ingenting. Alla tre låser berörda rader (`SELECT … FOR UPDATE` på person, försäkring eller premierad) så att samtidiga anrop prövas i tur och ordning; databasens unikhetsregler är sista skyddet (krock → `ConflictError`).

**`register_salary_report`** (ny tabell `salary_reports`, `databasschema.md` §8b) – pensionsmedförande lön (PR-ITP1-014) per person, arbetsgivare och utbetalningsmånad. Skiljs från aktuell lön på personen och från premien.
- *Stöds:* ny rapport (`kind="new"`, version 1) och rättelse (`kind="correction"`, ny version som pekar på den gällande; `corrects_version` måste vara den gällande). Uttrycklig noll; en månad utan rad saknar rapport. Ursprung (`employer`/`manual`), avsändarens referens och mottagningsdag sparas. Rapporten skapar ingen premie och räknar inte om gamla premier – en rättelse av en månad med premie redovisar premien, som rättas med `correct_premium_transaction`.
- *Skydd:* en dubblett för samma månad ersätter inte den gällande rapporten (PR-ITP1-017); samma avsändarreferens registreras inte två gånger; en rättelse som inte ändrar lönen eller utgår från en inaktuell version avvisas.
- *Blockeras:* annan arbetsgivare än den försäkrades nuvarande (anställningshistorik saknas i modellen), månad före ITP1-tillhörighet eller anställning, månad efter anställningens slut (slutlön/bonus prövas manuellt, PR-ITP1-013), framtida månad, mottagningsdag i framtiden eller före månaden, avliden försäkrad, och ny rapport för en månad som redan har premie från premiehistoriken.

**`set_policy_paid_up`** (befintlig `policy_states`) – arbetsgivarens avanmälan: anställningens sista dag registreras på den försäkrade (status `terminated`) och försäkringen går över i fribrev dagen efter (PR-ITP1-013).
- *Stöds:* försäkring med öppet `premium_paying` och utan uttagsläge i tidslinjen; slutdagen senast i går (fribrev från senast i dag). Premieperioden stängs, `paid_up` öppnas och hela tidslinjen valideras (ett öppet läge, inga överlapp).
- *Blockeras:* pension startad eller avslutad (ett läge per försäkring kan inte uttrycka fribrev samtidigt med pågående eller pausad pension – det kräver att premieläget skiljs från pensionsläget, UTTAG_GEMENSAMT), framtidsdatering (läsningen tolkar den öppna raden som dagens läge), fler premiebetalande försäkringar för personen, premie eller löneunderlag för månader efter slutdagen, avliden eller pensionerad person, och fribrev av andra skäl än avslutad anställning (t.ex. 66 år, där frivillig fortsättning enligt PR-ITP1-016 inte kan prövas). Ett redan registrerat annat slutdatum är en konflikt.

**`correct_premium_transaction`** (ny kolumn `premium_transactions.corrects_transaction_id`, `databasschema.md` §8) – lönerättelse av en premierad (PR-ITP1-019 p.1–2). Ursprungsraden ändras aldrig; en länkad `adjustment`-rad med differensen och fullt underlag skapas med status `pending`.
- *Stöds:* ej mottagen premie (`pending`/`invoiced`) – kredit eller tillägg på fordran; mottagen premie där rättad premie är minst det mottagna – tilläggspremie som ny fordran (kapital och garanti först när den tas emot, PR-ITP1-018). Omräkning med premiemånadens IBB (PR-ITP1-032) och trappan (PR-ITP1-001). Upprepade rättelser bygger på varandra; samma rättelse två gånger avvisas (differens noll).
- *Blockeras:* minskning av redan mottagen premie – återtag kräver spårad kapitalandel och historisk garantidel (PR-ITP1-019 p.3, PR-ITP1-020) som modellen saknar, så ingen andel av dagens kapital gissas; flera premierader samma månad (fördelning, PR-ITP1-015); andra radtyper än `premium`; makulerade rader; rader utan beräkningsunderlag eller som inte går att räkna fram igen; IBB som avviker från radens underlag; månad med justeringar utan länk; avliden försäkrad (PR-ITP1-010); rättad lön som inte stämmer med registrerat löneunderlag för månaden.
- `HUMAN_ONLY`: negativa rättighetsändringar och återkrav avgörs av människa (PR-ITP1-031).

**`terminate_policy` – uppskjuten.** Varken slutavräkning efter sista månadsrätten (PR-ITP1-027) eller dödsfallsavräkning (PR-ITP1-010) kan genomföras korrekt: båda kräver uttagsdelar, månadsanspråk, betalningsskuld och kapitaljournal. Ett avslut genom en lägesändring skulle kunna dölja kapital och anspråk, så det finns ingen operation och ingen registerrad.

### 9.2 Anslutning, stamdata och arbetsgivare (Fas 4, S5) – vad som stöds och vad som blockeras

Modellval och avgränsning stämdes av med operatören 2026-10-12 (**B-032**, underlag i `projekt/01_ärendehantering/OPERATIONER_BESLUTSFORSLAG.md`). Ingen schemaändring.

**`enroll_insured_person`** (PR-ITP1-012/013) skapar i en transaktion:

- den försäkrade (status `active`),
- en försäkring (nästa `AL-NNNNNN`),
- förmånen `retirement_dc`,
- läget `premium_paying` från den dokumenterade ITP1-tillhörigheten.

`signed_date` = `start_date` = tillhörighetsdagen. Databasen kräver start ≥ tecknad, så registreringsdagen och anmälans referens står i stället i händelseloggen och i lägets `note`. Anslutningen skapar ingen premie och skickar inget försäkringsbesked (villkor §14), och resultatet anger att beskedet inte är skickat.

- *Stöds:*
  - ny person hos en aktiv ITP-arbetsgivare;
  - tillhörighet senast i dag, inte före anställningen och inte före arbetsgivarens ITP-anslutning;
  - retroaktiv anslutning;
  - person under 25 år, med `premium_paying` och ordinarie premie från 25-årsmånaden (PR-ITP1-013). Premiemotorns åldersfönster ger ingen premie före dess.
- *Blockeras:*
  - VD, ägare, utlandsanställd eller avstående, som kräver uttryckligt beslut (PR-ITP1-012);
  - tillhörighet i framtiden;
  - 66 år eller äldre vid start (frivillig premie 66–67, PR-ITP1-016);
  - arbetsgivare som inte är aktiv eller har annat avtal än ITP (B-002);
  - befintligt personnummer med avslutad anställning. Återanställning och arbetsgivarbyte kräver anställningshistorik som modellen saknar.
- *Konflikt:* personen finns redan som aktiv. Två samtidiga anslutningar som räknar fram samma försäkringsnummer stoppas av unikhetsregeln (verifierat mot Postgres).

**`update_current_salary`** ändrar aktuell månadslön och tjänstgöringsgrad på personen. Det är stamdata, inte pensionsmedförande lön: PR-ITP1-014 tillåter inte avtalad lön som underlag. Ändringen skapar därför varken löneunderlag eller premie. Tidigare och nytt värde står i händelseloggen.

- *Blockeras:* anställningen har upphört, eller personen är pensionerad eller avliden.
- *Konflikt:* oförändrat värde.
- Operationen har ingen produktregel, så golvet (*write utan regel*) håller den `HUMAN_ONLY` för agenter.

**`update_contact_details`** ändrar e-post och telefon. Båda anges som de ska vara efter ändringen, och ett tomt fält tar bort uppgiften. Motiveringen anger hur rätt person verifierades (PR-ITP1-031). Namn och personnummer ändras inte.

- *Blockeras:* avliden försäkrad.
- *Konflikt:* oförändrade uppgifter.
- Operationen är `HUMAN_ONLY`, eftersom ett byte av e-post är en väg till kontokapning.

**`register_employer`** registrerar en ny försäkringstagare med ITP som kollektivavtal och organisationsnummer med kontrollsiffra.

- *Blockeras:* anslutningsdag i framtiden.
- *Konflikt:* organisationsnumret finns redan.
- Status, organisationsnummer och anslutningsdag ändras inte här, eftersom en arbetsgivares avslut berör alla dess försäkrade.

**`list_employers`** visar organisationsnummer, namn, status, anslutningsdag och antal aktiva försäkrade, utan kontaktpersoner. Listan läser inga personuppgifter och loggas inte.

**Regelversioner i de byggda fallen.** Beräkningar använder periodens parametrar: premiemånadens IBB ur `base_amounts`, och en rättelse stoppas om radens sparade IBB avviker. Regelstatus och filversion vid verkställigheten skrivs i händelseloggen (§4). Före giltighetsdagen för PR-ITP1 v1.0 (2026-11-01, B-031) är operationerna handläggarstöd enligt kommande regler. Begränsning: det finns ännu ingen låst regelversion per händelse eller beräkning (t.ex. `PR-ITP1-001 v1.0` i `calculation_basis`) och ingen markering av teknisk driftsättning. Det behövs för flaggskeppsflödet regel → produktion och bör stämmas av med delprojekt 4.

---

### 9.3 Ärenden (Fas 5, F5-2) – vad som stöds och vad som blockeras

Beslutat av operatören 2026-10-24 (**B-033**, underlag i `projekt/01_ärendehantering/ARENDEN_BESLUTSFORSLAG.md`). Tabellen `cases` (`databasschema.md` §9g). Kod: `src/services/operations/cases.py`.

| Operation | Typ | PII | Register | Vad den gör |
|---|---|---|---|---|
| `create_case` | `write` | Ja | `HUMAN_ONLY` | Registrerar ett ärende med nästa `CASE-NNNNNN` och status `open` |
| `get_case` | `read` | Ja | `AGENT` | Ärendet med försäkrad, arbetsgivare, månad, mottagning, status och inrapporterade uppgifter |
| `list_cases` | `read` | Ja | `HUMAN_ONLY` | Handläggarens lista: aktiva (standard), en status, stängda eller alla; urval på typ, handläggare och försäkrad |
| `update_case_status` | `write` | Nej | `HUMAN_ONLY` | Byter status bland de öppna och vid behov handläggare och senaste agentkörning |
| `close_case` | `write` | Nej | `HUMAN_ONLY` | Stänger med utfall och anteckning |

Skrivningarna saknar produktregel och är därmed `HUMAN_ONLY` för agenter även genom golvet. Harness skriver status efter en agentkörning som systemaktör (F5-3). Agenten kan bara läsa ärenden; harness begränsar `get_case` till körningens ärende.

**Ärendet i händelseloggen.** Tjänstelagret sätter `case_id` för varje anrop som gäller ett ärende: kontextens `case_id`, annars indatans `case_number`, och för `create_case` resultatets nummer. Anger både kontext och indata ett ärende måste de vara samma, annars stoppas anropet. Ärendets historik är därmed händelserna med dess `case_id` (B-033 val A), och ett agentförslag i ärendet får `case_id` i godkännandekön.

**`create_case`** – ärendetyp `salary_report`, kanal `manual` (v1). Uppgifterna (`details`) valideras som löneunderlag: lön ≥ 0, `new` eller `correction` (med `corrects_version` vid rättelse och bara då) och källa. Periodmånaden rundas till månadsförsta.

- *Stöds:* befintlig försäkrad och arbetsgivare; valfri försäkring som hör till personen; mottagningsdag senast i dag; valfri tidsfrist och handläggare.
- *Saknas:* personen, arbetsgivaren eller försäkringen (eller försäkringen hör till någon annan).
- *Blockeras:* mottagningsdag i framtiden.
- *Konflikt:* samma typ, arbetsgivare och avsändarreferens är redan ett ärende. Två samtidiga registreringar som räknar fram samma nummer stoppas av unikhetsregeln.

**`update_case_status`** byter mellan `open`, `in_progress`, `waiting_approval` och `waiting_info`. Ett stängt ärende ändras inte (konflikt). Stängning görs bara med `close_case`.

**`close_case`** – utfall `approved`, `rejected`, `supplement_requested`, `manual_review` eller `no_action`.

- *Kräver motivering:* `rejected` och `manual_review` (PR-ITP1-031).
- *Blockeras:* förslag i ärendet väntar i godkännandekön – de avgörs först; `approved` utan genomförd ändring i ärendet, alltså varken ett godkänt agentförslag eller en utförd skrivning med ärendets `case_id`.
- *Konflikt:* ärendet är redan stängt.

### 9.4 Produktparametrar (Fas 3c, 3c-P1) – vad som stöds och vad som blockeras

Beslutat av operatören 2026-10-25 (**B-035**, underlag i `02_system/flaggskeppsflöde.md`). Tabellen `product_parameters` (`databasschema.md` §9h). Kod: `src/services/parameters.py` (uppslag) och `src/services/operations/product_parameters.py`.

| Operation | Typ | PII | Register | Vad den gör |
|---|---|---|---|---|
| `get_product_parameters` | `read` | Nej | `AGENT` | Värdena som gäller en dag (standard i dag) och alla versioner med giltighet, tillstånd (gällande, kommande, upphörd, återkallad), produktregel, källa och beslut |
| `schedule_product_parameter_change` | `write` | Nej | `APPROVAL` | Ny version från en framtida månadsförsta; den föregående avslutas dagen före (3c-P2) |
| `withdraw_product_parameter_change` | `write` | Nej | `HUMAN_ONLY` | Drar tillbaka en version som inte börjat gälla; den föregående gäller igen tills vidare (3c-P2) |

**Premieberäkningen följer parametrarna för premiemånaden.** `calculate_premium_preview` och `correct_premium_transaction` slår upp premieålder, satser och brytpunkter i `product_parameters` och skickar dem till premiemotorn. Versionerna står i `calculation_basis` (`parameters`, `age_window`).

- *Stoppas:* en parameter saknas för månaden (`NotFoundError`), två giltiga versioner av samma parameter samma månad, eller en premieålder som inte är hela år (`BlockedError`). Ingen tyst reserv.
- *Undantag:* finns tabellen inte (Lakebase före migrationen) används paketets värden PR-ITP1 v1.0 i koden, märkt i `calculation_basis`.

Skrivoperationerna bär produktreglerna PR-ITP1-001, -013 och -032 (respektive -032) och är därför `HUMAN_ONLY` för agenter till 2026-11-01. Därefter får en agent föreslå en ny version, men aldrig dra tillbaka en.

**`schedule_product_parameter_change`** – parameter, nytt värde, giltighetsdag (månadsförsta), regelns nya version, källa och beslut. Regeln följer parametern (åldrar PR-ITP1-013, satser och brytpunkter PR-ITP1-001). Versionen sparas med aktören som verkställde den; vid ett godkänt agentförslag står förslagsställaren i kön och händelseloggen.

- *Stöds:* en ny version från tidigast nästa månad; den gällande versionen avslutas dagen före.
- *Blockeras:* giltighet i innevarande eller passerad månad (ingen retroaktivitet, PR-ITP1-032); premieålder som inte är hela år mellan 16 och 80; premiesats utanför 0–1 (andel); brytpunkt som inte är positiv; parametrar som inte hänger ihop dagen ändringen börjar gälla (premieåldern från ska vara lägre än till, brytpunkten lägre än lönetaket).
- *Konflikt:* det finns redan en senare version (dra tillbaka den först – en kommande version per parameter i taget); en version, även återkallad, finns redan från samma dag; värdet är detsamma som det gällande.

**`withdraw_product_parameter_change`** – parameter och giltighetsdag.

- *Stöds:* en version som inte börjat gälla; den föregående får tillbaka `valid_to = NULL`.
- *Blockeras:* versionen har redan börjat gälla – då ändras värdet bara med en ny version.
- *Konflikt:* en senare version finns. *Saknas:* ingen giltig version från dagen.

En återkallad version ligger kvar som historik. Samma giltighetsdag kan inte återanvändas för parametern (unik nyckel och dag); välj en annan månad.

### 9.5 Beståndsinsikt för en parameterändring (Fas 3c, 3c-B) – vad som stöds och vad som spärras

Beslutat i **B-035** (`02_system/flaggskeppsflöde.md` §5 *bestand*, val I och K). Kod: `src/services/operations/portfolio_impact.py` (operationen) och `src/analytics/parameter_impact.py` (den rena beräkningen och undertryckningen). Ingen schemaändring.

| Operation | Typ | PII | Register | Vad den gör |
|---|---|---|---|---|
| `estimate_parameter_change_impact` | `read` | Nej | `AGENT` | Baslinje mot scenario för de aktiva försäkrade år för år: berörda, extra premiemånader och extra premievolym, första berörda år, antaganden och dolda celler. Ändrar ingenting |

**Indata:** parameter (`key`, samma sex som i §9.4), nytt värde, giltighetsdag (månadsförsta) och `horizon_years` (1–45 år, standard 10).

**Beräkningen sker i betrodd kod.** Operationen läser de aktiva försäkrade (status `active` med en öppen försäkring i läget `premium_paying`) internt: födelsedatum ur personnumret, aktuell månadslön och ett känt slutdatum för anställningen. Identiteten lämnar aldrig operationen. För varje person och månad räknar premiemotorn premien två gånger:

- *Baslinjen* är de parametrar som gäller månaden enligt `product_parameters`, med samma uppslag som premieberäkningen (`services/parameters.py`, en fråga för hela perioden). Schemalagda versioner ingår.
- *Scenariot* är samma parametrar med det nya värdet från giltighetsdagen.

En person är berörd ett år om premien skiljer sig någon månad det året. Extra premiemånader är månaderna i premieåldern i scenariot minus i baslinjen, och kan bli negativa (lägre premieålder). Extra premievolym är scenario minus baslinje.

**Antagandena står i svaret:** dagens aktiva, inga nyanställda, inga avgångar och ingen dödlighet; dagens lön utan lönetillväxt; inkomstbasbeloppet för året och för år utan fastställt belopp det senast fastställda, utan uppräkning; ingen avkastning, ränta eller avgift. Volymen är summan av premier, inte kapital eller pension.

**Skydd mot röjande (`harness.md` §5.1):**

- *Inga individuppgifter i utdata:* inga personnummer, namn, födelsedatum, löner eller försäkringsnummer. Utdatamodellen har bara aggregat.
- *Små celler döljs:* ett år med 1–9 berörda visas som `dold`, och berörda, extra premiemånader, extra volym och scenariovolym blir `None`. Baslinjens volym döljs om 1–9 betalar premie det året. Samma gäller totalen, antalet aktiva och antalet som inte gick att beräkna. Noll visas som noll.
- *Kompletterande döljning:* de dolda åren ska tillsammans omfatta minst 10 berörda. Annars döljs också det minsta synliga året med berörda, så att en dold cell inte kan räknas fram som totalen minus de synliga.
- *Avrundning:* belopp i hela tusental kronor, grövre än en enskild månadspremie.
- *Ej beräknat är aldrig noll:* en månad utan parametrar (saknad version, två giltiga versioner eller parametrar som inte hänger ihop med det nya värdet) gör året `ej beräknad` med skälet. Totalen blir då också ej beräknad.

**Spärras:**

- *Blockeras:* giltighetsdag i innevarande eller passerad månad (tidigast nästa månad, som för schemaläggningen); värde utanför parameterns gränser eller som inte hänger ihop med övriga parametrar (samma kontroll som `schedule_product_parameter_change`, §9.4); tabellen `product_parameters` saknas.
- *Konflikt:* en senare schemalagd version av samma parameter finns efter giltighetsdagen. Då blir scenariot tvetydigt.
- *Ogiltig indata:* giltighetsdag som inte är en månadsförsta, okänd parameter, horisont utanför 1–45 år.

**Gränser kvar till senare steg.** Operationen skyddar varje enskilt svar, men inte mot differenser mellan upprepade anrop med olika horisont, giltighetsdag eller värde. Därför binder resurskontrollen i 3c-T aktuarieagentens anrop till den parameterändring som grind 1 godkänt (`key`, `value`, `valid_from`) och bör binda även `horizon_years`. Operationen monteras i podden `bestand` först i 3c-T och är omappad till dess. Före skarp demo i Lakebase behövs databasrollen `agent_aktuarie` med `SELECT` på `insured_persons`, `policies`, `policy_states`, `base_amounts` och `product_parameters`, och rätt att skriva loggrader (val I, 3c-V).

## 10. Öppna frågor

- **Fyraögonprincip** (två olika människor) är inte möjlig med en operatör – framtida option per operation.
- **Hur mycket indata som loggas** för PII-operationer – fullt, maskerat eller som referens.

---

## 11. Hänvisningar

- **B-017** – människa som fullständig operatör (samma operationer och samma spår för människor och agenter)
- **B-020** – handläggar-UI före kundportal, backend för två klienter
- **B-022** – försäkringsmodellen (försäkring → förmåner → lägen, premier per förmån)
- **B-026** – agentekosystem (harness, skill-poddar, sidoeffektsklasser)
- **B-028** – byggordning och tjänstelager
- `01_domän/produktregler/`, `02_system/agentekosystem.md`, `02_system/databasschema.md`
