# Certa och bolagets lokala inloggning

Den lokala webbstarten öppnar Certa på `/`. Klicka på märket i kokongen för
att skriva användarnamn och lösenfras. Operatören öppnar Centralen och når
Försäkring samt de arbetsytor som finns i den valda miljön. Handläggaren öppnar
Försäkring med bestånd, ärenden, premier, pensioner och handläggningens godkännanden.

Genvägen avgör vilken server och databas som startas. Kontot avgör vilka
sidor och åtgärder som tillåts på den servern. Servern prövar också direktlänkar
och använder den verifierade användarens id i tjänstelagrets händelselogg.
Bankfilsgodkännande, månadsstängning och andra redan skyddade bolagsåtgärder
kräver operatörens session.

## Kom igång

Operatören använder sitt befintliga lokala konto. Vid första provisionering
eller byte av lösenfras använder operatören en interaktiv terminal från
huvudcheckouten:

```powershell
python scripts/web/set_operator_password.py
python scripts/web/set_operator_password.py --handlaggare <namn>
```

Det andra kommandot används när ett handläggarkonto behövs. Operatörsnamnet
är som standard `karl`. Skriptet frågar efter lösenfrasen två
gånger med dold inmatning och skriver bara dess Argon2id-hash till `.env`.
Lösenfrasen ska vara 12–1 024 tecken. Ingen lösenfras eller hash skrivs till
terminalen. Skriptet vägrar utan interaktiv terminal eller om målfilen heter
något annat än `.env`; det bevarar övriga miljövariabler.

`--operator <namn>` väljer ett annat operatörsnamn. `--env-file <sökväg-till-.env>`
väljer konfigurationsfil. Starta om respektive miljös webbserver efter
provisionering eller byte. Använd sedan den vanliga skrivbordsgenvägen eller
DEMO-genvägen. [Start och datakällor](handläggar-ui.md#3-starta).

| Variabel | Betydelse |
|---|---|
| `OPERATOR_ID` | Namngiven lokal operatör. Standard `karl` |
| `OPERATOR_PASSWORD_HASH` | Operatörens Argon2id-hash |
| `HANDLAGGARE_LOGIN_ID` | Namngiven lokal handläggare med annat användarnamn än operatören |
| `HANDLAGGARE_PASSWORD_HASH` | Handläggarens Argon2id-hash |

Faktiska värden hör endast hemma i gitignorerad `.env`. `.env.example`
dokumenterar variablerna utan värden. En tom hash lämnar motsvarande konto
avstängt. En felaktig hash stoppar konfigurationen med ett sanerat fel.

### Moduler vid start

Samma lokala `.env` används av skrivbordsgenvägen, miljöbytaren och en vanlig
kommandostart. `WEB_ACTUARY_WORKSPACE=true` ansluter aktuariedialogen med
befintlig AI-konfiguration, lokala DM Sans-filer och aktuarierollen i Lakebase.
`WEB_COMPANY_ORCHESTRATOR=true` aktiverar nya bolagsuppdrag i Demo med
konfigurerad operatör och modell. Sätt värdena en gång och starta om servern.
Centralens avsnitt **Arbetsytor** visar vilka funktioner som är anslutna i
miljön. Modellkörningar startas genom respektive arbetsyta.

## Session, rättigheter och livslängd

Sessionen ligger i serverprocessens minne. Webbläsaren får en slumpmässig,
ogenomskinlig cookie; servern lagrar endast dess hash som uppslagsnyckel.
Sessions-id och formulärtoken byts vid lyckad inloggning och den tidigare
sessionen återkallas. Utloggning görs med POST och giltig sessionstoken;
GET loggar inte ut. Serveromstart återkallar samtliga sessioner.

- **15 minuters inaktivitet** eller **8 timmars absolut livslängd** avslutar
  sessionen. Aktivitet förlänger inte den absoluta gränsen.
- Cookien har `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/` och inget
  `Domain`. Namnet `__Host-al-operator-<miljö>` skiljer miljöerna åt på samma
  värd; serverlagret är separat per process. Miljöbyte överför ingen session.
- Fem felaktiga försök inom fem minuter ger fem minuters väntan. Gränsen
  delas av den lokala appens alla namn-/IP-försök och sessioner, även vid
  samtidiga anrop. Den ligger också i processminnet och återställs vid omstart.
- Identiteten i tjänstelagrets läsningar och åtgärder kommer från den verifierade
  sessionen. `HANDLAGGARE_ID`, formulärfält och proxyhuvuden är inga
  inloggningsbevis. Sessionen ger inte `policy_admin`, nya poddar,
  personuppgiftsmandat eller databasrättigheter.

Första driften är fortfarande **HTTP på loopback**, med serverbindning till
`127.0.0.1` och godkänd Host. `Secure` slås aldrig av som reserv. In- och
utloggning med säker cookie har verifierats på `http://127.0.0.1` i Codex
inbyggda Chromium-webbläsare. Övriga webbläsare har inte verifierats i denna
leverans; de måste stödja säkra cookies på loopback. HTTPS krävs enligt
designstoppet före OC-5:s styrning eller annan serverbindning än loopback.
Ingen certifikatuppsättning eller exponerad nätverksserver ingår här.
Startkommandot accepterar inte proxyhuvuden (`proxy_headers=False`).

## Koppling till nya skrivvägar

Återanvänd `web.operator_auth.operator_action(request, form)` **före varje**
anrop till uppdragsadaptern för start, körning, granskning och avbrytande.
Hjälparen kontrollerar verifierad session, skrivmetod, exakt ursprung inklusive
port och sessionsbunden formulärtoken, och returnerar en `Actor.human` för
den verifierade operatören. HTTP 401 betyder att session saknas/har gått ut;
403 betyder att formulärtoken eller ursprung inte godtas. Nekanden får inte
starta en körning eller fatta ett grindbeslut.

```python
from web.operator_auth import operator_action

form = dict(await request.form())
actor = operator_action(request, form)
# Först därefter: uppdragsadapterns start/decide/cancel med denna actor.
```

Den gemensamma renderingen tillhandahåller `operator_user` och `operator_csrf`.
Bolagsfrågornas formulär använder `operator_csrf`; den gamla `csrf_token`
är handläggningens processtoken och godtas inte av den nya hjälparen.
`operator_actor(request)` finns för läsvägar som behöver verifierad operatör.
Försäkringsvägar använder `handler_ctx` och `check_csrf` för aktör och
formulärskydd. Bolagets godkännanden och försäkringens förslag skiljs åt på servern.

**Referer och ursprung:** inloggningssidan och sidor med aktiv operatörssession
använder `Referrer-Policy: same-origin` i både svarshuvud och HTML-meta.
Det skickar ingen referer till andra webbplatser och gör att vanliga POST-formulär
behåller sitt ursprung. `Origin: null` eller annat ursprung nekas även med
rätt token. `no-referrer` kan göra `Origin` till `null` för formulärposter;
se [MDN:s Origin-dokumentation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin).
Utloggade äldre sidor behåller `no-referrer`. Resurslänkar med uttrycklig
`referrerpolicy="no-referrer"` behåller detta, exempelvis typsnittslänken.

## Förhållande till tidigare lokal inloggning

OC-3a val H–I införde den lokala operatörssession som Certa återanvänder.
Den tidigare avgränsade formen finns för uttryckligt skapade instanser med
`WebSettings(portal_login=False)`, till exempel äldre automatiserade prov.
Normala webbstarter använder Certa och kräver verifierad session. OC-5:s
modell- och budgetstyrning har egna beslutade identitets- och transportkrav.

## Kontroller och kvarstående verifiering

`tests/test_web_auth.py` ingår i grupperna `web` och `security`. Proven
täcker in-/utloggning, rotation, förfalskad aktör, gamla/felaktiga tokens,
ursprung och Host, anonym/utgången/återspelad session, miljö- och processbyte,
samtidiga felaktiga försök, formulärgränser, provisionering och sanerad utmatning.
Inloggningssidan kan visas utan verksamhetsdatabas och dess svar cachas inte.

Det lokala Certa-provet använder separata syntetiska konton och SQLite-demo.
Proven kontrollerar rollstyrda startsidor, direkta anrop, sessionsbunden
formulärtoken och vem som står som aktör i händelseloggen.
Sessionen är lokal för en process: flera webbprocesser eller ett gemensamt
sessionslager ingår inte.

Argon2id använder det etablerade biblioteket
[`argon2-cffi` 25.x](https://argon2-cffi.readthedocs.io/en/stable/api.html),
med slumpmässigt salt och bibliotekets standardparametrar. Ingen egen
kryptografisk implementation används.

### Historisk leveranskontroll för OC-3a 2026-10-27

| Kontroll via `scripts/testing/run_tests.py` | Resultat |
|---|---|
| `--changed --base origin/main --run` (hela lokala sviten på grund av nytt beroende/testkatalog) | 1 244 godkända, 78 bortvalda; 66 testfiler, 139,73 sekunder |
| `--suite web --dependents --run` (webb och körverktyg efter importstädning) | 283 godkända; 15 testfiler, 80,11 sekunder |

Postgres-proven var bortvalda, inte godkända eller körda. Ändringsplanen
pekade inte ut något berört Postgres-prov. Ruff för de ändrade Pythonfilerna,
lokala dokumentlänkar och `git diff --check` är kontrollerade. Ingen identisk
helkörning upprepades efter enbart importstädning och dokumentuppdatering.
Testbiblioteket installerades i arbetskopians gitignorerade cache; den delade
Pythonmiljön och operatörens lösenordsinställningar ändrades inte.
