# Utvecklaragent

## Grundinformation

| Fält | Värde |
|------|-------|
| **Funktionsområde** | IT & dataplattform |
| **Team** | Utveckling & plattform (`utveckling`) – se `../agentekosystem.md` §3 (B-026) |
| **Roll i teamet** | Ledande agent (orkestrerare) |
| **Status** | 🟡 Planerad i [projekt 11](../../projekt/11_utveckling_och_andringshantering/PROJEKTPLAN.md) |
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

När en U3-körning startas ska agenten via bolagets tjänsteoperationer kunna
lista nya ändringsärenden inom sitt mandat och ta ett av dem. När agenten tar
ärendet ska systemet reservera det för agenten och sätta status *Pågår* i samma
transaktion. När kodändring och testbevis har lämnats kan agenten sätta status
*Väntar på granskning* med referenser till båda underlagen. Boarden visar samma
status, ansvarig och historik som tjänsteoperationerna sparar.

Acceptansen för U3 ska visa att agenten bara kan se och ta behöriga ärenden,
att ett samtidigt anspråk från en människa och en agent ger en ansvarig och
att överlämningen för granskning syns på boarden. Automatisk bevakning av kön
och villkoren för när den startar en körning behandlas separat.

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
