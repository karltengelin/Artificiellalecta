---
title: "Välkommen till Artificiellalecta"
period: "Läget 2026-10-31"
date: "2026-10-31"
version: "1.0"
author: "Artificiellalecta"
source: "MASTER_CONTEXT, BESLUTSLOGG, ATT_GORA och agentkartan per 2026-10-31."
---

<!-- slide: titel | title | Välkommen till Artificiellalecta -->
En introduktion för nya medarbetare.

Ett simulerat, AI-native tjänstepensionsbolag för ålderspension ITP1: principer, avgränsningar, organisation och läget i dag.

<!-- slide: bolaget | content | Ett riktigt bolag – i simulering -->
**Slutsats:** Agentteam gör det arbete som avdelningarna i ett riktigt bolag skulle göra.

- **En produkt:** ålderspension inom kollektivavtalet ITP1.
- **En operatör:** en människa driver bolaget med stöd av AI-agenter.
- **En sandlåda:** inga riktiga kunder, data eller kapital.

> MASTER_CONTEXT §1. B-002, B-003, B-037.

<!-- slide: avgransning | table | Smalt med flit: en produkt, ett avtal -->
| Ingår | Ingår inte |
| --- | --- |
| Ålderspension ITP1, premiebestämd | Sjukpension, familjepension och ITPK |
| Traditionell försäkring med garanti | Andra kollektivavtal |
| Regler för hela livscykeln | Direktpension och individuella lösningar |
| Kapitalförvaltning som paper trading | Riktiga kunder, data och kapital |

> MASTER_CONTEXT §2. B-019, B-027, B-031.

<!-- slide: siffror | kpis | Bolaget i tre tal -->
| Mått | Värde | Kommentar |
| --- | --- | --- |
| Delprojekt | 10 | Från ärenden till central |
| Agentteam | 7 | En ledande agent per team |
| Körbara roller | 3 av 10 | Övriga är beskrivna |

> MASTER_CONTEXT §4b och agentkartan.

<!-- slide: principer-styrning | content | Människan har alltid sista ordet -->
- **Människa i loopen:** allt externt godkänns först.
- **En väg in:** alla ändrar via tjänstelagret.
- **Människan kan allt** som en agent kan.

> MASTER_CONTEXT §3.5, §3.7 och §3.8. B-017, B-028.

<!-- slide: principer-bygge | content | Byggt för att kunna förändras -->
- **Skills före nya agenter.**
- **Modellagnostiskt:** AI via eget lager.
- **Markdown först;** PDF vid behov.

> MASTER_CONTEXT §3.1, §3.2 och §3.6. B-008, B-012, B-025.

<!-- slide: mandat | table | Agenter förbereder – människan beslutar -->
| Klass | Exempel | Hantering |
| --- | --- | --- |
| Läsa | Kunddata, regelverk | Direkt, journalförs |
| Beräkna | Premier, aggregat | Direkt, journalförs |
| Skriva | Ärenden, utkast | Journalförs; ibland godkännande |
| Externt | Utskick, transaktion | Aldrig direkt; godkännandekö |

> Agentekosystem §5.3. Vissa operationer är endast för handläggare.

<!-- slide: lager | content | Varje regel kan spåras till källan -->
- **1. Regelverkskällor:** lagar, föreskrifter, avtal.
- **2. Tolkningar:** vad reglerna betyder för oss.
- **3. Styrdokument:** det vi själva har bestämt.
- **4. Operativt arbete:** med spår till regeln.

> B-010. Ändrad regel: compliance tolkar, aktuarien räknar, operatören godkänner.

<!-- slide: team-byggda | table | Tre av sju team har körbara agenter -->
| Team | Ledande agent | Läge i dag |
| --- | --- | --- |
| Försäkring och kund | Handläggaragent | Byggd för löneunderlag |
| Aktuarie och analys | Aktuarieagent | Profil byggd |
| Compliance | Compliance-agent | Profil byggd |

> Varje team har en ledande agent som orkestrerar. Agentkarta §1. B-026.

<!-- slide: team-planerade | table | Fyra team är beskrivna men inte byggda -->
| Team | Ledande agent | Ansvar |
| --- | --- | --- |
| Kommunikation | Kommunikationsagent | Alla utgående kanaler |
| Kapitalförvaltning | Portföljagent | Placeringar |
| Ekonomi och inköp | Ekonomiagent | Bokföring och avtal |
| Utveckling | Utvecklaragent | Kod och data |

> Agentekosystem §3.3. Internrevision saknar ännu team.

<!-- slide: arbetsflode | content | Från uppdrag till godkänd leverans -->
- **Operatören** startar uppdraget.
- **Centralen** når rätt teams ledande agent.
- **Agenten** arbetar via tjänstelagret.
- **Godkännandekön** väntar på en människa.

> Ingen VD-agent. Eskalering till compliance är alltid tillåten. B-028, B-036.

<!-- slide: byggstatus | table | Det här finns – och det här återstår -->
| Byggt och testat lokalt | Återstår |
| --- | --- |
| Handläggar-UI och tjänstelager | Handel i kapitalförvaltningen |
| Handläggaragent för löneunderlag | Reserv-, ALM- och FTA-motorer |
| Produktregler och regeländring | Hela premie- och betalningsflödet |
| Centralen med Fråga bolaget | Kundportal och internrevision |

> En beskriven roll, en körbar profil och en verifierad förmåga är olika saker.

<!-- slide: narmast | content | Närmast: från fråga till rapport -->
**Slutsats:** En byggleverans i taget, styrd av verksamhetens behov.

- **Närmast:** fråge- och rapportkedjan.
- **Kommande:** premie och betalning.
- **Förberedelse:** första FTA-leveransen.

> ATT_GORA hög prioritet. B-037, B-041.

<!-- slide: arbetssatt | content | Så jobbar vi i vardagen -->
- **Beslut har nummer** i BESLUTSLOGG.
- **En branch per uppgift** och verktyg.
- **Merge till main** efter uttryckligt OK.
- **Rätta överallt** i samma commit.
- **Inga hemligheter** i Git.

> CLAUDE.md §3 och AGENTS.md §4. B-023.

<!-- slide: kom-igang | content | Din första vecka -->
- **Läs grunden:** MASTER_CONTEXT först.
- **Se helheten:** företagsöversikten.
- **Prova systemet** med övningsdata.
- **Fråga hellre än gissa.**

> Handläggar-UI med övningsdata: python scripts/web/start_ui.py
