# PR-ITP1-026 – månadsanspråk, bank och inkomstskatt
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Skatte-/anspråksram; egen bankdag och betalningsjournal.
**Källor:** K-SKV-PENSION, K-SKV-SINK, K-SFL, K-SFF, K-SKV-TABELL-2026, K-FAL, K-RANTA, K-SKV-RANTA i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-007](../../04_regulatoriskt/tolkningar/T-ITP1-007-skatt-och-betalning.md).
**Villkor:** [§11 i v2.0](../försäkringsvillkor.md).

## Regel

Varje uttagsdel/månad kan ha exakt ett bruttoanspråk. Det förbrukar
månadsrätt vid uppkomst, inte vid varje bankförsök. Brutto debiterar C
en gång och blir betalningsskuld. Betala i efterskott på första svenska
bankdagen efter pensionsmånaden till verifierat konto som tillhör rätt mottagare.
Flera delar kan sammanföras i ett bankuppdrag med underliggande detalj.

Saknat konto, bankavvisning eller kontobyte ger betalningshinder och
komplettering; skulden kvarstår. Försök igen med samma anspråks-ID
när kontot verifierats. Det är ingen paus och ingen ny pensionsmånad.
Om bankstatus är okänd inväntas avstämning före nytt försök.
Återkommen bankbetalning återöppnar skuld med bankreferens och skatteavstämning.

Preliminär inkomstskatt styrs av **faktisk utbetalningsdagens** år, personens
skattebeslut och utbetalarroll, inte pensionsrättens ursprungsår.
1. Giltigt individuellt Skatteverksbeslut tillämpas för den ersättning,
   period och mottagare beslutet gäller, inklusive jämkning/undantag.
2. Verifierad SINK: årets sats/beslut och tillämpligt skatteavtal. Utlandsadress
   ensam ger inte SINK. Skattefrihet/fribelopp antas aldrig för ITP utan stöd.
3. Svensk huvudinkomst: årets pensionskolumn/tabell, summerad över personens
   delar hos samma utbetalare. För 2026 är pensionskolumnen 2 för födda 1959
   eller tidigare och 6 för födda 1960 eller senare, enligt SKVFS 2025:20.
   Födelsedag under året byter inte kolumn. Begär saknat skattebeslut.
   Om villkoren i SFL 11 kap. 21 § är uppfyllda används obligatoriskt
   förhöjt avdrag: relevant tabell för utbetalarens kontorsort, plus 10 %
   av tabellavdraget. Saknad sådan års-/ortsparameter blockerar betalning
   med bibehållen skuld; använd inte en gissad kundtabell.
4. Svensk sidoinkomst: 30 %. Kund kan begära högre frivilligt avdrag,
   men lägre avdrag kräver stöd i beslut/regler.
5. För svensk A-skatt görs inget avdrag om utbetalningens sammanlagda
   ersättning understiger 100 kr eller förväntad total från samma utbetalare
   till personen under betalningsåret understiger 1 000 kr (SFL 10 kap.
   3–4 §§). Exakt 100/1 000 omfattas inte av dessa undantag. Alla delar
   räknas tillsammans; dela inte upp ett bankuppdrag för att kringgå gränsen.
   Detta undantag överförs inte automatiskt till SINK-grenen.
6. Retroaktiv/särskild engångsbetalning tillsammans med huvudinkomst
   använder årets engångstabell i motsvarande pensionskolumn. Årsunderlag
   är normalt 12 × regelbunden månadspension hos oss plus engångsbelopp,
   med dokumenterad justering enligt årets anvisning/individuellt beslut.
   Övrigt engångsbelopp använder 30 % om inget särskilt beslut styr.
   Periodbelopp och engångsbelopp särredovisas även i samma bankuppdrag.

Begäran om extra avdrag från huvudinkomst verkställs senast vid första
utbetalning som infaller två veckor efter begäran, med beaktande av
SFL 11 kap. 22 §:s undantag. Högre frivilligt sidoavdrag är vårt erbjudande.

Beräknat skatteavdrag redovisas i hela kronor enligt tillämplig skatteregel;
procentavdragets öretal bortfaller i vår grundhantering. Ingen
ROUND_HALF_UP till ören används för inkomstskatteavdrag. Netto = brutto −
avdrag, aldrig negativt. Skatt blir betalningsskuld till staten först
för faktiskt verkställd skattepliktig utbetalning; bankavvisning skapar
inte en andra skatteredovisning. KU18 eller KU19, ersättningskod 400,
används för individuppgiften; utbetalarsammanställning enligt Skatteverkets
AGI-anvisning är separat. Ingen dubbel individrapportering KU och AGI.

Dödsbo/utländskt konto/ombud/särskilt beslut kräver verifierad behörighet
och skatteklassificering, inte nya efterlevandeförmåner. Simuleringen
genererar endast journal/underlag, inga verkliga bank-/myndighetsanrop.

## Dröjsmålsränta

Skilj bolagets dröjsmål från ett verifierat mottagarorsakat hinder; dokumentera
förfallodag, fullständigt underlag, orsak och rättslig dröjsmålsdag. FAL 20 kap.
15 § hänvisar till 16 kap. 1 §, där även regler för icke-periodisk ersättning
och ostridig del finns. Egna kompletteringsfrister undanröjer inte lagen.
Tillämplig ränta enligt räntelagen 6 § är halvårets referensränta + 8
procentenheter. Beräkna separat på förfallet belopp per dag med ACT/365,
dela vid halvårsskifte och avrunda totalen till ören. Kundkapitalet debiteras
inte. Rättsligt fastställd startdag ingår, betalningsdagen undantas i vår
beräkningskonvention. Räntan är egen ersättningspost med separat
skatte-/rapporteringsklassificering, inte ny pensionsrätt eller arvsvinst.

Dröjsmålsränta på vår skuld klassificeras som ränteinkomst, separat från
pensionens KU18/19. För obegränsat skattskyldig fysisk person/svenskt
dödsbo görs normalt 30 % avdrag i hela kronor och KU20-underlag.
Detta är ränta på fordran, inte ränta på inlåningskonto; <100-kontoundantag
eller pensionens <100/<1 000-undantag används inte. Begränsat skattskyldig
mottagare har normalt inget svenskt avdrag från ränta enligt SFL 10 kap.
16 §; KU20-uppgift och eventuellt skatteavtal prövas separat. Pensionens
SINK-beslut läggs inte automatiskt på räntan. Avvikande myndighetsbeslut
och faktisk skattskyldighet har företräde.

## Kontrollfall

Brutto 1 000, sidoavdrag 30 %: skatt 300, netto 700, kapitaldebit 1 000.
Decemberrätt betald första bankdagen i januari använder januariårets skatt.
2025-rätt utbetald 2026 med SINK-beslut: 2026-regel, inte automatiskt 25 %.
Bankavvisning och nytt försök: en bruttopost och en lyckad nettobetalning.
