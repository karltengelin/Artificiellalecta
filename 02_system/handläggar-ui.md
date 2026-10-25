# Handläggar-UI:t

> **Status:** 🟡 Under uppbyggnad i Fas 4 (delprojekt 1). **Byggt:** sök, översikt, löneunderlag och premiehistorik (S1); formulär för löneunderlag, fribrev och premierättelse (S2); godkännandekö och händelselogg (S3); anslutning av ny försäkrad, aktuell lön, kontaktuppgifter och arbetsgivare (S5). **Verifierat skarpt i Lakebase 2026-10-12** (S6, se ATT_GORA): verifieringsposten AL-000499.
> **Bygger på:** B-017 (människa som fullständig operatör), B-020 (handläggar-UI före kundportal), B-028 (tjänstelagret), B-032 (anslutning, stamdata och arbetsgivare)
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
- **Digital klarhet (B-034).** UI:t är designspråkets pilotyta (`06_design/designsprak.md`). Färger,
  typsnitt, avstånd och hörnradier finns bara i tokenfilen `src/design/digital_clarity.tokens.json`.
  `src/web/static/tokens.css` genereras ur den med `python scripts/web/build_design_tokens.py`, och
  `app.css` använder enbart dessa variabler. Härledda nyanser blandas med `color-mix()`.
  `tests/test_design_web_css.py` fallerar om `tokens.css` inte är aktuell eller om `app.css` får egna
  färgvärden. Stilarken länkas med `?v=` och en innehållshash (`web.handler.static_version`), så att
  webbläsaren inte fortsätter använda en cachad gammal version efter en ändring. DM Sans laddas från Google Fonts utan referer, eftersom adresserna innehåller
  personnummer. Saknas nätet används reserven `system-ui`.
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

**Skrivbordsgenväg (Windows).** Kör `python scripts/web/install_desktop_shortcut.py` en gång från
huvudcheckouten. Det lägger genvägen *Artificiellalecta – handläggare* på skrivbordet, med märket
som ikon: den indigofärgade rutan ur `src/design/icon.py`, med färgen ur tokenfilen. Genvägen kör
`scripts/web/open_ui.ps1`. Skriptet startar servern i ett eget minimerat fönster om den inte redan
kör, väntar tills UI:t svarar och öppnar `http://127.0.0.1:8765` i webbläsaren. Stäng serverfönstret
för att stoppa UI:t. Genvägen använder demodatabasen. `--db lakebase` ger en separat genväg mot
beståndet, och lägger man inte till den finns ingen genväg till Lakebase.

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

**Godkännandekön och händelseloggen (S3).**

| Adress | Innehåll | Operationer |
|---|---|---|
| `/godkannanden?status=vantar\|godkanda\|avslagna\|alla` | Agentförslag med operation, indata, motivering, förslagsställare och körning | `list_approval_requests`, `count_approval_requests` |
| `/godkannanden/{id}/godkann` (POST) | Godkänn med valfri kommentar. Operationen körs på nytt mot aktuellt läge, och agenten blir förslagsställare i loggen | `ServiceLayer.approve` |
| `/godkannanden/{id}/avsla` (POST) | Avslå med obligatoriskt skäl, som sparas i loggen | `ServiceLayer.reject` |
| `/handelselogg` | Hela loggen, senaste först, med urval på operation och utfall. Läsningar visas på begäran | `get_operation_events` |
| `/forsakrade/{pnr}/handelser` | Händelser som rör den försäkrade | `get_operation_events` |

**Produktparametrar (Fas 3c, 3c-P2, B-035).**

| Adress | Innehåll | Operationer |
|---|---|---|
| `/parametrar` | Gällande värden i dag som nyckeltal, alla versioner med giltighet, tillstånd, regel, källa och beslut, och formuläret för en ny version | `get_product_parameters` |
| `/parametrar/ny` (POST) | Schemalägg en ny version från en framtida månad, med regelns nya version, källa, beslut och motivering | `schedule_product_parameter_change` |
| `/parametrar/aterkalla` (POST) | Dra tillbaka en kommande version med motivering; föregående version gäller då vidare | `withdraw_product_parameter_change` |

Handläggaren utför ändringarna direkt. En agent kan bara föreslå en ny version, och förslaget avgörs i
`/godkannanden`. Procentsatser skrivs som andel (0,045 = 4,5 %) och visas i procent.

Antalet väntande förslag visas i menyn. Det hämtas med `count_approval_requests`, som inte läser
personuppgifter och därför inte loggas. Ett godkännande som krockar med dagens läge, till exempel för
att handläggaren redan har registrerat underlaget, rullas tillbaka i sin helhet. Förslaget ligger då kvar
som väntande och kan avslås. Tider visas i datorns lokala tid, medan tjänstelagret sparar UTC.

**Kön, loggen och agenterna.** De tre läsoperationerna är `HUMAN_ONLY` i registret
(se [tjänstelager.md](tjänstelager.md) §9).

**Anslutning, stamdata och arbetsgivare (S5, B-032).** Operationerna stämdes av med operatören i
`projekt/01_ärendehantering/OPERATIONER_BESLUTSFORSLAG.md`. Stödda och blockerade fall står i
[tjänstelager.md](tjänstelager.md) §9.2.

| Adress | Innehåll | Operation |
|---|---|---|
| `/forsakrade/ny` (`?arbetsgivare=`) | Anslut ny anställd: person, försäkring, förmån och premiebetalande | `enroll_insured_person`, `list_employers` |
| `/forsakrade/{pnr}/lon` | Aktuell månadslön och tjänstgöringsgrad (stamdata). Formuläret skiljer den tydligt från löneunderlaget | `update_current_salary` |
| `/forsakrade/{pnr}/kontakt` | E-post och telefon, där ett tomt fält tar bort uppgiften. Ange varifrån ändringen kommer och hur personen verifierades | `update_contact_details` |
| `/arbetsgivare` | Arbetsgivare med antal aktiva försäkrade och länk till anslutning | `list_employers` |
| `/arbetsgivare/ny` | Ny arbetsgivare (ITP) | `register_employer` |

Översikten har knappar för löneunderlag, aktuell lön och kontaktuppgifter. Startsidan har en knapp för att ansluta en ny försäkrad.

**Ärenden och handläggaragenten (Fas 5 F5-4, B-033).** Ärendet är agentens arbetsenhet och mandat. Operationerna står i [tjänstelager.md](tjänstelager.md) §9.3 och agentkörningen i `src/agents/case_runs.py`.

| Adress | Innehåll | Operation |
|---|---|---|
| `/arenden?status=aktiva\|stangda\|alla` | Handläggarens lista med typ, försäkrad, månad, mottagning, status och handläggare | `list_cases` |
| `/arenden/ny` (`?pnr=`) → `/arenden` | Registrera ett ärende om inrapporterat löneunderlag; med `?pnr=` förifylls personen och arbetsgivaren | `create_case` |
| `/arenden/{nummer}` (`?lasningar=1`) | Ärendet: inrapporterade uppgifter, agentens senaste körning, förslag i ärendet, statusbyte, stängning och historik (ändringar och förslag, läsningar på begäran) | `get_case`, `list_approval_requests`, `get_operation_events` |
| `/arenden/{nummer}/agent` (POST) | *Starta agent*: handläggaragenten körs i ärendet. Resultatet visar status, sammanfattning, förbrukning, underlag, förslag och journalens sökväg | `run_case` |
| `/arenden/{nummer}/status` (POST) | Byt status bland de öppna, och vid behov handläggare | `update_case_status` |
| `/arenden/{nummer}/stang` (POST) | Stäng med utfall och motivering | `close_case` |

- **Agenten körs synkront**, en körning åt gången i processen (B-033 val D). Knappen frågar först, eftersom körningen gör modellanrop som kostar. Modellklienten skapas vid första körningen – UI:t startar utan API-nycklar.
- **Databasrollen per läge** (B-033 val H): i `demo` och `svc_test` simuleras agentens roll och sidan visar *simulerad*; mot `lakebase` används den riktiga rollen `agent_forsakring`, vars läsrätt på `cases` verkställdes i Lakebase 2026-10-24 (F5-5).
- **Efter körningen** skriver harness ärendets status: *Väntar på godkännande* om ett förslag lagts, annars *Pågår*. Förslaget avgörs i `/godkannanden`, där det länkar till ärendet.
- **Egen registrering i ärendet.** *Registrera löneunderlaget själv* öppnar löneunderlagsformuläret med ärendets uppgifter och ärendenumret medskickat (`?arende=`). Registreringen hamnar då i ärendets historik, och ärendet kan stängas som *Godkänt*.
- **Demo- och testdatabasen** får nya tabeller, som `cases`, när UI:t startar mot en befintlig fil eller ett befintligt schema. Befintliga tabeller och rader rörs inte, och Lakebase ändras aldrig härifrån.
- Godkännandekön kallar sina poster *förslag*, så att de inte blandas ihop med ärenden.

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
