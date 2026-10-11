# PR-ITP1-034 – distribution, hållbarhet och kontinuitet
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Tillämplighetsbedömning och egna produkt-/systemgränssnitt.
**Källor:** K-LTF, K-FFFS-DISTRIBUTION, K-GDPR, K-DORA, K-AI, K-SFDR, K-AML i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-010](../../04_regulatoriskt/tolkningar/T-ITP1-010-tvarregler.md).
**Villkor:** [§14–16 i v2.0](../försäkringsvillkor.md).

## Tillämplighet och val

Se [T-010](../../04_regulatoriskt/tolkningar/T-ITP1-010-tvarregler.md).
Kollektivavtalad pension omfattas inte automatiskt av varje regel för
individuell försäkringsbaserad investeringsprodukt. LTF 1 kap. 16 § och
FFFS 2019:21 1 kap. 4 § avgör avgränsningen. Vi väljer ändå tydlig målgrupp,
produktöversyn, intressekonfliktskontroll och begriplig information.

Målgrupp: verifierat ITP1-anslutna som väljer traditionell ålderspension
utan efterlevandeskydd; riskförmåga/kundval får inte antyda att garanti är
obegränsad avkastning. Informationen är generell produktinformation.
Individuell rekommendation kräver separat rådgivningsklassificering,
kompetens och dokumentation; en chattext görs inte till ett oregistrerat råd.

Produktens hållbarhetsbaseline är SFDR:s grundupplysningar enligt artikel 6,
utan utfästelse om artikel 8-/9-egenskaper eller taxonomianpassad andel.
Redovisa faktisk integrering/avsaknad av hållbarhetsrisk och konsekvens på
avkastning enligt dokumenterad placeringsriktlinje; inventera inte en ESG-
procent. Förvaltningsprojektet levererar det faktiska placeringsinnehållet.

DORA bedöms efter rättslig verksamhet och planmedlemmar, inte antal anställda.
Produkträttigheter/obetalda anspråk ska kunna återskapas från oförändrade
beslut och journal efter driftstörning. Saknad bankkvittens ger avstämning
före nytt uppdrag. Backup, kontinuitet, incidentrapportering och externa
IKT-avtal specificeras i system-/styrdokumentsprojekten, med detta
produktkrav som gränssnitt.

AI får inte skapa tariff eller besluta negativ rättighetsändring utan
människa. Användning för liv-/sjukförsäkringsrisk eller prissättning måste
klassificeras mot AI-förordningen före införande; vårt deterministiska
produktflöde är inte i sig ett obegränsat undantag för AI-agenter.

Ren LTF-tjänstepensionsverksamhet är undantagen från den granskade
penningtvättslagens livförsäkringsgren. Vi väljer ändå identitets-, betalare-
och kontoverifiering samt avvikelsekontroll. Om verksamhetsform/produkt
ändras prövas AML-tillämpligheten igen; inget falskt AML-lagkrav läggs på
denna produkt.

## Kontrollfall

En operatör men 500 planmedlemmar: DORA-undantag följer inte av personalantal.
Oidentifierad betalare: avstämningskonto enligt PR-018.
Prognos 5 %: ingen utfästelse om hållbarhet eller garanterad avkastning.
