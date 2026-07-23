import { useTranslation } from "react-i18next";
import type { Locale } from "@/api/auth";
import { useAuth } from "@/auth/AuthContext";
import { Select } from "@/components/ui/primitives";
import { useTheme, type ThemePreference } from "@/lib/theme";

/** Language selector. Works anonymously (just changes the UI language); when signed in, the
 * change is also persisted to the user's preference via AuthContext.setLocale. */
export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const { setLocale } = useAuth();
  return (
    <Select
      aria-label={t("common.language")}
      value={i18n.resolvedLanguage}
      onChange={(e) => void setLocale(e.target.value as Locale)}
      className="w-auto py-1"
    >
      <option value="en">EN</option>
      <option value="es">ES</option>
    </Select>
  );
}

export function ThemeSwitcher() {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  return (
    <Select
      aria-label={t("common.theme")}
      value={theme}
      onChange={(e) => setTheme(e.target.value as ThemePreference)}
      className="w-auto py-1"
    >
      <option value="light">{t("theme.light")}</option>
      <option value="dark">{t("theme.dark")}</option>
      <option value="system">{t("theme.system")}</option>
    </Select>
  );
}
