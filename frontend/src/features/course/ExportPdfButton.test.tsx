import { act, type ReactElement } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import en from "@/i18n/en.json";
import type { GenerateProgress } from "@/lib/pdf/generate";

/** What the reader sees while the PDF is being made: a named phase, and a failure that stays on screen. */

const generateCoursePdf = vi.fn<(o: { onProgress?: (p: GenerateProgress) => void }) => Promise<unknown>>();
const downloadPdf = vi.fn();

vi.mock("@/lib/pdf/generate", () => ({
  generateCoursePdf: (o: { onProgress?: (p: GenerateProgress) => void }) => generateCoursePdf(o),
  downloadPdf: (generated: unknown) => downloadPdf(generated),
}));

/** The real EN catalog, interpolated: the test asserts the strings a reader actually sees. */
function translate(key: string, params?: Record<string, unknown>): string {
  const template = key
    .split(".")
    .reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], en);
  if (typeof template !== "string") throw new Error(`missing catalog key ${key}`);
  return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(params?.[name]));
}

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: translate, i18n: { resolvedLanguage: "en" } }),
  initReactI18next: { type: "3rdParty", init: () => {} },
}));

const { ExportPdfButton } = await import("./ExportPdfButton");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const COURSE = { id: "crypto-futures", title: "Crypto Futures, from Zero", description: "From zero." };

let host: HTMLDivElement;

function mount(node: ReactElement): void {
  host = document.createElement("div");
  document.body.appendChild(host);
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  act(() => {
    createRoot(host).render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
  });
}

function button(): HTMLButtonElement {
  const found = host.querySelector("button");
  if (!found) throw new Error("no export button");
  return found as HTMLButtonElement;
}

/** The mutation's state lands over several ticks, not one microtask. */
async function waitUntil(ready: () => boolean, what: string): Promise<void> {
  for (let attempt = 0; attempt < 50; attempt++) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    if (ready()) return;
  }
  throw new Error(`timed out waiting for ${what}`);
}

function alert(): HTMLElement | null {
  return host.querySelector('[role="alert"]');
}

beforeEach(() => {
  generateCoursePdf.mockReset();
  downloadPdf.mockReset();
  document.body.innerHTML = "";
});

describe("the export action", () => {
  it("offers the export, then hands the finished file to the browser", async () => {
    const generated = { blob: new Blob(["%PDF-"]), filename: "tradeschool-crypto-futures-en-2026-08-03.pdf" };
    generateCoursePdf.mockResolvedValue(generated);
    mount(<ExportPdfButton course={COURSE} />);

    expect(button().textContent).toBe(en.course.pdfAction);
    expect(button().disabled).toBe(false);

    await act(async () => {
      button().click();
    });
    await waitUntil(() => downloadPdf.mock.calls.length > 0, "the download");

    expect(downloadPdf).toHaveBeenCalledWith(generated);
    // Back to offering it, not stuck in a spinner.
    expect(button().textContent).toBe(en.course.pdfAction);
    expect(alert()).toBeNull();
  });

  it("says which part of the work is happening while it runs", async () => {
    let report: (p: GenerateProgress) => void = () => {};
    let finish: () => void = () => {};
    generateCoursePdf.mockImplementation(async (o) => {
      report = (p) => o.onProgress?.(p);
      await new Promise<void>((resolve) => {
        finish = resolve;
      });
      return { blob: new Blob([]), filename: "f.pdf" };
    });
    mount(<ExportPdfButton course={COURSE} />);

    await act(async () => {
      button().click();
    });
    await waitUntil(() => button().disabled, "the button to go busy");
    expect(button().getAttribute("aria-busy")).toBe("true");

    await act(async () => {
      report({ phase: "export", done: 0, total: 0 });
    });
    expect(button().textContent).toContain(en.course.pdfPreparing);

    await act(async () => {
      report({ phase: "figures", done: 12, total: 29 });
    });
    expect(button().textContent).toContain("Drawing figures 12/29");

    await act(async () => {
      report({ phase: "typeset", done: 0, total: 0 });
    });
    expect(button().textContent).toContain(en.course.pdfTypesetting);

    await act(async () => {
      finish();
    });
    await waitUntil(() => button().textContent === en.course.pdfAction, "the action to come back");
  });

  it("keeps the failure on the page, naming the reason, and offers a retry", async () => {
    generateCoursePdf.mockRejectedValue(new Error("figure fig-m09-accumulation could not be loaded"));
    mount(<ExportPdfButton course={COURSE} />);

    await act(async () => {
      button().click();
    });
    await waitUntil(() => alert() !== null, "the error state");

    expect(alert()?.textContent).toContain("figure fig-m09-accumulation could not be loaded");
    expect(alert()?.textContent).toContain(en.course.pdfRetry);
    expect(downloadPdf).not.toHaveBeenCalled();

    // Retrying runs it again — this time it works, and the error clears.
    generateCoursePdf.mockResolvedValue({ blob: new Blob([]), filename: "f.pdf" });
    const retry = [...host.querySelectorAll("button")].find(
      (b) => b.textContent === en.course.pdfRetry,
    );
    await act(async () => {
      retry?.click();
    });
    await waitUntil(() => downloadPdf.mock.calls.length > 0, "the retry to succeed");
    expect(downloadPdf).toHaveBeenCalledTimes(1);
    expect(alert()).toBeNull();
  });
});
