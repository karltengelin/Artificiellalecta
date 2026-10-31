# Lokal PDF-läsare

Mozillas PDF.js **6.4.299**, oförändrade webbläsarfiler från `pdfjs-dist`.
Källa: <https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.4.299.tgz>.
Dokumentation: <https://mozilla.github.io/pdf.js/getting_started/>.
Licens: Apache-2.0, se `PDFJS_LICENSE.txt`.

Tar-arkivets npm-integritet (SHA-512, base64), kontrollerad före extraktion:
`AVl138zALtfaAPvADulE0PZThbYzCBS79nL4pOSL/6Sm/4AH5A21BD9VHt97OlCuzJuCpmeZtAtkinisF4Vb1g==`.

| Fil i npm-paketet | Lokal fil | SHA-256 |
|---|---|---|
| `build/pdf.min.mjs` | `pdfjs-6.4.299.min.mjs` | `57456c8e0c81e46be31174b499ef77f2b9f5ee46d04412ba627320a36755d4c2` |
| `build/pdf.worker.min.mjs` | `pdfjs-worker-6.4.299.min.mjs` | `9536359f1b8367850d485731ca1d5e45c159a7b7a0912325e539937aa21ceb18` |

`pdf-preview.mjs` anpassar visningen till bolagets arbetsyta. Modulen läser
bara PDF-leveranser från samma ursprung genom den befintliga leveransrouten.
Rapporten innehåller inbäddade DM Sans-typsnitt; externa font-, CMap- eller
Wasm-resurser ingår inte i denna avgränsade visare. PDF-innehåll får inte
aktivera eval. Bibliotek och worker ska alltid uppdateras tillsammans,
kontrollsummeverifieras och provas i appens webbläsare.
