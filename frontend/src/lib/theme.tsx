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
 * The OS is asked one question — dark or not — and it can only ever answer with one of those two.
 *
 * OLED is a choice, never an inference: `prefers-color-scheme` has no pure-black value to report, so
 * reading system-dark as OLED would put every dark-mode user on a theme they never asked for. It is
 * reachable only by picking it, which is also why it survives a reload — it is stored like any other
 * preference, not re-derived.
 */
function resolve(theme: ThemePreference): ResolvedTheme {
  if (theme === "system") return systemPrefersDark() ? "dark" : "light";
  return theme;
}

/**
 * OLED sets BOTH classes. It is the dark theme plus a delta (see the `oled` variant in index.css):
 * `.dark` keeps every existing dark utility applying, and `.oled` switches on the handful that pure
 * black needs. Dropping `.dark` here would leave OLED rendering as *light* everywhere no `oled:`
 * override happens to exist.
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
 * An override also means "no `ThemeProvider` needed", which is the point: the PDF export draws figures in
 * its own React root outside the app tree, and mounting a second provider there would write `localStorage`
 * and toggle `<html class="dark">` as a side effect of exporting a file.
 */
export function useResolvedTheme(override?: ResolvedTheme): ResolvedTheme {
  const ctx = useContext(ThemeContext);
  if (override) return override;
  if (!ctx) throw new Error("useResolvedTheme must be used within a ThemeProvider, or given a theme");
  return ctx.resolvedTheme;
}
