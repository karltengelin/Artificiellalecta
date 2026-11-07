# U6 – Första sandlådepolicy

**Policy-ID och version** `u6-quote-discount/v1`

**Beslutsstatus** Operatören valde denna version för det lokala sandlådeprovet
i chatten 2026-11-07. Granskat läge är standard i den ordinarie utvecklingsytan.

## Tillåten ändring

Rätta rabattberäkningen i U3:s fiktiva offert. Startaren skapar det
syntetiska felärendet, en isolerad Git-kopia med enbart `quote.sql` och en
separat demofil med U5:s två lokala testdubblar. Startaren binder operatör,
ärende-ID, utvecklarkörning, policyversion, bascommit och sandlådeinstans.
Den bindningen kommer från den betrodda startaren. Ärendetext, en etikett och
kodarens förslag ger i sig inget sådant mandat. Valet gäller ett ärende i ett
uttryckligt startat prov.

| Kontroll | Tillåtet i version 1 |
|---|---|
| Filträd | Exakt en vanlig fil med Git-läge `100644`, `quote.sql`, i båda träden |
| Före | Exakt `SELECT :price + :discount;` följt av LF |
| Efter | Exakt `SELECT :price - :discount;` följt av LF |
| Historik | En ändringscommit med den startbundna bascommitten som enda förälder |
| Merge och mål | U5:s simulerade repo `demo/artificiellalecta` och dess simulerade `main` i provets egen `.delivery.db`. Målmiljön är `demo/<ärende-id>` i samma isolerade testdubbel |
| Obligatoriskt `kodprov` | Betrodd SQLite-kontroll på den committade källan. Pris 1 000 med rabatt 200 ska ge 800. Pris 1 700 med rabatt 0 ska ge 1 700. Båda måste passera |

Filträd, Git-läge och exakta bytes stänger även för extra filer, namnbyten,
symlänkar, ändrade tester och dolda ändringar i SQL-filen. Policyn tillåter
bara startarens syntetiska felärende. Ärenden om ändrad pensionslogik och
regelbeställningar från U4 går till oberoende mänsklig granskning även om
en föreslagen ändring eller ett testbevis råkar matcha offertprovet.

## Betrodd prövning och verkställighet efter beslut

1. Pröva U5:s behörighet inom samma ärende och aktiva `ChangeQueueRun`.
   Läs operatörens val och den utfärdade bindningen från den betrodda sidan.
   Kontrollera den faktiska instansen av testdubblarna och den avsedda
   målmiljön. En sträng som säger `demo` är otillräcklig som miljöbevis.
2. Läs bas, aktuell head, föräldrar, fullständiga träd, blobbar och faktisk
   diff från den isolerade Git-kopian. Använd den exakta committen som
   testindata. Den betrodda sidan håller Git-objekt och provbevis utanför
   kodarens skrivyta. Läs in eller kör om det fasta `kodprov` som ägs av betrodd
   kod utanför kandidatens träd. Bind utfallet och testreferensen till
   ärendet, körningen, bas, head och diff. Jämför med den aktuella
   granskningsinlämningen och PR-kandidaten i U5.
3. Spara ett eget policybeslut med policyversion, mandatbindning,
   granskningsinlämning, fullständig kandidat och mål. Beslutet ska gå att
   skilja från ett mänskligt godkännande. Använd beslutets ID med U5:s
   försöksnyckel per steg. Dubbla anrop med samma nyckel återfår samma
   kvitto. Kontrollera samma kandidat vid verkställighet.
   U5:s testdubbel jämför kandidat och bevis under sitt skrivlås. Första
   provet automatiserar enbart kodgodkännandet. Operatören begär införande
   och verifiering. Mergekvitto, införandekvitto och kontroll av observerad
   version och hälsa ligger kvar som tre separata bevis.
4. Vid saknat mandat, avvikande diff, ändrad commit, miljö eller testbevis
   går ärendet via **Väntar på granskning**. Spara orsaken på ärendet.
   Om ett försök redan är påbörjat använder betrodd kod först U5:s
   avstämning med samma försöksnyckel. Matchande kvitto slutför det gamla
   steget. Bekräftat utebliven effekt med ändrat underlag kräver mänsklig
   granskning. Vid okänt utfall väntar ärendet på avstämning och gör inget
   nytt muterande anrop. Efter övertagande kan operatören stämma av det
   redan påbörjade försöket. Ett nytt försök kräver gällande mandat.

## Kör det uttryckliga sandlådeprovet

Starta från reporoten. Katalogen för `start` ska vara ny och dess förälder
ska finnas. Startaren använder en skriptad kodare och U5:s lokala SQLite-
testdubblar. Den stannar efter den simulerade mergen. Operatören kör sedan
`deploy` och `verify` som separata kommandon om införandekedjan ska provas.

```powershell
python scripts/demo/run_sandbox_policy.py --directory tmp/u6-offert start --policy u6-quote-discount/v1 --operator-id karl
python scripts/demo/run_sandbox_policy.py --directory tmp/u6-offert status
python scripts/demo/run_sandbox_policy.py --directory tmp/u6-offert deploy
python scripts/demo/run_sandbox_policy.py --directory tmp/u6-offert verify
```

`status` visar policybeslut, granskningsunderlag eller avslag samt skilda
kvitton. Kör `merge` för att stämma av ett avbrutet mergeförsök från samma
katalog. Vid avslag visar `status` skälet och eventuellt underlag för U5:s
mänskliga väg. Efter granskning kan operatören använda `review --seen`
med underlagets fingeravtryck och därefter `merge`.

Startaren lagrar mandatet i `sandbox.json`, den arkiverade Git-kopian i
`source.git`, provbevis i `runs/` och ärendets beslut i `case.db`.
Testdubblarnas kvitton ligger i `case.delivery.db`. De lokala proven täcker
nekat mandat, ändrad diff, commit och testbevis, regelärenden, dubbelanrop
och avstämning efter avbrott. Införande och hälsokontroll provas separat.

Valet av denna policy gäller ett lokalt sandlådeprov. Verkliga
skrivanslutningar, ändrad mergepolicy och integration av U6 till
Artificiellalectas `main` kräver varsitt beslut.
