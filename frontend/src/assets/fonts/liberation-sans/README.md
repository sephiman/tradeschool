<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Liberation Sans — the print face for the course PDF

Four unmodified TrueType files (Regular, Bold, Italic, BoldItalic) plus the upstream `LICENSE`
(SIL Open Font License 1.1). Not used anywhere on screen: the app's stack stays
`system-ui, …, Helvetica, Arial`.

**Why a font is committed at all.** A PDF has to carry its own type — the reader's system fonts are not
in the file. The obvious candidate, the Roboto pdfmake bundles, has **no `U+2192`**, and `→` appears in
the lesson prose over a hundred times, where it printed as an empty box. Liberation Sans is
metric-compatible with Helvetica/Arial, so the printed page stays close to the app's feel, and it covers
everything the course uses.

**Why unmodified.** Subsetting would shrink these files considerably, but the OFL reserves the name
"Liberation" for the unmodified font, and a subset would have to be regenerated (and renamed) every time
a lesson introduced a character it did not carry. Shipping the whole face keeps the licence simple and
the content free to use any glyph the font has.

Registered in `frontend/src/lib/pdf/fonts.ts` (`installPrintFonts`) and mapped to pdfmake's four style
slots in `frontend/src/lib/pdf/document.ts` (`PRINT_FONTS`). `frontend/src/lib/pdf/fonts.test.ts` asserts
these files cover **every character in `content/`** — if that test goes red, the fix is a font that covers
the new character, not a character the font covers.
