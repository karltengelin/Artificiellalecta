# PR-ITP1-010 – dödsfall och avräkning
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Avtalets dödsmånad; egen datum- och avräkningskonvention.
**Källor:** K-ITP-AVTAL-2026, K-DODSFALL-ALECTA i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-005](../../04_regulatoriskt/tolkningar/T-ITP1-005-dodsfall-och-arvsvinster.md).
**Villkor:** [§12 i v2.0](../försäkringsvillkor.md).

## Regel och indata

Verifierat dödsdatum, källreferens och rapportdatum krävs. Flagga misstänkt
dödsfall stoppar nya bankuppdrag för kontroll, men raderar inte intjänad rätt.
Produkten har inget efterlevande- eller återbetalningsskydd.

Pågående ej pausad del har rätt till **hela dödsmånaden**, även vid dödsfall
den första dagen, därefter inga nya rättigheter. Dödsfall före första
start ger ingen pension. Vid ny första start/återstart samma månad som
dödsfallet uppkommer rätt om planen gäller och dödsdatum är på eller efter
månadens första dag. Datumfältet saknar klockslag; vi väljer därför att
även dödsfall på startdagen ger hela rättighetsmånaden. Dödsdatum före
startdagen hindrar start/återstart. Samma dödsmånadsprincip används för
ny och tidigare pågående del; inget särskilt första-dagen-avslag införs.
En redan beslutad paus gäller även under dödsmånaden och skapar inget belopp.

Avräkna alla förfallna obetalda bruttorättigheter L. Om L redan debiterats
kapital och ligger som betalningsskuld ska det **inte** dras igen. Annars
förs beloppet från C till betalningsskulden en gång. Saknas C finansieras
rätten enligt PR-028. Faktiskt återstående icke-negativt C förs till pool
enligt PR-011. Frigjord garanti/skuld är inte ytterligare tillgångar.

Dödsbo kan få äldre obetalda anspråk efter behörighets-/skatteprövning,
inte återstående pensionskapital. Efter dödsdatum krävs manuell avräkning
av sen premie/rättelse; löne- eller premieinformation kastas inte bort.
En felaktig senare utbetalning ger återkravsprövning enligt PR-019.
En fordran på dödsbo är inte kontanter i arvsvinstpoolen.

## Kontrollfall

C=1 000, obetald dödsmånadsrätt 100 ännu ej debiterad: skuld 100,
pool 900. Redan debiterad skuld och C=900: pool 900, inte 800.
C=80, giltig rätt 100: bolagsstöd 20, pool 0.
Dödsfall under paus: endast äldre obetalda rättigheter avräknas.
Dödsfall på beslutad start-/återstartdag: en hel månadsrätt, därefter avslut.
