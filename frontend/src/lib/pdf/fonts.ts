import { PRINT_FONTS } from "@/lib/pdf/document";
import { PRINT_FONT } from "@/lib/pdf/page";

/**
 * The embedded print face, installed into pdfmake's virtual file system.
 *
 * Not pdfmake's bundled Roboto: it has no U+2192, and `→` appears in the prose over a hundred times,
 * printing as an empty box. `fonts.test.ts` asserts Liberation Sans covers every character used.
 */

export type PdfMakeLike = {
  addFonts: (fonts: Record<string, Record<string, string>>) => void;
  addVirtualFileSystem: (vfs: Record<string, string>) => void;
};

export const PRINT_FONT_FILES: string[] = Object.values(PRINT_FONTS[PRINT_FONT]);

/** Where the .ttf files live relative to `src/`: shared by the browser loader and the tests. */
export const FONT_DIR = "assets/fonts/liberation-sans";

/** `bytes` maps each file in `PRINT_FONT_FILES` to its base64 contents. */
export function installPrintFonts(pdfMake: PdfMakeLike, bytes: Record<string, string>): void {
  for (const file of PRINT_FONT_FILES) {
    if (!bytes[file]) throw new Error(`print font ${file} was not loaded`);
  }
  pdfMake.addVirtualFileSystem(bytes);
  pdfMake.addFonts(PRINT_FONTS as unknown as Record<string, Record<string, string>>);
}

function toBase64(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes);
  let binary = "";
  // Chunked: one spread of a 400 kB array blows the argument limit.
  for (let i = 0; i < view.length; i += 8192) {
    binary += String.fromCharCode(...view.subarray(i, i + 8192));
  }
  return btoa(binary);
}

/** Fetch the assets Vite emitted, once per session: the four files are ~1.6 MB. */
let cached: Promise<Record<string, string>> | null = null;

export function loadPrintFontBytes(urls: Record<string, string>): Promise<Record<string, string>> {
  cached ??= (async () => {
    const entries = await Promise.all(
      PRINT_FONT_FILES.map(async (file) => {
        const url = urls[file];
        if (!url) throw new Error(`no asset url for print font ${file}`);
        const response = await fetch(url);
        if (!response.ok) throw new Error(`print font ${file} failed to load (${response.status})`);
        return [file, toBase64(await response.arrayBuffer())] as const;
      }),
    );
    return Object.fromEntries(entries);
  })();
  return cached;
}
