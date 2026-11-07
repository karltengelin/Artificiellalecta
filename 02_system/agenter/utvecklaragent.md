# Utvecklaragent

## Grundinformation

| Fält | Värde |
|------|-------|
| **Funktionsområde** | IT & dataplattform |
| **Team** | Utveckling & plattform (`utveckling`) – se `../agentekosystem.md` §3 (B-026) |
| **Roll i teamet** | Ledande agent (orkestrerare) |
| **Status** | 🟡 Ändringskö och avgränsad kodkörning verifierade med testdubblar i [U3](../../projekt/11_utveckling_och_andringshantering/PROJEKTPLAN.md#prova-u3-i-demo) |
| **Skapad** | 2026-05-15 |

## Mandat

Ansvarar för att ta tilldelade ändringsärenden från undersökning till testad kod
och verifierat införande inom beslutad policy. Ett ärende kan komma från en
människa, ett team, ett driftflöde eller en antagen regel som kräver ny kod.

**Utvecklarroll.** Undersöker kodbasen och beroenden, planerar ändringen och
dokumenterar risker och motåtgärder. Ändrar berörd kod, kör tester, felsöker och
rättar inom uppdragets gränser. Levererar ändring, testbevis och införandeplan.

**Dataplattformsroll.** Hanterar ändringsärenden om datapipelines, datamodeller
och dataintegritet med respektive miljös godkännande och införandekrav.

## Skills

Planerade förmågor är att läsa källkod och tester, arbeta i en isolerad kopia av
repot och använda test- och Git-verktyg inom ärendets mandat. En mänsklig kodare,
Codex eller Claude Code ska kunna arbeta med samma uppdrags- och resultatkontrakt.

## Behörigheter

### Ändringskön (U3)

Vid uttrycklig start får U3-körningen ett mandat från betrodd kod. Agenten
listar nya ärenden inom mandatet och kan ta ett av dem. Samma transaktion
reserverar ärendet för körningen och sätter status *Pågår*. Efter godkända
tester sparar körningen referenser till diff och testbevis och lämnar
ärendet i *Väntar på granskning*. Boarden och detaljen visar ansvarig, status
och den gemensamma historiken. Operatören kan ta över och spärra den tidigare
körningens överlämning.

Den lokala körningen använder fiktivt underlag och en skriptad kodare.
Codex CLI-adaptern är verifierad med en processdubbel. Automatisk bevakning
och villkoren för när kön ska starta en körning behandlas separat.

### Kod och införande

Agenten arbetar med källkod och testdata på egen branch. Den kan committa och
begära push, pull request och merge enligt ärendets mandat. Standard är att en
utsedd granskare godkänner den exakta versionen före införande. Merge till
`main` kräver operatörens uttryckliga godkännande enligt AGENTS.md §4.6.
Ett senare autonomt läge prövas först för förhandsgodkända ändringstyper i en
isolerad testmiljö. Produktionsbehörigheter och releasekontroller hanteras
utanför agentens kodmiljö.

### Agentinteraktioner
- Kan be compliance eller aktuarien precisera förväntad effekt och testfall.
- Kan samarbeta med Data scientist-agenten kring datainfrastruktur.
- Lämnar tillbaka spårbara ändrings- och verifieringsbevis till beställaren.

## Byggplan

[Projekt 11](../../projekt/11_utveckling_och_andringshantering/PROJEKTPLAN.md)
äger ärendets arbetsgång, kontrollkrav, GitHub-koppling och utvecklingsyta.
