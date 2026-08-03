// @vitest-environment node
import { describe, expect, it } from "vitest";
import { openSync } from "fontkit";
import en from "@/i18n/en.json";
import es from "@/i18n/es.json";
import { installPrintFonts, PRINT_FONT_FILES, type PdfMakeLike } from "@/lib/pdf/fonts";
import { contentCharacters, printFontBytes, printFontPaths } from "@/test/courseContent";

/**
 * The print font has to be able to draw the course. pdfmake's bundled Roboto has no `→`, which the prose
 * uses in over a hundred places, where it printed as an empty box — and a missing glyph is invisible to
 * every other assertion here: the PDF renders, the page count is right, the text is "there".
 *
 * If this goes red, the fix is a font that covers the new character, not a character the font covers.
 */

const paths = printFontPaths();

/** The chrome the PDF adds: table of contents, cover line, page numbers. */
function pdfChrome(): string {
  const catalogs = [en.course, es.course] as unknown as Record<string, string>[];
  return catalogs
    .flatMap((course) =>
      Object.entries(course)
        .filter(([key]) => key.startsWith("pdf"))
        .map(([, value]) => value),
    )
    .join("");
}

describe("the print font", () => {
  const required = new Set([...contentCharacters(), ...pdfChrome()]);

  it("has something to cover in the first place", () => {
    // Or an empty character set would make the coverage checks below vacuous.
    expect(required.size).toBeGreaterThan(80);
    expect(required.has("→")).toBe(true);
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
