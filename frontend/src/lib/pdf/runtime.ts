import type { TCreatedPdf, TDocumentDefinitions } from "pdfmake/interfaces";
import { PRINT_FONT_URLS } from "@/lib/pdf/fontAssets";
import { installPrintFonts, loadPrintFontBytes } from "@/lib/pdf/fonts";

/** The slice of pdfmake the export uses. */
export interface PdfMakeRuntime {
  createPdf: (definition: TDocumentDefinitions) => TCreatedPdf;
  addFonts: (fonts: Record<string, Record<string, string>>) => void;
  addVirtualFileSystem: (vfs: Record<string, string>) => void;
}

let runtime: Promise<PdfMakeRuntime> | null = null;

/** The prebuilt browser bundle is imported dynamically, so a reader who never exports never downloads
 *  a megabyte of typesetting engine. Loaded once per session, with its font. */
export function loadPdfMake(): Promise<PdfMakeRuntime> {
  runtime ??= (async () => {
    const loaded = (await import("pdfmake/build/pdfmake")) as unknown as {
      default?: PdfMakeRuntime;
    } & PdfMakeRuntime;
    // A UMD bundle arrives as a namespace or a default, depending on the bundler's interop.
    const pdfMake = loaded.default ?? loaded;
    installPrintFonts(pdfMake, await loadPrintFontBytes(PRINT_FONT_URLS));
    return pdfMake;
  })();
  return runtime;
}
