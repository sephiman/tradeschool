import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemePreference = "light" | "dark" | "oled" | "system";
export type ResolvedTheme = "light" | "dark" | "oled";

const STORAGE_KEY = "theme";

/** OLED keeps the mobile address bar black instead of letting a bright indigo bar sit above a #000 app. */
const BRAND_THEME_COLOR = "#4f46e5";
const OLED_THEME_COLOR = "#000000";

interface ThemeContextValue {
  theme: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStored(): ThemePreference {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "oled" || v === "system") return v;
  } catch {
    /* ignore */
  }
  return "system";
}

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/**
 * The OS can only answer dark or not, so OLED is a choice and never an inference: `prefers-color-scheme`
 * has no pure-black value, and reading system-dark as OLED would opt every dark-mode user in.
 */
function resolve(theme: ThemePreference): ResolvedTheme {
  if (theme === "system") return systemPrefersDark() ? "dark" : "light";
  return theme;
}

/**
 * OLED sets BOTH classes — it is dark plus a delta. Dropping `.dark` would render OLED as *light*
 * everywhere no `oled:` override exists.
 */
function applyToDocument(resolved: ResolvedTheme) {
  document.documentElement.classList.toggle("dark", resolved !== "light");
  document.documentElement.classList.toggle("oled", resolved === "oled");
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", resolved === "oled" ? OLED_THEME_COLOR : BRAND_THEME_COLOR);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(() => readStored());
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => resolve(readStored()));

  useEffect(() => {
    const resolved = resolve(theme);
    setResolvedTheme(resolved);
    applyToDocument(resolved);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  useEffect(() => {
    if (theme !== "system") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      const resolved: ResolvedTheme = mql.matches ? "dark" : "light";
      setResolvedTheme(resolved);
      applyToDocument(resolved);
    };
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [theme]);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolvedTheme, setTheme: setThemeState }),
    [theme, resolvedTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}

/**
 * The palette to draw with: an explicit override wins, otherwise the UI theme.
 *
 * An override also means no `ThemeProvider` is needed — the PDF export's own React root must not write
 * `localStorage` or toggle `<html class="dark">` as a side effect of exporting a file.
 */
export function useResolvedTheme(override?: ResolvedTheme): ResolvedTheme {
  const ctx = useContext(ThemeContext);
  if (override) return override;
  if (!ctx) throw new Error("useResolvedTheme must be used within a ThemeProvider, or given a theme");
  return ctx.resolvedTheme;
}
