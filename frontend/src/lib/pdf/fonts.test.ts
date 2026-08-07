// @vitest-environment node
import { describe, expect, it } from "vitest";
import { openSync } from "fontkit";
import en from "@/i18n/en.json";
import es from "@/i18n/es.json";
import { COURSE_AUTHOR } from "@/lib/pdf/document";
import { installPrintFonts, PRINT_FONT_FILES, type PdfMakeLike } from "@/lib/pdf/fonts";
import { contentCharacters, printFontBytes, printFontPaths } from "@/test/courseContent";

/**
 * The print font has to be able to draw the course. A missing glyph is invisible to every other
 * assertion — the PDF renders, the page count is right, the text is "there".
 *
 * If this goes red, the fix is a font that covers the new character, not a character the font covers.
 */

const paths = printFontPaths();

/** The chrome the PDF adds. Comes from the app's catalogs, so `contentCharacters()` cannot see it. */
function pdfChrome(): string {
  const catalogs = [en, es] as unknown as Record<string, Record<string, string>>[];
  const namespaces = ["course", "exercise", "divergence", "chartLabel", "chartMarker", "band", "level"];
  return catalogs
    .flatMap((catalog) =>
      namespaces.flatMap((namespace) => Object.values(catalog[namespace] ?? {})),
    )
    .join("");
}

/** Characters the generators produce that are authored nowhere — a price, a date, an option letter. */
const GENERATED = `0123456789abcdefghijklmnopqrstuvwxyz.,-+/()%×…·—${COURSE_AUTHOR}`;

describe("the print font", () => {
  const required = new Set([...contentCharacters(), ...pdfChrome(), ...GENERATED]);

  it("has something to cover in the first place", () => {
    // Or an empty character set would make the coverage checks below vacuous.
    expect(required.size).toBeGreaterThan(80);
    expect(required.has("→")).toBe(true);
    // The answer key's own punctuation: a price range, a step separator, an anchor dash.
    expect(required.has("…") && required.has("·") && required.has("—")).toBe(true);
  });

  it.each(PRINT_FONT_FILES)("%s draws every character the course uses", (file) => {
    const font = openSync(paths[file]);
    const missing = [...required]
      .map((char) => char.codePointAt(0) as number)
      .filter((codePoint) => codePoint > 31 && !font.hasGlyphForCodePoint(codePoint))
      .map((codePoint) => `U+${codePoint.toString(16).toUpperCase()} ${String.fromCodePoint(codePoint)}`);
    expect(missing, `${file} would print an empty box`).toEqual([]);
  });
});

describe("installing the print font", () => {
  it("registers all four variants against pdfmake's virtual file system", () => {
    const registered: Record<string, unknown>[] = [];
    const pdfMake: PdfMakeLike = {
      addFonts: (fonts) => registered.push(fonts),
      addVirtualFileSystem: (vfs) => registered.push(vfs),
    };
    installPrintFonts(pdfMake, printFontBytes());
    const [vfs, fonts] = registered;
    expect(Object.keys(vfs).sort()).toEqual([...PRINT_FONT_FILES].sort());
    expect(Object.values(fonts)[0]).toMatchObject({
      normal: "LiberationSans-Regular.ttf",
      bold: "LiberationSans-Bold.ttf",
      italics: "LiberationSans-Italic.ttf",
      bolditalics: "LiberationSans-BoldItalic.ttf",
    });
  });

  it("refuses to typeset with a variant missing rather than falling back", () => {
    const bytes = printFontBytes();
    delete bytes["LiberationSans-Italic.ttf"];
    expect(() =>
      installPrintFonts({ addFonts: () => {}, addVirtualFileSystem: () => {} }, bytes),
    ).toThrowError(/LiberationSans-Italic\.ttf was not loaded/);
  });
});
