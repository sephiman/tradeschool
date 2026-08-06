import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider, useResolvedTheme, useTheme, type ResolvedTheme } from "@/lib/theme";

/**
 * Who needs a `ThemeProvider`. The PDF export draws figures in its own root, outside the app tree, so a
 * component that insists on the provider cannot be captured — and the failure is invisible at the call
 * site, because a hook that throws on mount looks like a component that is slow to appear.
 *
 * And what "System" is allowed to mean. `prefers-color-scheme` answers dark or light and has no third
 * value: reading system-dark as OLED would move every dark-mode reader onto a pure-black theme they
 * never chose, which is the one thing the preference must never do.
 */

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function render(node: ReactNode): { host: HTMLDivElement; error: Error | null } {
  const host = document.createElement("div");
  document.body.appendChild(host);
  let error: Error | null = null;
  try {
    act(() => {
      createRoot(host, { onUncaughtError: (e) => (error = e as Error) }).render(node);
    });
  } catch (thrown) {
    error = thrown as Error;
  }
  return { host, error };
}

function Probe({ theme }: { theme?: ResolvedTheme }) {
  return <span data-testid="resolved">{useResolvedTheme(theme)}</span>;
}

describe("resolving the palette to draw with", () => {
  it("takes an explicit theme without any provider at all", () => {
    const { host, error } = render(<Probe theme="light" />);
    expect(error).toBeNull();
    expect(host.textContent).toBe("light");
  });

  it("follows the UI theme when not given one", () => {
    // The provider asks the OS for its preference; jsdom has no `matchMedia`, so: no.
    vi.stubGlobal("matchMedia", (media: string) => ({
      matches: false,
      media,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    const { host, error } = render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    vi.unstubAllGlobals();
    expect(error).toBeNull();
    // "system" resolves light here; what matters is that it came from the provider, not an argument.
    expect(host.textContent).toBe("light");
  });

  it("says so when it has neither", () => {
    const { error } = render(<Probe />);
    expect(error?.message).toMatch(/must be used within a ThemeProvider, or given a theme/);
  });
});

/** `matchMedia` for a jsdom that has none: `dark` decides what the OS is claiming to prefer. */
function stubSystem(dark: boolean) {
  vi.stubGlobal("matchMedia", (media: string) => ({
    matches: dark,
    media,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

/**
 * `localStorage` for a jsdom that has none either — this one runs on `about:blank`, which has no
 * origin to key storage by, so the global is genuinely absent (hence the try/catch around every
 * access in the provider). The map is returned so a test can read back what was written to it.
 */
function stubStorage(initial?: string): Map<string, string> {
  const store = new Map<string, string>();
  if (initial !== undefined) store.set("theme", initial);
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  });
  return store;
}

/** Reads the preference back out of the provider, and lets a test set one. */
function Preference() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  return (
    <button type="button" onClick={() => setTheme("oled")}>
      {theme}/{resolvedTheme}
    </button>
  );
}

describe("choosing a theme", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.className = "";
  });

  // The rule, from both directions: whatever the OS says, "system" has only two answers.
  it.each([
    [true, "dark"],
    [false, "light"],
  ])("resolves system to the OS preference and never to OLED (system-dark=%s)", (osDark, expected) => {
    stubSystem(osDark);
    stubStorage("system");
    const { host } = render(
      <ThemeProvider>
        <Preference />
      </ThemeProvider>,
    );
    expect(host.textContent).toBe(`system/${expected}`);
    expect(document.documentElement.classList.contains("oled")).toBe(false);
  });

  it("only reaches OLED when it is picked, and remembers it", () => {
    stubSystem(true);
    const store = stubStorage();
    const { host } = render(
      <ThemeProvider>
        <Preference />
      </ThemeProvider>,
    );
    expect(host.textContent).toBe("system/dark");

    act(() => {
      host.querySelector("button")!.click();
    });
    expect(host.textContent).toBe("oled/oled");
    // Persisted like any other preference — this is what survives the reload.
    expect(store.get("theme")).toBe("oled");
  });

  // OLED is the dark theme plus a delta, so it must carry BOTH classes: `.dark` alone renders today's
  // dark theme, `.oled` alone would render LIGHT everywhere no override happens to exist.
  it.each([
    ["oled", ["dark", "oled"]],
    ["dark", ["dark"]],
    ["light", []],
  ])("applies %s to the document as %s", (stored, classes) => {
    stubSystem(false);
    stubStorage(stored);
    render(
      <ThemeProvider>
        <Preference />
      </ThemeProvider>,
    );
    expect([...document.documentElement.classList].sort()).toEqual([...classes].sort());
  });
});
