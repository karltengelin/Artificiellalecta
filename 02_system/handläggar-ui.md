# Handläggar-UI:t

> **Status:** 🟡 Under uppbyggnad i Fas 4 (delprojekt 1). **Byggt:** sök, översikt, löneunderlag och premiehistorik (S1); formulär för löneunderlag, fribrev och premierättelse (S2).
> **Bygger på:** B-017 (människa som fullständig operatör), B-020 (handläggar-UI före kundportal), B-028 (tjänstelagret)
> **Kod:** `src/web/` · **Start:** `python scripts/web/start_ui.py` · **Tester:** `tests/test_web_*.py`
> **Relaterat:** [tjänstelager.md](tjänstelager.md), [tjänstelager_operationer.md](tjänstelager_operationer.md), `projekt/01_ärendehantering/PROJEKTPLAN.md`

---

## 1. Syfte

Ett lokalt webbgränssnitt där handläggaren söker fram en försäkrad och gör ändringar som syns i
Lakebase-tabellerna och i händelseloggen. UI:t är tjänstelagrets första klient. Agenterna
(Fas 3b/5) använder senare samma operationer, med samma spår i loggen (B-017).

## 2. Teknik och gränser

- **FastAPI + Jinja2 + HTMX.** Sidorna renderas på servern. HTMX laddas från unpkg med fast version och
  SRI-hash. Det finns inget Node och inget byggsteg. Sidorna fungerar också utan JavaScript, och då ger
  HTMX bara mjukare navigering.
- **Bara tjänstelagret.** Webbkoden anropar `ServiceLayer.execute/approve/reject` och läsoperationerna,
  och rör aldrig modeller eller sessioner. Det gäller även läsningar, eftersom läsningar av
  personuppgifter loggas. Testet `test_webbkoden_ror_varken_modeller_eller_sessioner` vaktar gränsen.
  Behövs en lista eller en sökning byggs den som läsoperation med en rad i `access_register.yaml`.
- **Bara lokalt, ingen inloggning (v1).**
  - Servern binds till `127.0.0.1`, och Host-huvudet måste vara `127.0.0.1` eller `localhost`
    (skydd mot DNS-rebinding).
  - Skrivformulär bär en token per process (skydd mot att en annan webbplats postar hit).
  - Aktören är `Actor.human(HANDLAGGARE_ID)`, med standardvärdet `karl`.
- **Motivering i varje skrivformulär**, eftersom tjänstelagret kräver den för `write`.
- **Personuppgifter i webbläsaren.**
  - Adresserna innehåller personnummer, så serverns accesslogg är avstängd.
  - HTMX sparar ingen sidhistorik i webbläsarens lagring (`historyCacheSize: 0`).
  - När verklig autentisering eller kundportalen byggs bör adresserna byta personnummer mot interna id:n.

## 3. Starta

```powershell
python scripts/web/start_ui.py                    # demodatabas, http://127.0.0.1:8765
python scripts/web/start_ui.py --reset-demo       # skapa demodatabasen på nytt
python scripts/web/start_ui.py --db svc_test --port 8766
```

I Claude-appen finns startkonfigurationerna `handlaggare-ui` och `handlaggare-ui-svc-test` i `.claude/launch.json`.

| Variabel / flagga | Standard | Innehåll |
|---|---|---|
| `HANDLAGGARE_ID` | `karl` | Handläggarens id i händelseloggen |
| `HANDLAGGARE_DB` / `--db` | `demo` | `demo`, `svc_test` eller `lakebase` |

| Databas | Var | Tabeller |
|---|---|---|
| `demo` | `data/handlaggare_demo.db` (SQLite, gitignorerad) | Skapas med demobeståndet (`src/utils/demo_data.py`) om filen saknas |
| `svc_test` | Schemat `handlaggare_ui` i `SERVICES_TEST_POSTGRES_URL` | Skapas med demobeståndet om schemat är tomt. Vägrar om adressen är `DATABASE_URL` |
| `lakebase` | Beståndet via `DATABASE_URL` | Skapas aldrig. Schemaändringar görs bara med migrationsskript (T3-mönstret) |

Lakebase används aldrig av sig självt, trots att `DATABASE_URL` finns i `.env`. Mot beståndet visar
sidhuvudet en röd varning. Första skarpa skrivningen föregås av backup och operatörens OK
(AGENTS.md §4.5).

**Demobeståndet** innehåller fyra fiktiva personer och två agentförslag i godkännandekön:

| Person | Läge |
|---|---|
| 19850515-1236 | aktiv |
| 19720303-4561 | aktiv, lön över 7,5 IBB |
| 19900101-7897 | fribrev |
| 19590420-2461 | pension pågår |

Agentförslagen prövas mot regelpaketet som om det redan gällde, men bara i demodatabasen. Före
2026-11-01 kan en agent annars inte föreslå skrivningar, eftersom regelgolvet ger `HUMAN_ONLY`.

## 4. Sidor

| Adress | Innehåll | Operationer |
|---|---|---|
| `/` och `/sok?q=` | Sök på personnummer (ÅÅÅÅMMDD-NNNN) eller försäkringsnummer (AL-…) | – |
| `/forsakrade/{pnr}` | Översikt: person, anställning, aktuell lön, försäkringar med läge och kapital | `get_insured_overview` |
| `/forsakringar/{nr}` | Samma översikt, med försäkringen markerad | `get_insured_overview` |
| `/forsakrade/{pnr}/loneunderlag` | Löneunderlag per månad med alla versioner | `get_insured_overview`, `get_salary_reports` |
| `/forsakringar/{nr}/premier` | Premiehistorik med urval på månader och summa betalt | `get_insured_overview`, `get_premium_history` |

Varje sidvisning loggas som läsning av personuppgifter (vem tittade på vem). Läsresultatet loggas inte.

**Skrivformulär (S2).** Formulären visar operationens beskrivning, produktregler med status och vad
agenter får göra med operationen enligt registret och regelgolvet. Varje formulär kräver en motivering.
Efter en lyckad ändring visas operationens resultat.

| Formulär (GET) → skickas till (POST) | Operation | Nås från |
|---|---|---|
| `/forsakrade/{pnr}/loneunderlag/ny` → `/forsakrade/{pnr}/loneunderlag` | `register_salary_report`: ny rapport eller rättelse (`?typ=rattelse&manad=&version=`) | Fliken Löneunderlag |
| `/forsakringar/{nr}/fribrev` → samma adress | `set_policy_paid_up`: avanmälan och fribrev | Översikten, vid premiebetalande försäkring |
| `/forsakringar/{nr}/premier/{id}/rattelse` → samma adress | `correct_premium_transaction`: länkad rättelserad | Premiehistoriken, per premierad |
| `/berakna/premie` (POST, HTMX) | `calculate_premium_preview`: förhandsberäkning i formulären, sparar ingenting | Löneunderlag och premierättelse |

Rättas lönen för en månad som har premie, länkar resultatsidan direkt till premierättelsen med den nya lönen.

## 5. Felvisning

Tjänstelagrets fel visas i en ruta med rubrik, skäl och de produktregler som nämns, med regelns
rubrik och status ur `01_domän/produktregler/`:

| Fel | HTTP | Rubrik |
|---|---|---|
| `BlockedError` | 422 | Stoppat – kräver manuell prövning |
| `ConflictError` | 409 | Krock med aktuellt läge |
| `InvalidInputError` / `MissingReasonError` | 422 | Ogiltiga uppgifter, per fält |
| `NotFoundError` | 404 | Hittades inte |

Efter ett fel i en ändring står det uttryckligen *Ingenting har ändrats.* Tjänstelagret rullar
tillbaka hela anropet (tjänstelager.md §6.1).
