import { act, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider, useResolvedTheme, type ResolvedTheme } from "@/lib/theme";

/**
 * Who needs a `ThemeProvider`. The PDF export draws figures in its own root, outside the app tree, so a
 * component that insists on the provider cannot be captured — and the failure is invisible at the call
 * site, because a hook that throws on mount looks like a component that is slow to appear.
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
