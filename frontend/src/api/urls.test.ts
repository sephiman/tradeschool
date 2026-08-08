import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { COURSE_PATH, COURSE_SLUG } from "@/api/client";

/**
 * Aliases are for clients we do not control. Ours use the canonical course-scoped URLs, and this is
 * the grep-level gate that keeps it that way — the backend's `test_course_scoped_urls.py` is the
 * other half.
 */

const API_DIR = resolve(__dirname);
/** Endpoints that are genuinely global: an account is not per-course, dev tooling is not a surface. */
const GLOBAL = ["/auth", "/dev"];
/** First segment of every course-owned endpoint, as the router mounts them. */
/** An actual request — `apiClient.interceptors.…` is configuration, not a call. */
const HTTP_CALL = /apiClient\.(get|post|put|patch|delete)[<(]/;
const COURSE_OWNED =
  /["`]\/(course|courses|lessons|modules|figures|glossary|exams|stats|attempts|exercises|export|print)\b/;

function apiSources(): { file: string; body: string }[] {
  return readdirSync(API_DIR)
    .filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts"))
    .map((f) => ({ file: f, body: readFileSync(resolve(API_DIR, f), "utf8") }));
}

describe("internal callers use the canonical scoped URLs", () => {
  it("the slug is the manifest's permanent course id", () => {
    expect(COURSE_SLUG).toBe("crypto-futures");
    expect(COURSE_PATH).toBe("/courses/crypto-futures");
  });

  it("no api module calls a course-owned endpoint on its unscoped alias", () => {
    const offenders: string[] = [];
    for (const { file, body } of apiSources()) {
      for (const line of body.split("\n")) {
        if (!HTTP_CALL.test(line)) continue;
        if (GLOBAL.some((g) => line.includes(g))) continue;
        // A course-owned URL must be built from COURSE_PATH, never written as a bare path.
        if (COURSE_OWNED.test(line) && !line.includes("COURSE_PATH")) {
          offenders.push(`${file}: ${line.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("every course-owned call is built from the one constant", () => {
    const calls = apiSources()
      .flatMap(({ body }) => body.split("\n"))
      .filter((l) => HTTP_CALL.test(l))
      .filter((l) => !GLOBAL.some((g) => l.includes(g)));
    expect(calls.length).toBeGreaterThan(15);
    expect(calls.every((l) => l.includes("COURSE_PATH"))).toBe(true);
  });
});
