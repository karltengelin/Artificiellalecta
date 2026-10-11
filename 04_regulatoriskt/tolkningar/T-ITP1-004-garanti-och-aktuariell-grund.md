# T-ITP1-004 – garanti och aktuariell grund

> **Status:** Utkast | **Version:** 0.1 | **Ägare:** Operatören
> **Källkontrollerad:** 2026-10-11 | **Godkänd av/datum:** Ej godkänd
> **Scope:** ITP1 ålderspension i traditionell försäkring enligt B-002/B-021.

## Fråga och källor

Vilken garanti bör vår produkt ha och hur ska pensionsbelopp beräknas?

| Källa i [källregistret](../kallregister.md) | Bestämmelse | Betydelse |
|---|---|---|
| K-ITP-AVTAL-2026 | Avdelning 1 punkt 7.3 och 7.5 | Traditionell försäkring och pensionsberäkning; lika beräkning för kvinnor och män |
| K-ITP1-SPARFORM | Avtalats beskrivning av traditionell försäkring | Garanterad pension och möjligt överskott |
| K-GARANTI-ALECTA-2026 | Villkor §4–5 och §8 | Exempel på premiebaserad garanti, historiska antaganden och rörligt kapital |
| K-GARANTI-AMF-2023 | AMF:s information om nytt ITP-erbjudande | Hela inbetalningen som garantigrund från oktober 2023; bolagsexempel |
| K-LTF-AKTUARIE | 9 kap. 4–5 §§ | Riktlinjer, beräkningsunderlag och styrning i verkligt företag |
| K-FFFS-AKTUARIE | 8 kap. 30–31 och 36–38 §§ | Principer, antaganden, underskott och reproducerbara beräkningar |
| K-SCB-LIVSLANGD | Livslängdstabell BE0101AW | Kandidat till statistikunderlag, inte färdig försäkringstariff |

## Tolkning

**Premiebestämd är inte garantifri.** Premiebestämdhet anger hur premien
fastställs. En traditionell produkt kan ge en avtalsgaranti för den pension
premierna köper. Nuvarande villkor §2.3 blandar ihop detta och behöver
ersättas i en ny godkänd villkorsversion.

**Garantin avser en förmån.** Den ska skiljas från kontots marknadsvärde,
ett löfte om varje års avkastning och ett återbetalningslöfte till dödsboet.
En annan start eller utbetalningstid kan ge ett annat garanterat månadsbelopp.
Att tidigare belopp inte alltid gäller efter en sådan ändring innebär inte
att bolaget fritt kan ta bort intjänade garantier vid marknadsfall.

**Ingen universell procentsats fastställs här.** Avtalspunkt 7.3 ensam anger
inte vår garantiprocent. Alectas och AMF:s konstruktioner är jämförelser.
En fullständig bedömning av verklig valbarhet kräver administrationsavtal
och upphandlingsvillkor; dessa har inte granskats som bindande krav här.

**Antaganden ska ha olika roller.** Avtalsgarantin, fördelningen av möjligt
överskott, kundprognosen och värderingen av bolagets skuld är olika
beräkningar. Samma ränta eller dödlighet får inte användas överallt utan
motivering. Ett produktberäknat garantivärde är inte automatiskt en
försäkringsteknisk avsättning enligt LTF eller redovisningsreglerna.

**Livslängd kräver en modell.** För ITP1-förmånen används samma tariff
oavsett individens kön. SCB:s periodstatistik behöver anpassas för
framtida dödlighet, försäkringsbestånd, säkerhetsmarginal och höga åldrar.
Att dela kapital med återstående medellivslängd räcker inte för en
livsvarig försäkring. Längre livslängd påverkar också bolagets risk.

## Alternativ och rekommendation

| Alternativ | Bedömning för simuleringen |
|---|---|
| Ingen förmånsgaranti | Avråds som grundmodell för den beslutade traditionella produkten |
| Garanti baserad på en del av premien | Möjligt alternativ; kräver bestämd andel och avtalskontroll |
| Garanti baserad på hela mottagna nettopremien | Rekommenderat arbetsförslag, begripligt och jämförbart med bolagsexemplen |

Godkänt produktval enligt B-027: garantigrundande andel 100 %, nettoränta 0 % i
garantitariffen och individuellt versionsspårade garantidelar. Nettopremie
betyder det som faktiskt tillförs vår försäkring efter eventuella separata
externa avdrag; detta löser inte premiefrågan F-008. Kapitalavgiften 0,20 %
enligt B-021 kvarstår och ska räknas med vid ekonomisk validering.
Noll nettoränta är inte noll avgift och inte ett löfte om noll marknadsförlust.

Rörligt pensionstillägg föreslås betalas ovanpå garantin om kapital och
beslutad överskottsmodell medger det. Automatisk garantiförstärkning
införs inte i första förslaget. Den förenklingen kräver kontroll mot
valbarhetskraven om simuleringen senare ska spegla en upphandlad produkt.

## Konsekvenser och kvarstående beslut

- [Aktuariell grund](../../01_domän/aktuariell_grund.md): modell, parameterkrav och räknefall.
- [PR-ITP1-008](../../01_domän/produktregler/PR-ITP1-008-garanti.md): intjänande och skydd av garantin.
- [PR-ITP1-009](../../01_domän/produktregler/PR-ITP1-009-pensionsbelopp.md): garanterad och rörlig pension.
- [Besluts- och villkorsunderlag](../../projekt/04_produktregelverk/GARANTI_BESLUTSFORSLAG.md): produktinriktningen godkänd i B-027; villkorsinförande återstår.

Produktinriktningen är beslutad i B-027. Beräkningsmodellen är ett utkast,
inte en antagen eller kalibrerad försäkringsteknisk
grund. Dödlighetstabell, marginaler, överskottsränta, skattehantering,
kollektiv för arvsvinster och finansiering av garantiunderskott återstår.
Inga gamla garantier skapas retroaktivt utan separat övergångsbeslut.
F-005 om dödsfall är fortfarande öppen. Det här arbetet upprättar inte
bolagets fullständiga styrdokument eller myndighetsrapportering.

| Version | Datum | Ändring |
|---|---|---|
| 0.1 | 2026-10-11 | Källgrund och föreslagen garantimodell |
