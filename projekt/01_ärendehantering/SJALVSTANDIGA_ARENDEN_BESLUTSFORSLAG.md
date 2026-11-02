# Beslutsförslag: självständiga ärendekörningar (F5-7)

> **Status:** Designstopp. Förslag till operatören, inte beslutat. Ingen kod, policy eller drift är ändrad.
> **Datum:** 2026-11-02, på `main` `4f769ac` (F5-5–6 verifierade i Lakebase).
> **Underlag:** [ärendedialog och automation](../../02_system/arendedialog_och_automation.md),
> [handläggar-UI §4](../../02_system/handläggar-ui.md#4-sidor), `src/agents/case_policy.yaml`,
> `src/agents/case_workspace.py` (`enqueue_daily`, `_claim`, `settle`), `src/services/case_review.py`,
> `scripts/agents/run_case_worker.py`, PR-ITP1-014 (löneunderlag) och -019 (rättelser).
> **Bygger på:** B-028, B-033, B-036, B-038 (budgetpolicy) och B-040 (Postgres-prov).

---

## 1. Läget

Hela kedjan ärende → agent → förslag → beslut → stängt är verifierad i demo, `svc_test` och Lakebase
(F5-5–6). Arbetaren, budgetboken och den betrodda automationsvägen finns. Ärendepolicyn har bara
`salary_report`, med `review_required: true`, `auto_close: true` och avstängt schema (07.00
Europe/Stockholm).

Läsningen av koden inför valen visade fyra saker:

1. **Urvalet skiljer inte på fall.** `enqueue_daily` väljer alla öppna `salary_report`, både nya
   rapporter, rättelser och manuella underlag. Bara automationskontrollen i `guard_case_proposal`
   begränsar till `kind: new` och `source: employer`.
2. **Schemat kan ta hela dagsbudgeten.** Varje försök reserverar handläggaragentens hela körtak
   (0,50 USD) utan återbetalning. 5 USD räcker därför till 10 försök, oavsett `max_jobs_per_day: 20`.
   Urvalet fyller alla platser, och då nekas handläggarens egna deluppdrag samma dag. Verklig kostnad
   i F5-5–6 var 0,04–0,10 USD per ärende.
3. **Policyn är gemensam för alla databaser och binds med sin hash.** Ett byte gör att köade och
   väntande uppdrag med den gamla bilden stoppas för handläggare. Därför ska bytet göras när inga
   uppdrag är aktiva i måldatabasen.
4. **Arbetsstatus syns dåligt i listan.** `/arenden` filtrerar på ärendestatus. Ett uppdrag som står
   på `needs_human` eller `reconciliation_required` syns där bara som *Pågår*.

Ärenden kommer i dag bara in genom handläggarens registrering (`create_case` är `HUMAN_ONLY`,
kanal `manual`). Det är handläggaren som anger om underlaget är arbetsgivarens rapport eller ett
manuellt underlag.

## 2. Val och rekommendationer

### A. Vilka ärendefall ingår

| Fall | Dagligt urval (agenten förbereder) | Automatisk slutbehandling |
|---|---|---|
| Ny arbetsgivarrapport (`kind: new`, `source: employer`) | **Ja** | Nej tills vidare (val C) |
| Rättelse från arbetsgivare (`kind: correction`, `source: employer`) | **Ja** | Aldrig i denna väg |
| Manuellt underlag (`source: manual`) | **Nej**, överlämnas för hand i panelen | Aldrig i denna väg |

*Skäl:* Agentens förberedelse är läsning, beräkning och ett förslag som granskas, så risken är låg
även för rättelser. Det var också rättelser som verifierades i F5-5–6. Ett manuellt underlag har
handläggaren redan framför sig, och om det väljs kl. 07.00 kan det krocka med handläggarens eget
arbete. *Alternativ:* bara nya rapporter i urvalet (smalast, men rättelser förbereds inte), eller
alla fall (dagens kod, men manuella underlag väljs också).

*Kräver kod:* urvalsfilter i policyn (`kinds`, `sources`) som `enqueue_daily` tillämpar i frågan.
Standardvärdet ska ge dagens beteende om fälten saknas.

### B. Dagligt urval, tid, antal och budget

- **Slå på:** ja. Först i demo och `svc_test` (steg 2), sedan i Lakebase efter verifiering (steg 3).
  Driften aktiveras först när arbetaren schemaläggs (val D). YAML-ändringen ensam startar ingenting.
- **Tid:** 07.00 Europe/Stockholm, oförändrat. Urvalet gäller *från* 07.00 samma dag, så en senare
  körning samma dag tar igen en missad start.
- **Antal:** högst **5 ärenden per dag ur schemat** (nytt fält `schedule.max_cases`). Totalt för
  ärendetypen gäller fortsatt 20 försök och 5 USD per dag, vilket lämnar minst 5 försök till manuella
  överlämningar och deluppdrag.
- **Budget:** 5 USD per dag och ärendetyp, oförändrat. Med reservationen ger det ett tak på
  10 försök per dag. Verklig förbrukning väntas bli under 0,50 USD per dag.

*Alternativ:* höja dagsbudgeten i stället för att införa ett eget schematak. Det löser inte
problemet, eftersom urvalet ändå fyller alla platser. Att sänka agentens körtak (0,50 USD) är en
körpolicyfråga för `ecosystem.yaml` och ingår inte här.

### C. Granskning: `review_required`

**Rekommendation: behåll `true` för alla fall nu.** Automatiken prövas bara i demo och `svc_test`,
med en tillfällig policyfil i röktestet. Den slås inte på i Lakebase.

*Skäl:*
1. Det finns ingen inkommande kanal. Varje ärende knappas in av handläggaren, och automatiken kräver
   exakt överensstämmelse med ärendet. Ett inknappningsfel skulle därför gå rakt igenom utan att en
   andra person ser det.
2. Automationsvägen är inte verifierad med riktig modell i Lakebase.
3. Premie ur löneunderlag (paket A) är inte byggd. När den byggs får en automatisk registrering
   ekonomiska följder.

*Villkor för att senare föreslå `false` för ny arbetsgivarrapport:* en verifierad inkommande kanal
där arbetsgivarens uppgifter inte knappas in av handläggaren (val E). Dessutom betrodda
rimlighetskontroller, till exempel ingen tidigare rapport för månaden, en aktiv premiebetalande
försäkring och anställning under månaden, och en löneförändring mot föregående rapport inom ett
granskat intervall. Till det kommer verifiering i alla tre miljöerna och en fungerande
uppföljningsrutin (val D). Det blir en ny granskad policyändring och ett eget beslut.

### D. Körning och uppföljning

**Rekommendation: schemalagd `--once` via Windows Schemaläggaren.**

- En uppgift körs vardagar 07.05 mot vald databas från huvudkatalogens Pythonmiljö, med `.env`
  oförändrad. Inställningar: *Kör så snart som möjligt efter missad start*, *Starta inte en ny
  instans om den redan körs* och utdata som läggs till i `logs/case_worker.log`.
- Varför inte `--serve`: processen måste hållas igång i ett fönster, stannar vid sömn och omstart,
  och en krasch under körning ger avstämningsfall. Webben hanterar redan manuella överlämningar och
  följer upp beslut i `/godkannanden` (`settle`). Arbetaren behövs bara för urvalet och för kvarlämnade
  köposter.
- Schemaläggaren skapas av operatören eller med operatörens OK, eftersom den är en stående
  konfiguration på operatörens dator.
- **Ansvar:** operatören (Karl), som ensam handläggare. Daglig kontroll:
  1. att uppgiftens senaste resultat är 0 och att loggraden finns,
  2. förslag i `/godkannanden`,
  3. uppdrag på `needs_human` eller `reconciliation_required`.
  Avstämning av avbrutna körningar görs i ärendepanelen enligt befintlig väg.
- *Kräver kod (liten):* arbetaren skriver antal uppdrag per uppföljningsstatus i loggen, och `/arenden`
  får ett filter för *uppdrag som behöver handläggare*. Utan detta syns punkt 3 bara ärende för ärende.

### E. Hur ärenden kommer in

**Rekommendation: tills vidare handläggarens registrering i `/arenden/ny` och märkta
verifieringsärenden.** En riktig kanal designas inom paket A, inte i F5-7.

- *Nu:* handläggaren registrerar ärenden under dagen och agenten förbereder dem nästa morgon.
  Källan (`employer`/`manual`) anges i formuläret och styr urvalet enligt val A.
- *Senare (paket A):* ett betrott intag av arbetsgivarfiler i ett definierat format. Det skapar
  ett ärende per person och månad med egen kanal, källreferens och idempotens. Intaget kräver att
  `create_case` får en systemaktör för intaget eller körs under operatörens identitet. Det är ett eget
  designstopp tillsammans med premie ur löneunderlag. Månadssimulatorn (paket C) kan leverera
  fiktiva arbetsgivarfiler till samma intag.

## 3. Policyändringen (steg 2, efter beslut)

```yaml
schema_version: 1
policy_id: case-work-v2
case_types:
  salary_report:
    review_required: true
    auto_close: true
    max_jobs_per_day: 20
    max_daily_cost_usd: 5.0
    schedule:
      enabled: true
      timezone: Europe/Stockholm
      hour: 7
      minute: 0
      max_cases: 5            # nytt: schemats andel av dagens försök
      kinds: [new, correction] # nytt: urvalsfilter
      sources: [employer]      # nytt: manuella underlag väljs inte
```

Kodtillägg med tester: de tre fälten i `CasePolicy` och `enqueue_daily`, statusraden i arbetaren och
filtret i `/arenden`. Dokumentationen uppdateras i samma commit-grupp. Policyn byts när inga uppdrag
är aktiva i måldatabasen.

## 4. Verifiering

**Steg 2, demo och `svc_test` med riktig modell.** Röktestet utökas med ett schemaläge, eller får ett
eget skript, som använder en tillfällig policyfil. Ingen ändring av webbens eller arbetarens
standardpolicy behövs för proven.

- Schemalagt urval: tre öppna ärenden (ny rapport, rättelse, manuellt underlag). Bara de två första
  väljs, en körning ger förslag och en körning till väljer inget nytt.
- Stoppvägar: schemataket (`max_cases: 1` ger ett urval), dagsbudgeten (manuellt deluppdrag efter
  förbrukad budget stoppas med meddelande) och policybyte under väntan (uppdraget stoppas för
  handläggare).
- Uppföljning efter beslut: godkännande stänger ärendet automatiskt, avslag lämnar det till
  handläggaren, och statusraden och filtret visar rätt uppdrag.
- Automatiken bara här: med tillfällig `review_required: false` stängs en ny arbetsgivarrapport med
  `case_automation`, medan rättelsen stannar för granskning.
- Proven: `run_tests.py --changed`, `--postgres` när verktyget varnar.

**Steg 3, Lakebase**, efter backup, operatörens uttryckliga OK och bekräftelse att ingen annan agent
kör mot databasen. Bara märkta verifieringsärenden med Vera Verifiering (AL-000499).

- Kontrollera först att inga uppdrag är aktiva och att CASE-000001–000003 är stängda.
- Registrera en rättelse av 2026-10 (v4) med `source: employer` och ett manuellt underlag. Kör
  `--once` efter 07.00 och kontrollera att bara rättelsen väljs. Godkänn och kontrollera det
  automatiska avslutet. Stäng det manuella ärendet för hand.
- Ny rapport: Veras försäkring är fribrev sedan S6. Vid torrkörningen avgörs om det finns en månad
  där en ny arbetsgivarrapport är rimlig. Om inte prövas nyfallet bara i demo och `svc_test`. Ett
  stopp från agenten för en fribrevsförsäkring räknas då som ett godkänt avvikelsefall.
- Läs tillbaka radantalen mot backupen. Därefter skapas uppgiften i Schemaläggaren mot Lakebase.

## 5. Utanför F5-7

- Intag av arbetsgivarfiler och premie ur löneunderlag (paket A), fler ärendetyper,
  extern komplettering och delegering från personärenden.
- Gallring av dialog och resultat i `case_messages`/`case_work`, som behövs före bredare drift.
- Ett lägre körtak för handläggaragenten och veckodagar i policyn. Schemaläggaren styr veckodagar.

## 6. Förslag till beslutspost (inte införd i BESLUTSLOGG)

> **B-0xx | 2026-11-xx | Självständiga ärendekörningar för löneunderlag (F5-7)**
>
> **Beslut:** Operatören godkände valen A–E i
> `projekt/01_ärendehantering/SJALVSTANDIGA_ARENDEN_BESLUTSFORSLAG.md`.
> 1. **Ärendefall.** Dagligt urval omfattar `salary_report` från arbetsgivare, både nya rapporter
>    och rättelser. Manuella underlag överlämnas för hand.
> 2. **Urval och budget.** Urvalet körs från 07.00 Europe/Stockholm med högst 5 ärenden ur schemat.
>    Ärendetypen har totalt högst 20 försök och 5 USD reserverat per verksamhetsdag.
> 3. **Granskning.** `review_required` förblir `true` för alla fall. Automatisk slutbehandling av
>    nya arbetsgivarrapporter prövas bara i demo och `svc_test`. Den föreslås för drift först med
>    en verifierad inkommande kanal och betrodda rimlighetskontroller, genom ett nytt beslut.
> 4. **Drift.** Arbetaren körs som `--once` från Windows Schemaläggaren vardagar 07.05.
>    Operatören följer dagligen upp fel, förslag och uppdrag som behöver handläggare.
> 5. **Intag.** Ärenden registreras av handläggaren tills ett intag av arbetsgivarfiler
>    designats inom paket A.
>
> **Motivering:** Agentens förberedelse ger nytta med låg risk eftersom varje registrering granskas.
> Utan en inkommande kanal skulle automatisk slutbehandling bekräfta handläggarens egen inknappning
> utan att någon annan ser den.
>
> **Konsekvenser:** Policyändringen `case-work-v2` med urvalsfilter, schematak, statusrad och
> listfilter. Verifiering i demo och `svc_test`, därefter Lakebase efter backup och OK
> (AGENTS.md §4.5). ATT_GORA, arendedialog_och_automation, handläggar-UI, harness, agentkarta och
> handläggaragentens instruktion uppdateras.
>
> **Preciserar:** B-033 (val D) och B-036 (punkt 4). B-028:s godkännandegolv består.
