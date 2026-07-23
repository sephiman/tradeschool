import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import es from "./es.json";

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      es: { translation: es },
    },
    fallbackLng: "en",
    supportedLngs: ["en", "es"],
    // Map region variants to the base language (es-ES, es-419 → es); anything non-Spanish → en.
    load: "languageOnly",
    nonExplicitSupportedLngs: true,
    interpolation: { escapeValue: false },
    detection: {
      // Anonymous visitors default to the browser language; a chosen language is remembered.
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
  });

export default i18n;
