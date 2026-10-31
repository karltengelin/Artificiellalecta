# Aktuariens teamyta v1 – A3

**Byggt 2026-10-31** enligt
[A3-uppdraget](../projekt/06_avdelningsfunktioner/UPPDRAG_A3_CODEX.md), B-042,
B-036 och B-041. Arbetsbranch: `codex/aktuarie-teamyta-a3`.

## Arbetsvägar

| Adress | Innehåll och handlingar |
|---|---|
| `/team/aktuarie` | Översikt över gällande grunder, rapporter, agentuppdrag och väntande granskningar. FI-frister återges som statisk **plan**, enligt aktuarieteamets plan §2.4 |
| `/team/aktuarie/rapporter` | Beställ produktrapport för ett tillgängligt år med valfri precisering, se tidigare rapporters status |
| `/team/aktuarie/rapporter/<flow_id>` | Steg, sammanfattning, verifierad PDF-förhandsvisning, godkännande/avslag, avbrott och spåret *Så togs rapporten fram* |
| `/team/aktuarie/rapporter/<flow_id>/leverans/<version>/rapport.pdf` | Hämta kontrollerad rapportfil; motsvarande väg finns för `rapport.md` |
| `/team/aktuarie/antaganden` | Bibliotekets faktiska grunder, status, giltighet, beslut och innehållskontroll |
| `/team/aktuarie/antaganden/<kod>` | Läsbara antaganden, kurvor som tabeller, källor, motivering och kontrollsumma. Ett förslag kan antas eller avslås av en människa |
| `/team/aktuarie/uppdrag` | Befintliga bolagsfrågor till aktuarien, med samma adapter och granskningsregler som tidigare |

Äldre detalj-/leveransadresser `/team/aktuarie/<flow_id>` fungerar också.
Äldre POST till teamroten stöds för befintliga formulär. Nya formulär och
länkar använder `/uppdrag`. Centralens adresser och arbetsflöde består.

Värderingar, FTA-analys, Bokföringsunderlag, Scenarier samt Data och kvalitet
visas inaktiva med orsaken **kräver värderingsmotorn (A6)**. Teammenyn är
öppningsbar på smala skärmar så att innehållet kommer före hela menyn.
Inga värden från skissens exempelläge används.

## Genomförande

1. Återanvänd `ProductReportConsole`, `QuestionConsole` och antagandebibliotekets
   operationer. Ingen ny agent, rapportmotor eller SQL i routerna.
2. Bygg teamöversikt, rapportbeställning/-granskning och grundsidor. Flytta de
   befintliga agentuppdragens primära adresser till `/uppdrag`.
3. Bind skrivformulär till verifierad session, CSRF och engångstoken.
4. Verifiera hela HTTP-förloppen med testmodell och lokal demo, sedan layout
   och PDF-visare i webbläsaren. Kör berörda grupper och hela lokala sviten.

Koden ändrar bara webbområdet, befintliga webbtester och webbdokumentation.
Inga ändringar görs i agenter, tjänsteoperationer, modeller eller databasroller.
Ingen migration eller Lakebase-körning behövs för detta uppdrag.

## Anslutning

```powershell
python scripts/web/start_ui.py --db demo --actuary-workspace --report-font-dir <mapp-med-DM-Sans>
```

`--company-questions` stöds också och ansluter båda adaptrarna. Den explicita
starten skapar AI-klienten och ansluter rapporter, men kör ingen agent förrän
en operatör beställer ett uppdrag. `--actuary-workspace` är inte en testmodell
eller ett alternativt dataläge.

`web.database.build_actuary_services` återanvänder samma databasanslutning,
aktuarietjänst och AI-klient för båda adaptrarna. I Lakebase används
`agent_aktuarie`; i demo/test följs den befintliga simulerade rollmodellen.
Miljö/dataset måste stämma med webbens inställningar; ingen annan datakälla
används om underlaget saknas. Översikten kan visa biblioteksdata även när
rapport-/frågeadaptrarna inte är anslutna, med tydliga uppgifter om vad som saknas.

Skrivvägarna kräver lokal operatörsinloggning. Befintlig installation saknar
operatörslösenfras enligt kontrollen vid ärendestödets driftsättning samma dag;
den väljs interaktivt med `scripts/web/set_operator_password.py`. Starta om
webbprocessen efter konfigureringen. Läsning följer den befintliga lokala
webbens avgränsning; teamytan visar inga individuppgifter från beståndet.

## Beslut, dubbla formulär och integritet

- Identitet hämtas ur operatörssessionen. Okända formulärfält, fel ursprung
  och fel sessions-CSRF stoppas före beställning eller beslut.
- Engångstoken är bunden till session och formulärets ändamål. Granskning
  binder även uppdrag, version och underlagshash; grundbeslut binder kod och
  kontrollsumma. Ett återanvänt formulär ger 409 och ingen ny åtgärd.
- Grunden och dess kontrollsumma visas före beslut. Tjänsten kontrollerar
  aktuellt läge och oföränderligt innehåll. Antagande kräver giltighetsdag och
  beslutsreferens; avslag kräver anteckning. Garantigrundens framåtriktade
  giltighet kontrolleras av operationen och verksamhetsfelet visas i formuläret.
- Rapportgranskningen använder adapterns versions- och hashkontroller. Båda
  rapportfilerna kontrolleras före visning/hämtning; ändrade filer spärrar
  granskningen. PDF-visaren tillåter bara kända rapportvägar på samma ursprung.
- Spåret visar modeller, verktyg, utfall, kostnad och policy ur körjournalen.
  Rå konversation, verktygsindata och personuppgifter visas inte där. Saknat
  eller ofullständigt spår markeras. Oväntade serverfel saneras.

## Verifiering

Webbproven ligger tillsammans med de befintliga frågeproven i
`tests/test_web_questions.py`, i den redan registrerade webbgruppen.
De omfattar produktrapport 2025 till mänskligt beslut och riktig PDF-export,
antagande och avslag, garantidatum, autentisering, CSRF/ursprung,
engångstoken, manipulerad rapport, miljögräns och kompatibla uppdragsadresser.
Klientprov verifierar PDF-visarens tillåtna/nekade adresser.

**Utfall:** ändringsstyrt urval `web` och `tooling`: 347 godkända prov.
Hela lokala sviten: **1 433 godkända**, 89 Postgres-prov bortvalda.
Efter den sista tabelljusteringen: sex design-/PDF-klientprov godkända,
265 andra webbprov bortvalda i det avgränsade urvalet. Inga prov rapporterades
som överhoppade. Testkatalog, kodstil och diffkontroll är godkända.
Postgres kördes inte eftersom A3 inte ändrar databasmodell eller rättigheter.

Visuell kontroll använder de verkliga mallarna med lokal demodata och
testmodell i en tillfällig GET-förhandsvisning. Ingen faktisk inloggning eller
verksamhetsändring automatiseras i webbläsaren. I 375 pixlars bredd har
översikten, grundförslagets beslutsfält och PDF-visaren kontrollerats utan
sidledsrullning i dokumentet. PDF-sidbyte från sida 1 till 2 är verifierat.
Underlagets datum 2026-11-02 är ett uttryckligt testdatum.
Förhandsvisningens PDF exporterades med rapportmallens Helvetica-alternativ;
den ordinarie startvägen registrerar DM Sans ur den angivna typsnittsmappen.

- [Översikt på dator, 1280 × 720](bilder/aktuarie_a3_dator.jpg)
- [Hela översikten vid 375 pixlar](bilder/aktuarie_a3_mobil.jpg)
- [Grundbeslut vid 375 pixlar](bilder/aktuarie_a3_grundbeslut_mobil.jpg)
- [PDF-visare vid 375 pixlar](bilder/aktuarie_a3_rapport_mobil.jpg)
- [Antagandebibliotekets mobilkort](bilder/aktuarie_a3_bibliotek_mobil.jpg)

## Föreslagna statusuppdateringar i delade dokument

Enligt uppdraget redigeras inte MASTER_CONTEXT, ATT_GORA, BESLUTSLOGG eller
AKTUARIETEAM_PLAN medan A5 pågår. Förslag till operatören:

- Markera A3:s webbimplementation/verifiering som byggd på arbetsbranchen och
  länka hit. Håll integration/aktivering skild från byggstatus.
- Uppdatera hänvisningarna till aktuariens uppdrag: teamroten är översikt,
  medan `/team/aktuarie/uppdrag` är uppdragslistan.
- Uppdragsfilens sex startgrunder är nu sju efter A5:s tillägg AVK-SIM.
  Teamytan visar alltid tjänstens faktiska register och inga egna startvärden.

Inga adapter- eller operationsändringar behövdes för A3:s arbetsvägar.
