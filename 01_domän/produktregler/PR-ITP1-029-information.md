# PR-ITP1-029 – information, besked och prognoser
> **Filversion:** 1.0 | **Paket:** PR-ITP1 v1.0 | **Dokumentdatum:** 2026-10-11
> **Status:** Specificerad tillämpning för simuleringen; införande separat. Implementation ingår inte i uppdraget.
> Gemensam giltighet, behörighet, avrundning och felhantering: [regelpaketets ingång](README.md).


## Spårbarhet

**Ursprung:** Informationskrav; egna beskeds-/prognosfrister.
**Källor:** K-FAL, K-FFFS-PENSIONSBESKED i [källregistret](../../04_regulatoriskt/kallregister.md).
**Tolkning:** [T-008](../../04_regulatoriskt/tolkningar/T-ITP1-008-avtal-information-och-rattigheter.md).
**Villkor:** [§14 i v2.0](../försäkringsvillkor.md).

## Grund och regel

FAL 20 kap. och FFFS 2019:21 3 kap.; se T-008. Informationen ska vara
begriplig, daterad, korrekt och möjlig att spara. Följande är bolagets
konkreta dokumentutbud, med utökad information inom myndighetsramen:

| Tidpunkt | Besked och minsta innehåll |
|---|---|
| Före anslutning | Produkt, parter, avgift/skatt, garanti/risk, inget efterlevandeskydd, inga simulerade flyttar, uttagsval, klagomålsväg |
| Efter anslutning/ändring | Identitet, avtal/förmån, giltig version, väsentliga rättigheter och begränsningar |
| Årligen senast 31 mars | Föregående års kapitalrörelser; premie, avkastning, arvsvinst, avgift, skatt, pension och kapitalstöd separat; G, plan, prognos och osäkerhet |
| Inför pension | PR-025:s 6/3/1-månadsinformation, val/frister, garanti/rörligt brutto och preliminär skatt |
| Vid start/omräkning/paus/förlängning | Gamla/nya belopp och datum, förbrukad/kvarvarande tid, orsak och rätt att få beslut granskat |
| Inför avslut/dödsfallsavräkning | Sista rätt, obetalda anspråk, kapitalhantering, mottagarbehörighet och skatteprövning |

Kundprognos använder uttryckligt scenario, värdedag och plan. Garanti,
kapitalbaserad pension och prognos får inte blandas. 0/3/5 % är nominella
bruttoscenarier med kostnad/skatt redovisad och ingen utfästelse.
Om inflation visas väljs 2 % scenario och anges; reala och nominella
belopp blandas inte. Ny anslutning med ingen premierätt ger inga
påhittade historiska premier i beskedet.

Beskedens förmånliga avvikelse från avtal får inte rättas automatiskt;
pröva FAL:s skydd i PR-030. Årlig information får inte användas som
tyst godkännande av försämrade villkor.
Kontaktkanal är den autentiserade simulerade kundportalen eller
operatörens ärendehantering; inga påhittade telefonnummer/myndighetsstatus.

## Kontrollfall

Arvsvinst bokad 300: redovisa 300 separat, inte som premie/avkastning.
Paus: redovisa inga anspråk för pausmånader och nytt planerat slut.
