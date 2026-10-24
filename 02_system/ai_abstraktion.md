# AI-abstraktionslagret

> **Status:** 🟢 Specificerat och implementerat i `src/ai/` (Fas 3). Valet av lösning är beslutat i **B-025**.
> **Beslut:** B-009 (modellagnostisk arkitektur), B-025 (egen tunn wrapper)
> **Relaterat:** `02_system/agentekosystem.md` (hur team, agenter och skill-poddar använder lagret), MASTER_CONTEXT §3.1
> **Senast verifierat mot leverantörernas dokumentation:** 2026-10-11

---

## 1. Syfte

Lagret är den **enda** vägen från bolagets kod till en AI-modell. Agent- och skillkod beskriver *vad* den vill – meddelanden, verktyg, önskat svarsformat och vilken modellroll som behövs. Lagret avgör *hur*: vilken leverantör och modell, hur anropet översätts till leverantörens API, vilken API-nyckel som används och hur anropet loggas.

Därmed kan modell eller leverantör bytas genom konfiguration utan att någon agent- eller skillkod ändras (B-009).

---

## 2. Krav

| ID | Krav | Källa |
|----|------|-------|
| K1 | Inga leverantörs-SDK:er i agent- eller skillkod – bara `src/ai/providers/` importerar `anthropic`/`openai` | §3.1, B-009 |
| K2 | Byte av modell eller leverantör via konfiguration (fil eller miljövariabel), utan kodändring | §3.1 |
| K3 | API-nycklar via miljövariabler; separata nycklar per team möjliga, med gemensam nyckel som reserv | §3.1, uppdrag Fas 3 |
| K4 | Leverantörsspecifika finesser (verktygsformat, strukturerade svar, prompt caching, resonemangsnivå) kapslas in | §3.1 |
| K5 | Verktygsanrop (function calling) i flera varv – skills exponeras som verktyg för agenter | B-007, B-008 |
| K6 | Strukturerade svar som valideras mot en Pydantic-modell | Lärdom agent-factory |
| K7 | Spårbarhet: varje anrop loggas med körning, team, agent, modell, tokens och kostnad | B-016, §3.5 |
| K8 | Dataminimering: promptinnehåll loggas inte som standard | B-006 |
| K9 | Testbart utan nätverk – agent- och flödestester ska kunna köras mot en fejkleverantör | — |
| K10 | Robust felhantering: omförsök bara där det hjälper, reservmodell vid driftstörning hos en leverantör | — |
| K11 | Litet beroendeavtryck – lagret hanterar API-nycklar och ska bara bero på få, välunderhållna paket | Supply chain-risk, se §3 |
| K12 | Kostnadsinsyn per team och agent | B-024 (team) |

---

## 3. Utvärdering av alternativ

### 3.1 Alternativen

**LiteLLM** (Python-SDK, valfritt med egen proxyserver)
Enhetligt anropsformat (OpenAI:s Chat Completions-format) mot 100+ leverantörer, inbyggda pristabeller, router med reservmodeller. Proxyservern erbjuder virtuella nycklar och budgetar per team.
- **För:** störst leverantörsbredd; färdig kostnadsberäkning; proxyläget löser team-nycklar centralt.
- **Emot:**
  - **Supply chain-incident:** den 24 mars 2026 publicerades två komprometterade versioner (1.82.7 och 1.82.8) på PyPI med kod som stal SSH-nycklar, molnnycklar och andra hemligheter vid varje Python-start. Paketen låg ute i cirka 40 minuter innan PyPI satte dem i karantän. Ett abstraktionslager som per definition hanterar våra API-nycklar är exakt den plats där den risken väger tyngst.
  - Stort beroendeträd och hög releasetakt med återkommande regressioner.
  - Minsta gemensamma nämnare: Anthropic-specifika funktioner (prompt caching, adaptivt tänkande, server-side fallbacks) nås via leverantörsspecifika extraparametrar – det läcker tillbaka in i anropande kod, i strid med K4.
  - Vi skulle ändå behöva ett eget lager ovanpå (roller, team-kontext, spårbarhet, godkännande) – LiteLLM blir då bara en intern detalj.
  - Proxyläget kräver en egen tjänst (server + databas) – överdimensionerat för ett enpersonsbolag i sandlåda.

**OpenRouter** (hostad proxy med OpenAI-kompatibelt API)
En nyckel, hundratals modeller, automatisk leverantörsreserv, möjlighet att bara routa till leverantörer utan datalagring.
- **För:** minst egen kod; enkel modellbredd för experiment.
- **Emot:**
  - En **tredje part i dataflödet** – alla promptar (även simulerade personuppgifter) passerar ytterligare ett biträde. Ett riktigt tjänstepensionsbolag skulle behöva biträdesavtal och tredjepartsbedömning (GDPR, DORA); simuleringen ska spegla det (B-003, B-006).
  - Avgift: 5,5 % på köpta krediter, alternativt BYOK (egna leverantörsnycklar) som är avgiftsfritt upp till en månatlig volym.
  - OpenAI-kompatibelt format ger varierande trohet för Anthropic-specifika funktioner.
  - Ytterligare en tillgänglighetsberoende länk och extra latens.
  - Ersätter de direkta OpenAI-/Anthropic-nycklarna med en OpenRouter-nyckel – team-nycklar per leverantör (K3) blir då OpenRouters begrepp i stället för leverantörernas egna workspaces/projekt.

**Egen tunn wrapper** (vidareutveckling av agent-factorys `LLMRouter`)
Egna kanoniska typer och en adapter per leverantör ovanpå de officiella SDK:erna (`anthropic`, `openai`).
- **För:** full kontroll över gränssnittet; varje leverantörs bästa funktioner används nativt (Anthropics strukturerade svar och prompt caching, OpenAIs Responses API med strikta scheman); bara officiella SDK:er + `pydantic` + `pyyaml` som beroenden; enkelt att testa med fejkleverantör; bygger på beprövad kod från agent-factory.
- **Emot:** vi underhåller adaptrarna när leverantörernas API:er ändras (begränsat – två adaptrar, och SDK:erna absorberar transportförändringar); färre leverantörer direkt ur lådan (en OpenAI-kompatibel adapter öppnar för OpenRouter, Mistral, lokala modeller m.fl. när det behövs).

### 3.2 Jämförelse mot kraven

| Krav | LiteLLM | OpenRouter | Egen wrapper |
|------|---------|------------|--------------|
| K1–K2 Byte via konfiguration | ✅ | ✅ | ✅ |
| K3 Team-nycklar per leverantör | 🟡 via proxyserver | 🟡 OpenRouters egna nycklar | ✅ namnkonvention + leverantörernas workspaces/projekt |
| K4 Leverantörsfinesser inkapslade | 🟡 extraparametrar läcker | 🟡 varierande trohet | ✅ nativt per adapter |
| K5 Verktygsanrop flera varv | ✅ | ✅ | ✅ |
| K6 Strukturerade svar | ✅ | 🟡 modellberoende | ✅ |
| K7 Spårbarhet med team/agent | 🟡 eget lager behövs ändå | 🟡 eget lager behövs ändå | ✅ |
| K8 Dataminimering | ✅ | ❌ extra tredje part | ✅ |
| K9 Testbart utan nätverk | 🟡 mock av LiteLLM | 🟡 mock av HTTP | ✅ inbyggd fejkleverantör |
| K10 Omförsök + reservmodell | ✅ | ✅ | ✅ |
| K11 Litet beroendeavtryck | ❌ stort träd, incident 2026 | ✅ (HTTP) men tredje part | ✅ |
| K12 Kostnad per team/agent | ✅ med proxy | 🟡 | ✅ |

### 3.3 Rekommendation och beslut (B-025)

**Egen tunn wrapper ovanpå de officiella SDK:erna**, med Anthropic (Messages API) och OpenAI (Responses API) som första adaptrar.

Motivering i korthet: lagret blir litet (ca 1 000 rader inklusive typer, konfiguration och loggning), helt under projektets kontroll, och de enda beroenden som hanterar nycklarna är leverantörernas egna SDK:er. LiteLLMs bredd behövs inte för två leverantörer, och OpenRouter tillför en tredje part i dataflödet som ett riktigt bolag skulle behöva motivera.

**När beslutet bör omprövas:** om fler än 3–4 leverantörer behövs löpande, eller om många människor/system ska dela nycklar centralt. Då kan LiteLLM eller OpenRouter läggas till som **en ny adapter bakom samma gränssnitt** – ingen agentkod påverkas.

---

## 4. Arkitektur

```
 agent- och skillkod, flöden, scripts
        │   from ai import get_client, Message, ToolSpec ...
        ▼
 ┌──────────────────────────────────────────────────────────────┐
 │ src/ai/client.py  AIClient: complete / ask / ask_structured   │
 │                   / bind(team=…, agent=…, run_id=…)           │
 │   ├─ config.py      roller → modeller, priser, förmågor       │
 │   ├─ keys.py        nyckelval per leverantör och team         │
 │   ├─ schema.py      Pydantic → strikt JSON Schema             │
 │   └─ tracing.py     anropslogg (JSONL)                        │
 └──────────────────────────────┬───────────────────────────────┘
                                │ ProviderRequest / ProviderResult
 ┌──────────────────────────────▼───────────────────────────────┐
 │ src/ai/providers/   (Provider-protokoll)                      │
 │   ├─ anthropic_provider.py → anthropic SDK (Messages API)     │
 │   ├─ openai_provider.py    → openai SDK (Responses API)       │
 │   └─ fake.py               → skriptade svar för tester        │
 └──────────────────────────────────────────────────────────────┘
```

| Modul | Ansvar |
|-------|--------|
| `ai/__init__.py` | Publikt API – det enda anropande kod importerar från |
| `ai/types.py` | Kanoniska typer: `Message`, `ToolSpec`, `ToolCall`, `ToolResult`, `ModelResponse`, `Usage`, `CallContext` |
| `ai/errors.py` | Leverantörsoberoende felhierarki |
| `ai/config.py` + `ai/ai_config.yaml` | Leverantörer, modeller (pris + förmågor), roller, loggning |
| `ai/keys.py` | Namnkonventionen för nycklar och team-nycklar |
| `ai/schema.py` | Gör Pydantic-scheman strikta (krävs av båda leverantörerna). Värdegränser som Anthropics strikta läge avvisar (`minimum`, `maxLength` m.fl.) flyttas till fältets beskrivning; anroparen validerar mot Pydantic-modellen |
| `ai/tracing.py` | Anropsloggen och dess utdata (sinks) |
| `ai/client.py` | Modellupplösning, reservkedja, kostnad, validering av strukturerade svar |
| `ai/providers/` | En adapter per leverantör – enda stället där SDK:erna importeras |

---

## 5. Gränssnitt mot agent- och skillkod

### 5.1 Grundanrop

```python
from pydantic import BaseModel
from ai import get_client

# Bind kontext en gång per körning: team styr nyckelval och kostnadsuppföljning
ai = get_client().bind(team="forsakring", agent="handlaggaragent", run_id=run_id)

# 1. Fritt textsvar
sammanfattning = ai.ask("Sammanfatta ärendet nedan ...", system=instruktion)

# 2. Strukturerat svar, validerat mot Pydantic-modell
class Bedomning(BaseModel):
    kraver_eskalering: bool
    motivering: str

bedomning = ai.ask_structured(fraga, Bedomning, model="deep")   # -> Bedomning-instans
```

### 5.2 Verktygsloop (så harness använder lagret)

```python
from ai import Message, ToolResult, ToolSpec

tools = [ToolSpec.from_model("calculate_itp1_premium", "Beräknar ITP1-premie ...", PremiumInput)]
messages = [Message.user(uppdrag)]

while True:
    resp = ai.complete(messages, system=instruktion, tools=tools, model="standard")
    messages.append(resp.to_message())          # bär med leverantörens interna state
    if resp.stop_reason != "tool_use":
        break
    results = [ToolResult(call_id=c.id, content=kor_skill(c.name, c.arguments))
               for c in resp.tool_calls]
    messages.append(Message.from_tool_results(results))
```

Själva loopen – behörighetskontroll, godkännande av externa handlingar, journal – hör till harness (se `agentekosystem.md` §4.2), inte till AI-lagret. Lagret garanterar att historiken går att skicka tillbaka till vilken modell som helst i reservkedjan.

### 5.3 Kanoniska typer

| Typ | Innehåll |
|-----|----------|
| `Message` | `role` (`user`/`assistant`), `text`, `tool_calls`, `tool_results`, `provider_state` (opak). Skapas med `Message.user()`, `Message.assistant()`, `Message.from_tool_results()` eller `ModelResponse.to_message()` |
| `ToolSpec` | `name` (ASCII `snake_case`, max 64 tecken), `description`, `parameters` (JSON Schema), `strict`. `ToolSpec.from_model()` bygger strikt schema ur Pydantic |
| `ToolCall` | `id`, `name`, `arguments` (dict) |
| `ToolResult` | `call_id`, `content` (text/JSON-sträng), `is_error` |
| `ModelResponse` | `text`, `tool_calls`, `stop_reason` (`end_turn`/`tool_use`/`max_tokens`/`refusal`/`other`), `usage`, `cost_usd`, `provider`, `model`, `model_ref`, `requested`, `latency_ms`, `request_id`, `fallback_from`, `parsed` |
| `Usage` | `input_tokens` (alla, inkl. cache), `output_tokens` (inkl. resonemang), `cached_input_tokens`, `cache_write_tokens`, `reasoning_tokens` |
| `CallContext` | `team`, `agent`, `run_id`, `step` – sätts via `bind()` |

Alla typer är Pydantic-modeller och kan serialiseras till JSON – körjournaler kan alltså spara hela konversationer.

### 5.4 Regler för anropande kod

- **Importera bara från `ai`** – aldrig från `ai.providers.*`, aldrig `anthropic`/`openai` direkt (K1).
- **Ange modellroll, inte modell-ID.** `model="deep"` – inte `"claude-opus-5"`. Explicit `"leverantör:modell"` (t.ex. `"openai:gpt-6-astra"`) används bara för utvärdering och tester.
- **Skicka tillbaka `response.to_message()`** i historiken, inte bara texten – den bär leverantörens interna resonemangsstate som krävs i verktygsloopar.
- **Ingen `temperature`/`top_p`.** Nyare resonerande modeller hos båda leverantörerna har tagit bort eller begränsat dem. Styr med `effort` (`low`/`medium`/`high`).
- **Verktygsnamn på engelska `snake_case`** = skillens Python-namn (B-015). Beskrivningen får vara på svenska.
- **Skicka bara nödvändig data** i promptar (B-006). Lagret maskerar inte personuppgifter – det är skillens och agentens ansvar.
- **Historiken är append-only.** Redigera eller ta inte bort tidigare meddelanden i en pågående konversation (krävs för prompt caching och för att Anthropics tänkande-block ska accepteras).

---

## 6. Modellval och konfiguration

### 6.1 Roller

Agenter och flöden väljer en **roll** – vilken modell rollen pekar på är konfiguration.

| Roll | Användning | Primär modell | Reserv | Effort |
|------|------------|---------------|--------|--------|
| `fast` | Klassificering, routing, extraktion, enkla sammanfattningar, hög volym | `openai:gpt-6-luna` | `anthropic:claude-haiku-4-5` | `low` |
| `standard` | Ordinarie agentarbete med verktyg, utkast, handläggning | `anthropic:claude-sonnet-5` | `openai:gpt-6.1-sol` | `medium` |
| `deep` | Regeltolkning, konsekvensanalys, aktuariella bedömningar, granskning | `anthropic:claude-opus-5` | `openai:gpt-6-astra` | `high` |

Startvalen är prisbaserade: för `fast` kostar `gpt-6-luna` en tiondel av `claude-haiku-4-5`; för `standard` är `claude-sonnet-5` och `gpt-6.1-sol` lika dyra; för `deep` kostar `claude-opus-5` hälften av `gpt-6-astra`. Varje roll har en reserv hos **den andra** leverantören, så att en driftstörning hos en leverantör inte stoppar bolaget. Valen bör utvärderas med riktiga uppgifter när de första agenterna finns (se `agentekosystem.md` §7). Nyligen lanserade Claude Opus 5.5 och Claude Sonnet 5.5 är naturliga kandidater i den utvärderingen – de läggs till under `models:` när de ska provas.

Effort-nivåerna är startvärden: `medium` för `standard` är ett kostnadsval som ska mätas; `high` är golvet för kvalitetskritiskt arbete. Modeller som saknar effort-stöd (t.ex. `claude-haiku-4-5`) får inte parametern alls.

### 6.2 Konfigurationsfilen

`src/ai/ai_config.yaml` är den enda källan för leverantörer, modeller, priser och roller (utdrag):

```yaml
providers:
  anthropic: {type: anthropic, api_key_env: ANTHROPIC_API_KEY, max_retries: 2, timeout_seconds: 300}
  openai:    {type: openai,    api_key_env: OPENAI_API_KEY,    max_retries: 2, timeout_seconds: 300}

models:
  anthropic:claude-opus-5:
    price: {input: 5.00, output: 25.00, cached_input: 0.50, cache_write: 6.25}   # USD per 1M tokens
    capabilities: {tools: true, structured_output: true, effort: true}
    options: {prompt_caching: true, server_side_fallback: true}
  # ...

roles:
  deep:
    model: anthropic:claude-opus-5
    fallbacks: [openai:gpt-6-astra]
    effort: high
    max_output_tokens: 16000

defaults: {role: standard, max_output_tokens: 16000}
tracing:  {sink: jsonl, path: logs/ai_calls.jsonl, log_content: false}
```

En modell måste finnas under `models:` för att kunna användas – det håller pristabellen komplett och fångar felstavade modell-ID:n vid start i stället för vid första anrop.

### 6.3 Överstyrning via miljövariabler

| Variabel | Effekt |
|----------|--------|
| `AI_CONFIG_FILE` | Sökväg till en alternativ konfigurationsfil |
| `AI_ROLE_<ROLL>` | Byter primärmodell för en roll, t.ex. `AI_ROLE_DEEP=openai:gpt-6-astra`. Används för jämförande utvärdering (B-009) |
| `AI_TRACE_FILE` | Annan sökväg för anropsloggen |
| `AI_LOG_CONTENT` | `true` loggar även promptar och svar – **bara för felsökning i sandlådan** (B-006) |

### 6.4 Priser

Priser per 1M tokens ligger i konfigurationen och är verifierade 2026-10-11 mot leverantörernas prissidor. Kostnaden i loggen är en **uppskattning** (standardnivå, kort kontext); fakturan hos leverantören är facit.

---

## 7. Nyckelhantering

**Konvention:** `<LEVERANTÖRENS NYCKELVARIABEL>_<TEAM-ID I VERSALER>`, med den gemensamma nyckeln som reserv.

| Anrop bundet till team | Nyckelvariabler som provas (i ordning) |
|------------------------|----------------------------------------|
| `team="kapital"` mot Anthropic | `ANTHROPIC_API_KEY_KAPITAL` → `ANTHROPIC_API_KEY` |
| `team="kapital"` mot OpenAI | `OPENAI_API_KEY_KAPITAL` → `OPENAI_API_KEY` |
| Inget team | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` |

- **Start:** bara de två gemensamma nycklarna i `.env`. Team-nycklar läggs till när det behövs – ingen kodändring krävs.
- **Varför team-nycklar:** varje team kan få ett eget *Workspace* hos Anthropic och ett eget *Project* hos OpenAI, med eget kostnadstak och egen användningsrapport hos leverantören. Spärras en nyckel stannar bara det teamet.
- **Saknas primärmodellens nyckel** hoppar lagret till nästa modell i rollens reservkedja och loggar varför (`missing_key`). Saknas nyckel för alla modeller i kedjan ges ett `ConfigError` som namnger variablerna. Bolaget fungerar alltså med bara en leverantörsnyckel, men loggen visar tydligt att reserven används.
- **Nycklar lämnar aldrig lagret:** de läses bara i `keys.py` och skickas direkt till SDK-klienten. De hamnar aldrig i prompt, logg eller agentkontext. Loggen registrerar *namnet* på variabeln som användes, aldrig värdet.
- **Team-id** är ASCII med gemener (`forsakring`, `kapital` …) eftersom det ingår i variabelnamn. Teamindelningen beskrivs i `agentekosystem.md` §3.

---

## 8. Inkapsling av leverantörsspecifika funktioner

| Funktion | Anthropic (Messages API) | OpenAI (Responses API) | Kanonisk form |
|----------|--------------------------|------------------------|---------------|
| Systeminstruktion | `system` | `instructions` | `system=` |
| Verktygsdefinition | `tools[].input_schema`, `strict` | `tools[]` med `type: function`, `parameters`, `strict` | `ToolSpec` |
| Verktygssvar | `tool_result`-block i user-meddelande, `is_error` | `function_call_output`-item (fel markeras med `Error:`-prefix) | `ToolResult` |
| Strukturerat svar | `output_config.format` (`json_schema`) | `text.format` (`json_schema`, `strict: true`) | `output_schema=`/`ask_structured()` |
| Resonemangsnivå | `output_config.effort` (adaptivt tänkande är standard) | `reasoning.effort` | `effort=` |
| Resonemang i verktygsloopar | Tänkande-block skickas tillbaka oförändrade | Krypterade resonemangs-items skickas tillbaka (`store=false`) | `provider_state` (opak) |
| Prompt caching | Automatisk via `cache_control` på anropsnivå | Automatisk hos leverantören | `options.prompt_caching` |
| Avböjda svar | `stop_reason: refusal`; server-side `fallbacks: "default"` (beta) för Opus 5 | Refusal-innehåll eller `content_filter` | `stop_reason="refusal"` |
| Datalagring hos leverantör | Ingen konversationslagring i Messages API | `store=false` – ingen konversation sparas hos OpenAI | — |
| Omförsök | SDK:ns `max_retries` (429, 5xx, nätverk) | Samma | `ProviderConfig.max_retries` |

**Leverantörsstate och reservkedjan:** `provider_state` innehåller de råa svarsblocken. Adaptern återanvänder dem bara när de går tillbaka till samma leverantör (OpenAI: samma modell), annars återskapas meddelandet ur de kanoniska fälten (text + verktygsanrop). Därför kan en konversation fortsätta på reservmodellen hos den andra leverantören mitt i en verktygsloop.

**Server-side fallback (Anthropic):** för `claude-opus-5` skickas `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`). Om modellens säkerhetsfilter avböjer en förfrågan kör Anthropic om den på en rekommenderad reservmodell inom samma anrop. Styrs av `options.server_side_fallback` och kan stängas av i konfigurationen.

---

## 9. Felhantering och reservmodeller

| Kanoniskt fel | Orsak (HTTP) | Omförsök i SDK | Byter till reservmodell |
|---------------|--------------|----------------|-------------------------|
| `RateLimitError` | 429, kvot slut | Ja | Ja |
| `ProviderUnavailableError` | 5xx, 529 överbelastad, nätverk, timeout | Ja | Ja |
| `AuthenticationError` | 401, 403 | Nej | Nej – felkonfiguration ska synas |
| `InvalidRequestError` | 400, 404, 413, 422 m.fl. | Nej | Nej – felet är i anropet |
| `StructuredOutputError` | Svaret validerar inte mot schemat | Nej | Nej |
| `ConfigError` | Okänd roll/modell, saknade nycklar, förmåga saknas | – | – |

Alla ärver `AIError`; leverantörsfelen ärver `ProviderError` med `provider`, `model`, `status_code`, `request_id`. Varje försök – även misslyckade och överhoppade – loggas, och det slutliga svaret anger i `fallback_from` vilka modeller som provades först.

---

## 10. Spårbarhet och loggning

Varje försök blir en rad i `logs/ai_calls.jsonl` (gitignorerad):

| Fält | Innehåll |
|------|----------|
| `timestamp`, `run_id`, `team`, `agent`, `step` | Var anropet hör hemma |
| `requested`, `model_ref`, `provider`, `model` | Vad som efterfrågades och vad som faktiskt svarade |
| `outcome`, `error_type`, `error_message` | `ok`, `error` eller `skipped` (t.ex. saknad nyckel) |
| `stop_reason`, tokenfälten, `cost_usd`, `latency_ms` | Resultat, förbrukning och uppskattad kostnad |
| `request_id`, `key_env`, `fallback_from` | Felsökning hos leverantören, vilken nyckelvariabel som användes, reservkedjan |
| `content` | Prompt och svar – **bara** om `AI_LOG_CONTENT=true` |

Anropsloggen är det tekniska lagret (kostnad, prestanda, fel). Den verksamhetsmässiga spårbarheten – vad en agent beslutade och varför – hör till agentens körjournal (`agentekosystem.md` §4.3), som länkas hit via `run_id`.

**Planerat:** en databas-sink som skriver till en tabell `ai_calls` i Lakebase, så att kostnad per team och agent blir tillgänglig för BI (delprojekt 2) och företagsöversikten (delprojekt 8).

---

## 11. Testning

- **`FakeProvider`** (`ai.providers.fake`) returnerar skriptade svar och sparar alla förfrågningar för kontroll. Agent- och flödestester injicerar den via `AIClient(provider_overrides={"anthropic": fake, ...})` – inga nätverksanrop, ingen kostnad.
- **Enhetstester** (`tests/test_ai_*.py`) täcker konfiguration, nyckelval, strikta scheman, klientens reservkedja och båda adaptrarnas översättning åt båda hållen mot SDK:ernas egna typer.
- **Röktest mot riktiga API:er:** `scripts/diagnostics/smoke_test_ai.py` kör ett textanrop, ett strukturerat svar och en verktygsloop i två varv per leverantör, med billigaste modellerna (totalt några ören). Körs manuellt efter att nycklar lagts in i `.env` eller när SDK:er uppgraderas.

---

## 12. Avgränsningar i v1 och planerade utökningar

| Avgränsning | Plan |
|-------------|------|
| Ingen streaming | Behövs för den inbyggda chatten i handläggar-UI:t, som byggs efter harness (Fas 3b; UI v1 i Fas 4 saknar chatt) – läggs till som `stream()` i klienten |
| Synkront API | Asynkron variant när FastAPI-backenden kräver det |
| Bara text in | Bilder/PDF när en skill behöver det (t.ex. inkomna dokument i ärendehantering) |
| Ingen styrning av verktygsval (`tool_choice`) | Modellen väljer själv; tvingande verktygsval stöds inte längre av alla nya modeller – strukturerade svar täcker behovet |
| Ingen budgetspärr i lagret | Spärren är leverantörernas kostnadstak per workspace/projekt; lagret loggar. Budget per körning hanteras av harness |
| Ingen PII-maskering i lagret | Skills och agenter ansvarar för dataminimering (B-006) |
| Två leverantörer | Ny adapter för OpenAI-kompatibla endpoints (OpenRouter, Mistral, lokala modeller) när det behövs |
| Anropslogg som fil | Databas-sink (`ai_calls`) |

---

## 13. Lärdomar från agent-factory

| agent-factory (`core/llm_router.py`) | Här |
|--------------------------------------|-----|
| Alias som blandar nivå och leverantör (`cheap`, `smart-claude`) | Leverantörsneutrala roller (`fast`/`standard`/`deep`) + reservkedja över leverantörer |
| Modell-ID och priser hårdkodade i koden | I `ai_config.yaml`, verifierade mot leverantörerna |
| Bara enstaka frågor, ingen historik | Kanoniska meddelanden med verktygsanrop i flera varv |
| Inga verktygsanrop | `ToolSpec`/`ToolCall`/`ToolResult` – grunden för skills |
| JSON från Anthropic via prompt + regex-parsning | Nativa strukturerade svar hos båda + Pydantic-validering |
| Omförsök på alla fel, även felaktig nyckel | SDK:ernas omförsök för 429/5xx/nätverk, sedan reservmodell; 4xx omförsöks inte |
| En nyckel per leverantör | Team-nycklar med gemensam reserv |
| Användningslogg utan team | Logg med team, agent, körning, nyckelvariabel och reservkedja |
| Klienter skapas vid första anrop | Behålls – nyckel krävs först när en leverantör faktiskt används |

---

## 14. Källor (verifierade 2026-10-11)

- LiteLLM, säkerhetsuppdatering om incidenten i mars 2026: <https://docs.litellm.ai/blog/security-update-march-2026>
- Datadog Security Labs, analys av LiteLLM-incidenten: <https://securitylabs.datadoghq.com/articles/litellm-compromised-pypi-teampcp-supply-chain-campaign/>
- OpenRouter, avgifter (5,5 % på Standard-planen) och BYOK (avgiftsfritt upp till 25 000 USD/månad i listpris, därefter 5 %): <https://openrouter.ai/pricing>
- OpenAI, modeller och priser: <https://developers.openai.com/api/docs/models>, <https://developers.openai.com/api/docs/pricing>
- OpenAI, function calling, strukturerade svar och resonemang (Responses API): <https://developers.openai.com/api/docs/guides/function-calling>, <https://developers.openai.com/api/docs/guides/structured-outputs>, <https://developers.openai.com/api/docs/guides/reasoning>
- Anthropic, priser inklusive cache: <https://platform.claude.com/docs/en/about-claude/pricing>

---

## 15. Hänvisningar

- **B-009** – modellagnostisk arkitektur (kravet bakom lagret)
- **B-025** – val av egen tunn wrapper
- **B-006** – dataminimering (ingen innehållsloggning som standard)
- **B-016** – spårbarhet i orkestrerade flöden
- `02_system/agentekosystem.md` – team, skill-poddar, modellval och nyckelhantering på ekosystemnivå
- Kod: `src/ai/`, tester: `tests/test_ai_*.py`, röktest: `scripts/diagnostics/smoke_test_ai.py`
