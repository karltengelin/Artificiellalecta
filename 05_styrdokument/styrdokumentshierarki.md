# Styrdokumentshierarki – minimal grund för kapitalförvaltningen

> **Dokument-ID:** SD-STYR-001 | **Version:** 0.1 | **Dokumentdatum:** 2026-10-24
> **Status:** Utkast för beslut; inte antaget
> **Syfte:** Ange den struktur och beslutsordning som behövs för att anta placeringsriktlinjen.
> **Dokumentägare:** Operatören, i rollen ansvarig för regelefterlevnad
> **Beslutas av:** Styrelsen; i simuleringen operatören i uttrycklig styrelseroll
> **Beslutsreferens och beslutsdatum:** Ej beslutade
> **Gäller från:** Ej beslutat | **Nästa översyn:** Senast tolv månader efter ikraftträdandet
> **Omfattning:** Kapitalförvaltning i simuleringen enligt B-003 och B-019
> **Regelverksgrund:** LTF 9 kap. 4 och 7 §§; B-010, B-011, B-012 och B-015
> **Ersätter:** Inget tidigare dokument

## 1. Struktur och företräde

Dokumentkedjan enligt B-010 är regelverkskällor i `04_regulatoriskt/`,
dokumenterade tolkningar, interna styrdokument i `05_styrdokument/` och
operativ tillämpning. Styrdokument ska länka till de källor och tolkningar
de bygger på och skilja externa krav från bolagets egna val.

Inom `05_styrdokument/` används följande struktur:

- `01_styrelse/`: beslut, övergripande mandat och hänvisningar till fastställda dokument.
- `02_policies/`: övergripande principer och riskaptit.
- `03_riktlinjer/`: bindande ramar, limiter och ansvar inom ett sakområde.
- `04_processer/`: arbetssteg, kontroller, rapportering och eskalering inom beslutade ramar.

Externa bindande krav har företräde. Interna processer får inte vidga ett
mandat eller en limit i ett överordnat dokument. Motsägelser eskaleras till
dokumentägaren och beslutsinstansen före berörd åtgärd. Mappnivån avgör
inte beslutsinstansen: placeringsriktlinjen ligger i `03_riktlinjer/` och
fastställs av styrelsen. Den samlar tills vidare kapitalförvaltningens
principer och limiter; en separat placeringspolicy krävs inte i denna
minimala struktur.

## 2. Ägarskap och beslut

Dokumentägaren ansvarar för saklighet, källkontroll, ändringsförslag och
uppföljning. Compliancefunktionen samordnar strukturen och granskar
regelverksspårbarheten (B-011). Kapitalförvaltningsansvarig äger
[placeringsriktlinjen](03_riktlinjer/placeringsriktlinje.md); risk- och
aktuariefunktionerna lämnar underlag om risker och åtaganden.

I simuleringen bär operatören de ansvariga rollerna tills annat beslutas.
Roll för beredning, granskning respektive beslut ska framgå även när samma
person utför dem. Detta utgör inte en oberoende kontrollorganisation för
verklig verksamhet. Agenter får bereda och granska men inte fastställa dokument.

Denna hierarki och placeringsriktlinjen fastställs av styrelsen.
Operativa instruktioner får fastställas av verksamhetsansvarig endast
inom uttryckligt beslutat mandat. Styrelseansvar enligt lag delegeras inte
genom denna struktur. I ett verkligt tjänstepensionsföretag fastställs
styrdokumenten enligt LTF 9 kap. 4 § av styrelsen och ses över minst årligen.

Ett uttryckligt införandebeslut ska identifiera dokument-ID, version och
ikraftträdandedag. Fram till dess gäller status **utkast**. Beslutade
framtida versioner märks **antagen, kommande**, gällande versioner
**gällande** och ersatta versioner **ersatt**. Git-commit eller merge är
inte i sig ett införandebeslut. Beslutsreferens och metadata fylls i efter
beslut; nya poster i `BESLUTSLOGG.md` kräver operatörens godkännande.

## 3. Översyn och versionshantering

Dokumentägaren genomför dokumenterad översyn minst årligen och vid ändrade
regler, produktåtaganden, riskprofil, allokeringsramar eller väsentliga
avvikelser. Väsentligt ändrad investeringspolicy föranleder snar översyn
av placeringsriktlinjen. Översyn utan ändring dokumenteras också.

Ändringar bereds med konsekvensbedömning och granskas före nytt beslut.
Versionshistoriken anger datum, ändring och beslut. Tidigare versioner
ska kunna återfinnas genom Git och identifieras i använda beslutsunderlag.
Varje operativt beslut hänvisar till den dokumentversion som tillämpats.
Riskaptit, limiter och mandat får inte ändras genom en redaktionell rättelse.

## 4. Standardmetadata

Alla styrdokument ska överst ange dokument-ID, titel, version,
dokumentdatum, status, syfte, dokumentägare, beslutsinstans,
beslutsreferens och beslutsdatum, giltighetsdag, nästa översyn,
omfattning, regelverksreferenser och vilket dokument/version som ersätts.
Saknade beslutsuppgifter markeras **ej beslutade**. Datum anges som
`ÅÅÅÅ-MM-DD`; dokumentet innehåller en kort versionshistorik.

## 5. Avgränsning och underlag

Detta är en minimal grund för Fas 2a. Fullständigt styrdokumentsregister,
övriga policies och bolagets samlade kontrollsystem återstår.
All tillämpning här avser simulering. För verklig verksamhet behöver bland
annat ingivande, offentliggörande och konsekvensredogörelse för
investeringsriktlinjer hanteras enligt LTF 9 kap. 7 §.

Underlag: [regelverkskartan](../04_regulatoriskt/regelverkskarta.md),
[LTF-underlaget](../04_regulatoriskt/01_huvudregim/ltf.md) och
[LTF, 9 kap. 4 och 7 §§](https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/lag-2019742-om-tjanstepensionsforetag_sfs-2019-742/).
Angivna lagrum kontrollerade 2026-10-24 mot Riksdagens text, ändrad till
och med SFS 2026:641; framtida lydelser tillämpas inte i förtid.

## Versionshistorik

- 2026-10-24, v0.1: Första beslutsutkast för Fas 2a. Inte antaget.
