# Tjänstelagret

> **Status:** 🟡 Designförslag (förslag **B-028**). Kod: `src/services/` (kommer, Fas 1f).
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
| `agent_access` | `AGENT` / `APPROVAL` / `HUMAN_ONLY` – se §4 |
| `pii` | Om operationen läser eller exponerar personuppgifter |

Skiss:

```python
@operation(
    name="register_salary_change",
    description="Registrerar ny pensionsmedförande månadslön från ett visst datum.",
    kind="write",
    rules=["PR-ITP1-001"],
    agent_access=AgentAccess.APPROVAL,
    pii=True,
)
def register_salary_change(ctx: OperationContext, data: SalaryChange) -> SalaryChangeResult:
    ...
```

---

## 4. Agentåtkomst – flaggan för *endast handläggare*

Varje operation har en av tre nivåer:

| Nivå | Kod | Vad en agent kan göra | Exempel |
|------|-----|------------------------|---------|
| **Agent** | `AGENT` | Utföra direkt – om operationen ingår i agentens skill-poddar | Läsa försäkringsöversikt, förhandsberäkna premie |
| **Agent med godkännande** | `APPROVAL` | Förbereda. Operationen utförs först när en handläggare har godkänt (§6) | Registrera lönändring, sätta försäkring i fribrev |
| **Endast handläggare** | `HUMAN_ONLY` | Ingenting. Operationen syns inte som verktyg; agenten kan bara lämna över ärendet till en handläggare | Avsluta försäkring, rätta historiska premietransaktioner, ändra identitetsuppgifter |

**Regler:**

1. **Strängast som standard.** En operation som inte anger nivå blir `HUMAN_ONLY`. Agentåtkomst måste öppnas uttryckligen.
2. **Kan bara skärpas, aldrig lättas.** En `external`-operation (påverkar omvärlden, §3.5) kräver minst `APPROVAL` – registret vägrar starta annars. Team och poddar kan neka ytterligare operationer men aldrig öppna en `HUMAN_ONLY`.
3. **Verkställs i två lager:**
   - **Tjänstelagret** kontrollerar aktören vid varje anrop. En agent som anropar en `HUMAN_ONLY`-operation får ett fel – oavsett hur anropet kom dit. Det här är det egentliga skyddet.
   - **Harness** visar aldrig `HUMAN_ONLY`-operationer som verktyg, så agenten försöker inte ens.
4. **Bara en människa kan godkänna** ett agentförslag, och godkännandet loggas med både förslagsställare och godkännare.
5. **Flaggan står i koden vid operationen.** Den är versionerad, syns i varje diff och täcks av tester. En genererad förteckning över alla operationer och deras nivåer (§9, T4) gör det enkelt att granska helheten. Att ändra en nivå är en kodändring som du godkänner vid merge.

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
| **T1** | Operationskontrakt, register, aktörer, åtkomstkontroll (§4–5) och händelselogg – med tester som visar att en agent inte kan utföra `HUMAN_ONLY` |
| **T2** | Första läsoperationerna: försäkringsöversikt per försäkrad, premiehistorik, förhandsberäkning av premie (premiemotorn, PR-ITP1-001) |
| **T3** | Första skrivoperationerna – en per nivå: `register_salary_change` (`APPROVAL`), `set_policy_paid_up` (`APPROVAL`), `terminate_policy` (`HUMAN_ONLY`), `correct_premium_transaction` (`HUMAN_ONLY`) – samt godkännandekön |
| **T4** | Genererad förteckning över alla operationer med nivå, typ, regler och PII |

Regelspecifika operationer (uttag, paus, återupptagande, garanti, pensionsbelopp) byggs när motsvarande produktregler i delprojekt 4 är antagna. Därefter byggs handläggar-UI:t (Fas 4) ovanpå tjänstelagret, och sist agentlagret (harness, Fas 3b, och handläggaragenten, Fas 5).

**Nya tabeller** (`operation_events`, `approval_requests`) dokumenteras i `databasschema.md` innan de skapas, och körningen mot Lakebase koordineras enligt AGENTS.md §4.5.

---

## 10. Öppna frågor

- **Testdatabas:** modellerna använder JSONB (Postgres). Testas tjänstelagret mot en lokal Postgres, en separat Lakebase-gren eller ett minnesbaserat repositorium? Avgörs i T1.
- **Operationer utan antagen produktregel:** ska skrivoperationer som saknar antagen regel automatiskt vara `HUMAN_ONLY` tills regeln antas? Det kopplar flaggan direkt till regelarbetet i delprojekt 4.
- **Fyraögonprincip** (två olika människor) är inte möjlig med en operatör – framtida option per operation.
- **Hur mycket indata som loggas** för PII-operationer – fullt, maskerat eller som referens.

---

## 11. Hänvisningar

- **B-017** – människa som fullständig operatör (samma operationer och samma spår för människor och agenter)
- **B-020** – handläggar-UI före kundportal, backend för två klienter
- **B-022** – försäkringsmodellen (försäkring → förmåner → lägen, premier per förmån)
- **B-026** – agentekosystem (harness, skill-poddar, sidoeffektsklasser)
- **B-028** *(förslag)* – byggordning och tjänstelager
- `01_domän/produktregler/`, `02_system/agentekosystem.md`, `02_system/databasschema.md`
