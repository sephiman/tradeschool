import { describe, expect, it } from "vitest";
import en from "./en.json";
import es from "./es.json";

function keyPaths(obj: unknown, prefix = ""): string[] {
  if (obj === null || typeof obj !== "object") return [prefix];
  return Object.entries(obj as Record<string, unknown>).flatMap(([k, v]) =>
    keyPaths(v, prefix ? `${prefix}.${k}` : k),
  );
}

describe("UI translations", () => {
  it("EN and ES expose the exact same key set", () => {
    const enKeys = keyPaths(en).sort();
    const esKeys = keyPaths(es).sort();
    expect(esKeys).toEqual(enKeys);
  });
});
