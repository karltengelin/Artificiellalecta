# T-ITP1-003 – tidsbegränsad utbetalning och förlängning

> **Status:** Utkast | **Version:** 0.1 | **Ägare:** Operatören
> **Upprättad/källkontrollerad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Omfattning:** ITP1 ålderspension, traditionell förvaltning utan efterlevandeskydd.

## Fråga och källunderlag

Hur ska tidsbegränsad pension väljas, ändras och avslutas? ”Temporär
utbetalning” används här som synonym till tidsbegränsad utbetalning.

| Källa i [källregistret](../kallregister.md) | Kontrollerad bestämmelse | Slutsats för denna utredning |
|---|---|---|
| K-ITP-AVTAL-2026 | Avdelning 1 punkt 7.5 | Tidsbegränsat uttag medges helt eller delvis, minst fem år; normalt månadsvis i efterskott |
| K-IL-UTTAG-2026 | 58 kap. 11–11 b och 20 §§ | Skatterättslig gren måste fastställas; lagens kortare undantag blir inte automatiskt ITP1-villkor |
| K-ITP-FLEX | Avtalats uppgifter om ITP-parternas överenskommelse | Förlängning under pågående utbetalning, upprepade gånger utan särskild avgift eller hälsoprövning |
| K-ALECTA-UTTAG-2026 | §8, sidor 16–18, samt pausinformationen | Hela månader, förskjutning vid paus och ändringar före sista utbetalning; jämförelse för egna villkor |
| K-AMF-UTTAG | Information för ITP1 och om val före start | AMF erbjuder 5–20 år; detta får inte göras till generell avtalsgräns |

## Tolkning och avgränsning

**Minimitid:** Vi utgår från ITP1:s fem år. ITPK:s två år och vissa andra
produkters treårsundantag ska inte blandas in. Avtalspunkt 7.5 anger ingen
generell maxlängd för tidsbegränsat uttag. Att AMF erbjuder högst 20 år och
Alecta saknar motsvarande fast gräns visar att erbjudanden behöver skiljas
från gemensamma krav. Vårt förslag är minst 60 hela utbetalningsmånader utan
fast maxlängd; det är ett bolagsval att granska, inte en obegränsad laglig rätt.

**Förlängning:** Den gemensamma överenskommelsen ger stöd för möjligheten.
Frist, hur ny tid anges och när belopp räknas om behöver eget villkor.
Förbud mot förkortning efter start behålls som föreslaget bolagsval.
Det ska inte beskrivas som ett universellt lagförbud.

**Belopp och skatt:** 11 b § hänvisar för tidsbegränsad pension enligt allmän
pensionsplan till planen i stället för 11 och 11 a §§. I övriga fall behöver
dessa paragrafers beloppsregler och undantag prövas. Tillämpligheten enligt
20 § måste fastställas. Förlängning kan ändra månadsbeloppet; en sänkning
är inte i sig ett skäl att alltid avslå, men kräver rätt beräkningsgrund.
Belopp får inte beräknas enbart som kapital dividerat med antal månader:
traditionell försäkring behöver godkänd aktuariell grund och garantihantering.

**Partiellt uttag:** Avtalet medger delvis tidsbegränsat uttag. Reglerna nedan
beskriver en utbetalningsplan för en hel vald försäkring. Kombination av
tidsbegränsad och livsvarig del inom samma försäkring kräver egen modell och
manuell utredning; avgränsningen är inte ett påstående om avtalsförbud.

## Föreslagna operativa val

- Ange den ändrade tiden som **totalt antal utbetalningsmånader från första
  starten**, inklusive redan förbrukade månader men exklusive pausmånader.
  ”Tio år totalt” får inte behandlas som ”tio år till”.
- Tillåt förändring före start inom minimitiden. Efter start tillåt längre
  total tid, även under paus och efter fem utbetalningsår. Ingen ny femårsperiod
  införs vid varje ändring.
- Tillåt övergång från tidsbegränsad till livsvarig form som föreslaget
  bolagsval, med särskild aktuariell och skatterättslig prövning. Detta är
  inte en separat verifierad universell rätt i de inhämtade källorna.
- Behåll gemensam frist: komplett begäran senast föregående månad.
  Förlängningen ska hinna få effekt innan utbetalningsplanen avslutas.
- Kunden ska få slutmånad och beloppsinformation före bekräftelse, inklusive
  att pensionen upphör efter vald tid och att prognoser kan ändras.

## Konsekvenser, giltighet och godkännande

[PR-ITP1-006](../../01_domän/produktregler/PR-ITP1-006-tidsbegransad-utbetalning.md)
beskriver val och löpande plan.
[PR-ITP1-007](../../01_domän/produktregler/PR-ITP1-007-forlangd-utbetalning.md)
beskriver förlängning. Båda följer
[gemensamma förutsättningar](../../01_domän/produktregler/UTTAG_GEMENSAMT.md)
och [förslaget till §7](../../projekt/04_produktregelverk/VILLKORSANDRING_UTTAG.md).
Ingen villkorsversion antas eller historisk utbetalning räknas om här.

Före implementation återstår godkännande av bolagsval och giltighetsdag,
aktuariell grund/garanti, tillämplig skatte-/avtalsgren samt slutavräkning.
Originalöverenskommelsen och administrationsbestämmelser behöver komplettera
Avtalats information. Produktens scope utökas inte till andra försäkringar.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Tolkning för tidsbegränsad utbetalning och förlängning |
