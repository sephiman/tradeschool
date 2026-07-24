import { useTranslation } from "react-i18next";
import type { Locale } from "@/api/auth";
import { useAuth } from "@/auth/AuthContext";
import { useTheme, type ThemePreference } from "@/lib/theme";
import { cn } from "@/lib/cn";

/** One control vocabulary shared by the in-app avatar menu and the auth pages. `block` fills the
 * width (menu panel); the default is compact/content-width (auth card top-right). */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  block,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  ariaLabel: string;
  block?: boolean;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn(
        "gap-0.5 rounded-md border border-border p-0.5 dark:border-gray-700",
        block ? "flex w-full" : "inline-flex",
      )}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "rounded px-2 py-1 text-xs font-medium transition-colors",
              block && "flex-1",
              active
                ? "bg-primary text-primary-foreground"
                : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** EN/ES segmented control. Anonymously it just switches the UI language; signed in it also
 * persists the preference (see AuthContext.setLocale). */
export function LanguageControl({ block }: { block?: boolean }) {
  const { t, i18n } = useTranslation();
  const { setLocale } = useAuth();
  const lang: Locale = i18n.resolvedLanguage === "es" ? "es" : "en";
  return (
    <Segmented<Locale>
      ariaLabel={t("common.language")}
      value={lang}
      onChange={(v) => void setLocale(v)}
      block={block}
      options={[
        { value: "en", label: "EN" },
        { value: "es", label: "ES" },
      ]}
    />
  );
}

/** Claro/Oscuro/Sistema segmented control. */
export function ThemeControl({ block }: { block?: boolean }) {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  return (
    <Segmented<ThemePreference>
      ariaLabel={t("common.theme")}
      value={theme}
      onChange={setTheme}
      block={block}
      options={[
        { value: "light", label: t("theme.light") },
        { value: "dark", label: t("theme.dark") },
        { value: "system", label: t("theme.system") },
      ]}
    />
  );
}

const THEME_ORDER: ThemePreference[] = ["light", "dark", "system"];

function ThemeIcon({ theme }: { theme: ThemePreference }) {
  const common = {
    width: 15,
    height: 15,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (theme === "light") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    );
  }
  if (theme === "dark") {
    return (
      <svg {...common}>
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <rect x="2" y="4" width="20" height="13" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}

/** Compact theme control that cycles light → dark → system. Used where a three-option segmented
 * control would be too wide (the auth-card footer on phone widths). */
export function ThemeCycleButton() {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const next = THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length];
  return (
    <button
      type="button"
      aria-label={t("common.theme")}
      title={t(`theme.${theme}`)}
      onClick={() => setTheme(next)}
      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
    >
      <ThemeIcon theme={theme} />
    </button>
  );
}
