# Tjänstelagret

> **Status:** 🟡 Beslutat (**B-028**), byggs i Fas 1f – **T1 och T2 klara** (grunden + läsoperationerna). Kod: `src/services/`, register: `src/services/access_register.yaml`.
> **Bygger på:** B-017 (människa som fullständig operatör), B-020 (backend för två klienter), B-022 (försäkringsmodellen), B-026 (agentekosystem)
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
| `name` | Engelska `snake_case`, t.ex. `register_salary_change`. Blir verktygsnamnet för agenter |
| `description` | Vad operationen gör och när den används (svenska) |
| `input` / `output` | Pydantic-modeller – indatamodellen blir direkt verktygsdefinitionen för agenter (`ToolSpec.from_model`) |
| `kind` | `read` / `compute` / `write` / `external` – samma klasser som sidoeffektsklasserna i B-026 |
| `rules` | Produktregler som operationen implementerar, t.ex. `["PR-ITP1-001"]` – spårbarhet regel → kod |
| `pii` | Om operationen läser eller exponerar personuppgifter |

Vad agenter får göra med operationen står **inte** i operationen utan i registret (§4) – så att gränserna kan ändras på ett ställe.

Skiss:

```python
@operation(
    name="register_salary_change",
    description="Registrerar ny pensionsmedförande månadslön från ett visst datum.",
    kind="write",
    rules=["PR-ITP1-001"],
    pii=True,
)
def register_salary_change(ctx: OperationContext, data: SalaryChange) -> SalaryChangeResult:
    ...
```

---

## 4. Agentåtkomst – registret och flaggan *endast handläggare*

Vad agenter får göra bestäms i **registret** `src/services/access_register.yaml` – en fil med en rad per operation. Vill du ändra vad agenter får göra ändrar du nivån på raden; ändringen går via commit och merge som allt annat. Handläggare får utföra alla operationer (B-017); registret kan senare utökas med handläggarroller om bolaget får fler personer.

```yaml
operations:
  get_insured_overview: AGENT
  register_salary_change: APPROVAL
  terminate_policy: HUMAN_ONLY
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

Registret kan alltså öppna för agenter, men aldrig förbi ett golv. Statusen läses ur produktregelns rubrik i `01_domän/produktregler/` (`**Granskningsstatus:** utkast/godkänd/ersatt`); allt annat än `godkänd` räknas som ej godkänt. En registerrad för en operation som inte finns ger fel vid start, så att stavfel inte tyst lämnar en operation stängd.

**Regler:**

1. **Strängast som standard.** Saknas operationen i registret blir den `HUMAN_ONLY`.
2. **Kan bara skärpas förbi golven.** Team och poddar kan neka ytterligare operationer men aldrig öppna en `HUMAN_ONLY`.
3. **Verkställs i två lager:**
   - **Tjänstelagret** kontrollerar aktören vid varje anrop. En agent som anropar en `HUMAN_ONLY`-operation får ett fel – oavsett hur anropet kom dit. Det här är det egentliga skyddet.
   - **Harness** visar aldrig `HUMAN_ONLY`-operationer som verktyg, så agenten försöker inte ens.
4. **Bara en människa kan godkänna** ett agentförslag, och godkännandet loggas med både förslagsställare och godkännare.
5. **Registret är versionerat.** Varje ändring syns i en diff och godkänns vid merge. En genererad förteckning (§9, T4) visar för varje operation registrets nivå, effektiv nivå och varför – t.ex. *APPROVAL i registret men HUMAN_ONLY eftersom PR-ITP1-002 är utkast*.

---

## 5. Aktörer och kontext

Varje anrop bär ett `OperationContext`:

| Fält | Innehåll |
|------|----------|
| `actor` | Vem som anropar: `human` (handläggare, t.ex. operatören), `agent` (agent-id + team) eller `system` (skript/batch som operatören startar) |
| `reason` | Motivering – obligatorisk för `write` och `external` |
| `run_id` | Agentkörningen (för agenter) – kopplar till körjournal och AI-lagrets anropslogg |
| `case_id` | Ärendet operationen hör till, när ärenden finns (delprojekt 1) |

`system` behandlas som handläggare i åtkomstkontrollen – i v1 är det alltid operatören som startar skripten – men loggas separat.

---

## 6. Godkännande

1. En agent anropar en `APPROVAL`-operation.
2. Tjänstelagret validerar indata och regler – förslaget ska vara giltigt redan när det läggs.
3. Ett **godkännandeärende** sparas (operation, indata, motivering, föreslagen av, `run_id`) med status `pending`, och agenten får svaret *väntar på godkännande* med ärende-id.
4. Handläggaren ser kön (CLI i v1, handläggar-UI:t från Fas 4), granskar och godkänner eller avslår.
5. Vid godkännande körs operationen **på nytt mot aktuellt läge** (data kan ha ändrats), utförd av handläggaren, med agenten angiven som förslagsställare.

Kön ligger i tjänstelagret – inte i harness – så att människor ser alla förslag på ett ställe oavsett vilken agent eller vilket flöde som lade dem. Det justerar B-026, där harness skapade godkännandeärenden; harness tar nu bara emot svaret *väntar på godkännande*.

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
| **T3** | Första skrivoperationerna – en per nivå: `register_salary_change` (`APPROVAL`), `set_policy_paid_up` (`APPROVAL`), `terminate_policy` (`HUMAN_ONLY`), `correct_premium_transaction` (`HUMAN_ONLY`) – samt godkännandekön |
| **T4** | Genererad förteckning över alla operationer med registrets nivå, effektiv nivå och skäl, typ, regler och PII |

Regelspecifika operationer (uttag, paus, återupptagande, garanti, pensionsbelopp) byggs när motsvarande produktregler i delprojekt 4 är antagna. Därefter byggs handläggar-UI:t (Fas 4) ovanpå tjänstelagret, och sist agentlagret (harness, Fas 3b, och handläggaragenten, Fas 5).

**Nya tabeller** (`operation_events`, `approval_requests`) dokumenteras i `databasschema.md` innan de skapas, och körningen mot Lakebase koordineras enligt AGENTS.md §4.5.

**Tester:** tjänstelagret testas mot en SQLite-databas i minnet med samma modeller som Lakebase (`tests/conftest.py`, fixturen `insurance_db`). Modellerna är portabla utan att Postgres-DDL:en ändrats (`databasschema.md` §12). I produktion används `services.db.database_session_factory()` mot Lakebase via `DATABASE_URL`.

**Byggda operationer:**

| Operation | Typ | Produktregler | PII | Register |
|-----------|-----|---------------|-----|----------|
| `get_insured_overview` | `read` | – | Ja | `AGENT` |
| `get_premium_history` | `read` | – | Ja | `AGENT` |
| `calculate_premium_preview` | `compute` | PR-ITP1-001 | Nej | `AGENT` |

---

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
