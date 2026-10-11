# Projekt 4: Produktregelverk & försäkringsvillkor

> Del av programmet "AI-native tjänstepensionsbolag" (MASTER_CONTEXT §4b, B-024).

## Scope

Göra efterforskning för att förstå och tolka gällande regelverk (LTF, FFFS:er, DORA, GDPR, IDD,
SFDR, AI-förordningen, skatt m.fl.), och omsätta tolkningen i en komplett uppsättning produktregler
som det egenbyggda försäkringssystemet speglar. Detta delprojekt är också hemmaplan för
flaggskeppsscenariot (MASTER_CONTEXT §1): regelverksändring → produktregel → produktionssatt
systemändring.

## Status

🟡 Pågår. Fas 1a (ITP1-regelverk, försäkringsvillkor v1.0) är klar. Utbyggnad av
`04_regulatoriskt/` per regelverk är hög prioritet i `ATT_GORA.md`.

Första arbetsutkastet till placering, skrivsätt och spårbarhet finns i
[ARBETSSATT.md](ARBETSSATT.md) (2026-10-11). Det innehåller en provregel för
premietrappan, källregister och öppna tolkningsfrågor. Dokumenten är utkast;
ingen ny villkorsversion eller produktregel är antagen genom detta arbete.

Uttagsområdet har nu sex separata utkast (tidigarelagt, uppskjutet, paus,
återupptagande, tidsbegränsad utbetalning och förlängning), se
[gemensam ingång](../../01_domän/produktregler/UTTAG_GEMENSAMT.md),
[källtolkning](../../04_regulatoriskt/tolkningar/T-ITP1-002-uttag-och-paus.md)
och [föreslagen villkorsändring](VILLKORSANDRING_UTTAG.md).
Utredningen om tidsbegränsad utbetalning finns i
[T-ITP1-003](../../04_regulatoriskt/tolkningar/T-ITP1-003-tidsbegransad-utbetalning.md).
Domänens felaktiga 63-årsgräns är rättad. Villkorsversion 1.0 är markerad
med granskningsanmärkning i väntan på beslut; uttagslogik är inte byggd.

## Beroenden

- Produktregler som tas fram här styr direkt vad premiemotorn (Fas 1c) och framtida
  försäkringssystem ska implementera

## Befintlig grund i repot

- `01_domän/ITP1_regelverk.md`, `01_domän/försäkringsvillkor.md`
- `04_regulatoriskt/regelverkskarta.md`
- B-010 (fyrlagermodell: regelverkskällor → tolkningar → styrdokument → operativt arbete)
- B-011 (compliance-agenten äger regelverk + styrdokument)
- B-021/B-022 (försäkringsvillkor v1.0, förenklingar)

## Öppna designfrågor

- Vilket regelverk används som demo-case för flaggskeppsscenariot (pensionsålder nämndes som
  exempel, inte nödvändigt bästa valet)?
- Hur dokumenteras kopplingen regelverk → produktregel → kodändring så att den är granskningsbar
  (jfr B-016 om orkestrerade flöden för compliance-kritiska processer)?
