import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import yaml from "js-yaml";
import type { CourseExport } from "@/api/course";
import type { CapturedFigure } from "@/lib/pdf/document";
import { FONT_DIR, PRINT_FONT_FILES } from "@/lib/pdf/fonts";
import { testPng } from "@/test/png";

/**
 * The REAL course, read straight off `content/`, so the export's completeness tests cannot drift from it:
 * driven off the manifest, no counts and no id literals, like the backend's export test. A block appended
 * tomorrow is covered the moment it is declared.
 */

/** Found by walking up, so the tests work from `frontend/` or from the repo root. */
function findContentDir(): string {
  let dir = process.cwd();
  for (let up = 0; up < 6; up++) {
    const candidate = resolve(dir, "content");
    if (existsSync(resolve(candidate, "course.yaml"))) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(`content/course.yaml not found above ${process.cwd()}`);
}

const CONTENT = `${findContentDir()}/`;

/** The print font as absolute paths, by pdfmake vfs file name. */
export function printFontPaths(): Record<string, string> {
  const dir = resolve(CONTENT, "..", "frontend", "src", FONT_DIR);
  return Object.fromEntries(PRINT_FONT_FILES.map((file) => [file, resolve(dir, file)]));
}

/** The same font as base64 bytes — the shape the browser hands pdfmake through its vfs. */
export function printFontBytes(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(printFontPaths()).map(([file, path]) => [
      file,
      readFileSync(path).toString("base64"),
    ]),
  );
}

export interface LocalizedText {
  en: string;
  es: string;
}

export interface ManifestExercise {
  id: string;
  type: string;
}

export interface ManifestLesson {
  id: string;
  title: LocalizedText;
  exercises?: ManifestExercise[];
}

export interface ManifestModule {
  id: string;
  title: LocalizedText;
  summary: LocalizedText;
  lessons?: ManifestLesson[];
}

export interface ManifestBlock {
  id: string;
  title: LocalizedText;
  modules: ManifestModule[];
}

export interface Manifest {
  course: { id: string; title: LocalizedText; description: LocalizedText };
  blocks: ManifestBlock[];
}

export type Locale = keyof LocalizedText;

export const LOCALES: Locale[] = ["en", "es"];

let manifest: Manifest | null = null;

export function readManifest(): Manifest {
  manifest ??= yaml.load(readFileSync(`${CONTENT}course.yaml`, "utf8")) as Manifest;
  return manifest;
}

export function lessonMarkdown(locale: Locale, lessonId: string): string {
  return readFileSync(`${CONTENT}${locale}/lessons/${lessonId}.md`, "utf8");
}

export function manifestModules(): ManifestModule[] {
  return readManifest().blocks.flatMap((block) => block.modules);
}

export function manifestLessons(): ManifestLesson[] {
  return manifestModules().flatMap((module) => module.lessons ?? []);
}

export function manifestExerciseIds(): string[] {
  return manifestLessons().flatMap((lesson) => (lesson.exercises ?? []).map((ex) => ex.id));
}

/**
 * The course as `/course/export?lang=…` serves it, built from the manifest and the lesson files — with the
 * markdown deliberately RAW, exercise directives and all, where the real endpoint hands over prose already
 * stripped. That makes every "no exercise reached the PDF" assertion stronger than production: it holds
 * even with the upstream stripping gone, because the print renderer has no rule for one.
 */
export function courseExportFromContent(locale: Locale): CourseExport {
  return {
    locale,
    blocks: readManifest().blocks.map((block) => ({
      id: block.id,
      title: block.title[locale],
      modules: block.modules.map((module) => ({
        id: module.id,
        title: module.title[locale],
        summary: module.summary[locale],
        lessons: (module.lessons ?? []).map((lesson) => ({
          id: lesson.id,
          title: lesson.title[locale],
          markdown: lessonMarkdown(locale, lesson.id),
        })),
      })),
    })),
  };
}

/** Every distinct character in the authored course: prose in both languages, plus the manifest and figure
 *  specs, which is where titles, summaries and captions come from. */
export function contentCharacters(): Set<string> {
  const chars = new Set<string>();
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = resolve(dir, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (/\.(md|yaml)$/.test(entry.name)) {
        for (const char of readFileSync(path, "utf8")) chars.add(char);
      }
    }
  };
  walk(CONTENT);
  return chars;
}

/** Every `::figure{id=…}` occurrence across the course, in reading order (repeats kept). */
export function figureDirectives(locale: Locale): string[] {
  return manifestLessons().flatMap((lesson) =>
    [...lessonMarkdown(locale, lesson.id).matchAll(/^::figure\{id=([^}\s]+)[^}]*\}\s*$/gm)].map(
      (match) => match[1],
    ),
  );
}

/** A stand-in bitmap the size a real capture produces (760×300 CSS px at the print scale). */
const STUB_PNG = testPng(1520, 600);

/** One rendered panel per figure, captioned by id. */
export function stubFigures(ids: string[], panelsPerFigure = 1): Map<string, CapturedFigure> {
  const captured = new Map<string, CapturedFigure>();
  for (const id of new Set(ids)) {
    captured.set(id, {
      id,
      caption: `caption for ${id}`,
      panels: Array.from({ length: panelsPerFigure }, () => STUB_PNG),
    });
  }
  return captured;
}
