/** Minimal typing for the slice of fontkit the print-font coverage test uses (fontkit ships none). */
declare module "fontkit" {
  export interface Font {
    postscriptName: string;
    hasGlyphForCodePoint(codePoint: number): boolean;
  }
  export function openSync(path: string): Font;
}
