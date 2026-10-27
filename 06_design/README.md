# Digital klarhet – bolagets designspråk

**Version:** 1.0 | **Beslutat:** 2026-10-24 | **Beslut:** B-034

Digital klarhet är Artificiellalectas gemensamma grafiska riktning för hemsidor,
kundportal, handläggargränssnitt, rapporter, dokumentation och presentationer.
Operatören valde denna riktning efter att ha jämfört fyra grafiska förslag.

Uttrycket bygger på **indigo, ljusa ytor, tydlig typografi och mjukare former**.
Det ska kännas modernt, professionellt och lugnt, med informationen i centrum.

- [Designspecifikation v1.0](designsprak.md) – regler för människor och agenter.
- [Visuell referens](digital_klarhet.html) – det valda förslaget med rapport, slide och handläggarvy; öppnas i webbläsare.
- [Gemensamma designvärden](../src/design/digital_clarity.tokens.json) – färger, typografi, avstånd och former för kommande implementationer.
- [Beslutslogg](../BESLUTSLOGG.md) – B-034 fastställer valet.
- [Införandeplan](../ATT_GORA.md) – se Grafisk identitet och designsystem.
- [Utförlig exempelrapport om agentnyttjande](exempel/README.md) – PDF och Markdown med fiktiva analyser, diagram och tabeller i Digital klarhet.
- [Återanvändbar rapportmall](rapportmall.md) – A4-komponenter för sidhuvud, rubriker, nyckeltal, tabeller och vektordiagram; används av exempelrapporten.
- [Återanvändbar presentationsmall](presentationsmall.md) – lokal Markdown → PDF i 16:9 med titelbild, innehåll, nyckeltal, tabell och diagram; syntetiskt exempel och tester.
- [Första skiss av operatörscentralen](../projekt/10_operatörscentral/SKISS.md) – planerad VD-arbetsyta med syntetiska exempel, inte en driftsatt vy.

Designspecifikationen är den normativa beskrivningen. Tokenfilen är den gemensamma
källan till de maskinläsbara grundvärdena. Den visuella referensen är en bevarad
ögonblicksbild av det valda förslaget, med exempeldata och skisser av komponenter.
Den är inte en kopia av dagens handläggar-UI eller en färdig rapport-/PPTX-mall.

Designgrunden är dokumenterad och tillämpad i handläggar-UI:t, som är pilotytan
(2026-10-24). Webbens CSS-variabler genereras där ur tokenfilen, se
`02_system/handläggar-ui.md` §2. Återanvändbara mallar för A4-rapport och
16:9-presentation finns. Införande i övriga ytor, övriga dokumentmallar samt de
gemensamma genereringsskillsen återstår enligt backloggen.
