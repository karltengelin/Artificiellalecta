# Arbetssätt – ett sammanhängande produktpaket

> **Version:** 1.0 | **Datum:** 2026-10-11
> Färdig dokumentstruktur på operatörens mandat; paketet infört genom B-031, gäller från 2026-11-01.
> B-005/B-010/B-012/B-015/B-021/B-022/B-024/B-027.

## Placering och spårbarhet

| Innehåll | Hemvist |
|---|---|
| Källor, giltighet och reglernas tillämplighet | [04_regulatoriskt](../../04_regulatoriskt/regelverkskarta.md) |
| Tolkningar, K-ID → T-ID | [T-ITP1-001–010](../../04_regulatoriskt/tolkningar/T-ITP1-010-tvarregler.md) |
| Precisa produktutfall, T-ID → PR-ID | [01_domän/produktregler](../../01_domän/produktregler/README.md) |
| Kundens rättigheter | [Försäkringsvillkor v2.0](../../01_domän/försäkringsvillkor.md) |
| Beräkningsmodell, tariffer och data | [Aktuariell grund](../../01_domän/aktuariell_grund.md), [parametrar](../../01_domän/parametrar/PARAMETERREGISTER.md) |
| Samlat införande och kontroll | Denna projektmapp |
| Kod och automatiserade tester | Senare byggsession, uttryckligen utanför uppdraget |

Strukturen följer B-010:s fyra lager: källa → tolkning → bolagets
tillämpning → operativ verkställighet. Projektmappen innehåller inte
en andra normativ kopia av produktreglerna.

## Skrivsätt och gemensamt kontrakt

Stabila K-, T- och PR-ID återanvänds vid versionsändring. Varje PR-fil
har paket-/filversion, dokumentdatum, status, källa/tolkning, villkorskoppling,
precist beteende och kontrollfall. Ägare, giltighet, obligatoriska
händelseuppgifter, utfall, avrundning och felhantering anges gemensamt
i regelpaketets ingång. En specialregel preciserar den allmänna.

Externa krav och egna bolagsval ska gå att skilja. Egen tariff eller
administrativ förenkling görs inte till en universell ITP-regel.
Saknade obligatoriska fakta ger definierad komplettering/manuell prövning,
inte gissning. Redan intjänad rätt försvinner inte genom en blockerad ny händelse.

Arbetet granskas **samlat över livscykeln**, enligt operatörens utökade
uppdrag. Ett färdigt avsnitt räcker inte om det motsäger finansiering,
skatt, dödsfall eller historik. Räkneexempel och bevarandekontroll används
för dokumentmodellen; nästa session bygger och verifierar programmet.

## Status och införande

Specificerad modell betyder att parametrar och produktval är bestämda
för simuleringen. Det betyder inte antagen myndighetsvaliderad tariff,
driftsatt kod eller professionell bedömning av ett verkligt bestånd.
Extern ikraftträdandedag, föreslagen produktdag, godkännande och driftsättning
lagras var för sig.

Allt införandeunderlag är samlat i [paketförslaget](PAKET_BESLUTSFORSLAG.md),
som operatören antog 2026-10-12 som B-031 med giltighet från 2026-11-01.
Nya beslutsloggsposter skrivs först efter operatörens godkännande enligt
AGENTS/CLAUDE. Ingen ny beslutsbeteckning reserveras under parallellt arbete.
Införandet ändrar inte historiska transaktioner.

## Avslutade utredningsfrågor

| ID | Slutsats och resultat |
|---|---|
| F-001 Avtalsgrund för trappan | ITP 2026 avdelning 1 punkt 7.1 verifierad; T-001 och PR-001 |
| F-002 Avrundning | Delpremier var för sig, exakta IBB-gränser; uttryckligt eget val, PR-001 |
| F-003 Uttag | 55/66, inget generellt 70-tak; eget månadserbjudande, deluttag, paus och frister i PR-002–007/024–025 |
| F-004 Garanti | B-027 behålls; full SIM-G/B/R, data, svans, beloppsgolv och finansiering i PR-008/009/028 |
| F-005 Dödsfall | Månadsanspråk, dödsbo, avräkning, faktisk pool och sena rättelser i PR-010/011/019/026 |
| F-006 Flera försäkringar | Trappa en gång före proportionell fördelning; centbevarande och primär mottagare, PR-015 |
| F-007 Historik | Årsspecifika värden, bevarad importerad rätt, syntetisk SIM-HIST endast vid uttrycklig omgenerering, PR-032 |
| F-008 Komplettering/netto | Dokumenterad verklig instruktion, ingen universal flexsats; extern nettopremie separat från internt nollavdrag, PR-016/018 |

Slutsatserna är färdiga produktval för dokumentleveransen. Operatörens
sammanhållna införandebeslut, programbygge och externa verksamhetskontroller
är olika nästa aktiviteter och öppnar inte dessa designfrågor på nytt utan skäl.

## Senare ändringar

[Regelförändringsflödet](../../02_system/Agentsystem/regelförändringsflöde.md)
används utan att dess agentgränssnitt byggs om här. Ny källversion får
konsekvensanalys för berörda regler, villkor, historik och kundbesked.
Kod-/testkopplingen läggs till av den session som faktiskt inför beteendet.
