import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import yaml from "js-yaml";
import type { CourseExport, GlossaryEntry } from "@/api/course";
import type { CapturedFigure } from "@/lib/pdf/document";
import { FONT_DIR, PRINT_FONT_FILES } from "@/lib/pdf/fonts";
import { testPng } from "@/test/png";

/**
 * The REAL course, read straight off `content/`, so the completeness tests cannot drift from it: no
 * counts and no id literals, like the backend's export test.
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

/** The content tree, for the fixtures that read more of it than this module does. */
export const CONTENT_DIR = CONTENT;

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
  /** Permanent identity (defaults to the id at creation); seeds and stored progress hang off it. */
  key?: string;
  type: string;
}

export interface ManifestLesson {
  id: string;
  key?: string;
  title: LocalizedText;
  exercises?: ManifestExercise[];
}

export interface ManifestModule {
  id: string;
  key?: string;
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

/** The permanent key of one exercise (= its id unless the manifest pins an older one). */
export function exerciseKey(exerciseId: string): string {
  const keys = new Map<string, string>();
  for (const lesson of manifestLessons()) {
    for (const ex of lesson.exercises ?? []) keys.set(ex.id, ex.key ?? ex.id);
  }
  return keys.get(exerciseId) ?? exerciseId;
}

/**
 * The course as `/course/export?lang=…` serves it, but with the markdown deliberately RAW where the real
 * endpoint pre-strips it — so "no exercise reached the PDF" holds even with the upstream stripping gone.
 */
/**
 * The real `glossary.yaml`, shaped as the export serves it, so the PDF tests print the real terms.
 *
 * Lesson refs in the yaml (`origin`, `link_except`) are permanent lesson KEYS; the API renders them
 * as display ids, and `space: "display"` mirrors that. The link-report golden runs in `"key"` space
 * so a display renumbering cannot move its lesson axis.
 */
export function glossaryFromContent(locale: Locale, space: "display" | "key" = "display"): GlossaryEntry[] {
  const path = resolve(CONTENT, "glossary.yaml");
  if (!existsSync(path)) return [];
  const raw = yaml.load(readFileSync(path, "utf8")) as {
    terms: {
      id: string;
      en: string;
      es: string;
      origin?: string;
      definition?: LocalizedText;
      senses?: { origin: string; definition: LocalizedText }[];
      alias_of?: string;
      link?: boolean | { en?: boolean; es?: boolean };
      match?: { en?: string[]; es?: string[] };
      link_except?: string[] | { en?: string[]; es?: string[] };
    }[];
  };
  /** `link` and `link_except` may be one value for both locales or one per locale, as the loader reads them. */
  const perLocale = <T,>(value: T | { en?: T; es?: T } | undefined, fallback: T): T => {
    if (value === undefined) return fallback;
    if (typeof value === "object" && value !== null && ("en" in value || "es" in value)) {
      return (value as { en?: T; es?: T })[locale] ?? fallback;
    }
    return value as T;
  };
  const byId = new Map(raw.terms.map((term) => [term.id, term]));
  const keyToId = new Map(manifestLessons().map((lesson) => [lesson.key ?? lesson.id, lesson.id]));
  const titles = new Map(manifestLessons().map((lesson) => [lesson.id, lesson.title[locale]]));
  const lessonRef = (key: string): string => (space === "key" ? key : (keyToId.get(key) ?? key));
  const titleOf = (key: string): string | null => titles.get(keyToId.get(key) ?? key) ?? null;
  return raw.terms.map((term) => {
    const target = term.alias_of ? byId.get(term.alias_of) : undefined;
    return {
      id: term.id,
      term: term[locale],
      origin: term.origin ? lessonRef(term.origin) : null,
      originTitle: term.origin ? titleOf(term.origin) : null,
      ...(term.definition ? { definition: term.definition[locale] } : {}),
      ...(term.senses?.length
        ? {
            senses: term.senses.map((sense) => ({
              origin: lessonRef(sense.origin),
              originTitle: titleOf(sense.origin),
              definition: sense.definition[locale],
            })),
          }
        : {}),
      ...(target ? { aliasOf: { id: target.id, term: target[locale] } } : {}),
      // Shaped exactly as `_glossary_entry` emits them: resolved for this locale, and absent where
      // the annotator's default applies.
      ...(perLocale(term.link, true) ? {} : { link: false }),
      ...(term.match?.[locale] ? { match: term.match[locale] } : {}),
      ...((): { linkExcept?: string[] } => {
        const except = perLocale<string[]>(term.link_except, []);
        return except.length ? { linkExcept: except.map(lessonRef) } : {};
      })(),
    };
  });
}

export function courseExportFromContent(locale: Locale): CourseExport {
  return {
    locale,
    glossary: glossaryFromContent(locale),
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

/** Every distinct character in the authored course: both languages, plus manifest and figure specs. */
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
