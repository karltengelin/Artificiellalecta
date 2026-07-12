# Försäkringsvillkor – Ålderspension ITP1

> **Dokumenttyp:** Försäkringsvillkor (bolagets egna villkor, lager 3 i fyrlagermodellen B-010)
> **Produkt:** Ålderspension ITP1
> **Försäkringsgivare:** Artificiellalecta (simulerat bolag, B-003 – villkoren har ingen rättslig verkan)
> **Version:** 1.0 | **Gäller från:** 2026-07-12
> **Refererade regelverk:** ITP-avtalet (Svenskt Näringsliv–PTK), se `ITP1_regelverk.md`; LTF; FFFS 2019:21 (se `04_regulatoriskt/regelverkskarta.md`)
> **Ägare:** Operatören | **Ändras genom:** nytt beslut i BESLUTSLOGG + ny version av detta dokument

---

## §1 Definitioner

| Term | Betydelse |
|---|---|
| **Försäkringstagare** | Arbetsgivare som tecknat pensioneringsavtal med Artificiellalecta (tabell `employers`) |
| **Försäkrad** | Anställd hos försäkringstagaren som omfattas av ITP1 (tabell `insured_persons`) |
| **Försäkringsavtal** | En försäkring tecknad för en försäkrad; kan innehålla en eller flera förmåner (tabeller `policies`/`policy_benefits`, B-022). Försäkringens läge över tid: `policy_states` |
| **Pensionsmedförande lön** | Kontant utbetald bruttolön per kalendermånad, enligt `ITP1_regelverk.md` §3 |
| **Pensionskapital** | Summan av inbetalda premier och tillgodoförd avkastning, minus avgifter och uttag |
| **IBB** | Inkomstbasbelopp, fastställs årligen av regeringen |

## §2 Försäkringsavtalet

1. Försäkringsavtal tecknas av arbetsgivaren till förmån för den anställde. Den anställde är försäkrad och förmånstagare till ålderspensionen.
2. Försäkringen träder i kraft den första dagen i månaden då den anställde uppfyller villkoren i §3.1.
3. Försäkringen är **premiebestämd**: bolaget garanterar inte en viss pensionsnivå, utan pensionens storlek bestäms av inbetalda premier, avkastning och avgifter.
4. Vid anställningens upphörande upphör premiebetalningen; intjänat pensionskapital kvarstår som **fribrev** och fortsätter förvaltas enligt §5.

## §3 Premier

1. Premie betalas för försäkrad från och med månaden hen fyller 25 år, till och med månaden innan hen fyller 66 år, under pågående anställning.
2. Premien beräknas per kalendermånad enligt premietrappan i `ITP1_regelverk.md` §2: 4,5 % av pensionsmedförande lön upp till 7,5 IBB/12 och 30 % av lönedelen mellan 7,5 och 30 IBB/12.
3. Arbetsgivaren rapporterar pensionsmedförande lön månadsvis. Utebliven rapportering hanteras som ärende (Fas 5).
4. Premien tillgodoförs den försäkrades pensionskapital när betalning mottagits.

## §4 Fakturering och betalning

1. Bolaget fakturerar försäkringstagaren månadsvis i efterskott.
2. Betalningsvillkor: 30 dagar. Vid utebliven betalning skapas ett ärende; försäkringsskyddet påverkas inte retroaktivt i simuleringen.
3. Varje premietransaktion registreras i `premium_transactions` med koppling till försäkringsavtal och löneunderlag – full spårbarhet från lönerapport till kapital.

## §5 Förvaltning av pensionskapital

1. Pensionskapitalet förvaltas kollektivt enligt bolagets **placeringsriktlinje** (`05_styrdokument/03_riktlinjer/`, Fas 2b).
2. Förenkling mot verkligheten (B-021): bolaget erbjuder i denna version **endast traditionell förvaltning** – inget fondval, ingen valcentral. Individuella val kan införas i senare version.
3. Avkastning tillgodoförs pensionskapitalet enligt den metod som fastställs i placeringsriktlinjen (Fas 2).

## §6 Avgifter

| Avgift | Nivå | Kommentar |
|---|---|---|
| Kapitalavgift | **0,20 % per år** av pensionskapitalet | Bolagets intäkt; debiteras månadsvis (1/12) |
| Fast avgift | **0 kr** | Ingen fast avgift i version 1.0 |

Avgiftsnivåerna är bolagets beslut (B-021) och kan ändras genom ny version av detta dokument. *(Nivån 0,20 % är vald i paritet med verkliga ITP1-upphandlade bolag.)*

## §7 Uttag av ålderspension

1. Uttag kan påbörjas tidigast från 63 års ålder och senast från 70 års ålder *(åldersgränser verifieras mot gällande regler när uttagslogik implementeras, se `ITP1_regelverk.md` §5)*.
2. Utbetalning sker som standard **livsvarigt**; den försäkrade kan välja tidsbegränsad utbetalning, dock kortast 5 år.
3. Den försäkrade kan **pausa ett påbörjat uttag**; kapitalet återgår då till förvaltning. Paus och återupptag hanteras som ärende och ska kunna utföras av den försäkrade själv i kundportalen (framtida fas) samt av handläggare i handläggargränssnittet (Fas 4).
4. Utbetalningarnas storlek beräknas enligt aktuariella antaganden i `aktuariell_grund.md` *(ej skrivet ännu – krävs innan uttagslogik byggs)*.

## §8 Efterlevandeskydd

Ingår inte (B-002). Kunder som frågar hänvisas till information om att produkten endast omfattar ålderspension utan återbetalningsskydd eller familjeskydd.

## §9 Flytträtt

Flytt av pensionskapital till eller från annan försäkringsgivare stödjs inte i version 1.0 av simuleringen (B-021). *(I verkligheten gäller flytträtt för ITP1 – kandidat för senare fas.)*

## §10 Personuppgifter

Behandling av de försäkrades personuppgifter följer bolagets behörighetsmodell (B-006): endast behöriga agenter och operatören har åtkomst till PII i `insured_persons`. Se `02_system/databasschema.md` §6.

---

## Ändringslogg

| Version | Datum | Ändring |
|---|---|---|
| 1.0 | 2026-07-12 | Första versionen (Fas 1a) |
