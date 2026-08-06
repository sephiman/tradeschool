import en from "@/i18n/en.json";
import es from "@/i18n/es.json";
import type { PdfLabels } from "@/lib/pdf/document";
import { pdfLabels, type Translate } from "@/lib/pdf/labels";
import type { Locale } from "@/test/courseContent";

/**
 * The PDF's chrome as a reader actually gets it: the app's own catalogs, through the app's own
 * `pdfLabels`. The tests therefore assert on the printed Spanish and English rather than on stand-in
 * strings — which is what lets the font-coverage test see every character the document can print.
 *
 * A small `t` rather than a real i18next instance: the PDF uses three of its features (interpolation,
 * `count` plurals, `defaultValue`), and those are worth having in-process and synchronous.
 */

const CATALOGS: Record<Locale, Record<string, Record<string, string>>> = {
  en: en as unknown as Record<string, Record<string, string>>,
  es: es as unknown as Record<string, Record<string, string>>,
};

export function translator(locale: Locale): Translate {
  const catalog = CATALOGS[locale];
  return (key, vars) => {
    const [namespace, ...rest] = key.split(".");
    const name = rest.join(".");
    const entries = catalog[namespace] ?? {};
    const count = vars?.count;
    const plural = typeof count === "number" ? (count === 1 ? "_one" : "_other") : "";
    const value = entries[`${name}${plural}`] ?? entries[name];
    if (value === undefined) {
      const fallback = vars?.defaultValue;
      if (typeof fallback === "string") return fallback;
      throw new Error(`no translation for ${key} in ${locale}`);
    }
    return value.replace(/\{\{(\w+)\}\}/g, (_match, variable: string) =>
      String(vars?.[variable] ?? `{{${variable}}}`),
    );
  };
}

export function testPdfLabels(locale: Locale): PdfLabels {
  const t = translator(locale);
  return pdfLabels(
    t,
    t("course.pdfGenerated", { language: t("course.pdfLanguage"), date: "03/08/2026" }),
  );
}
