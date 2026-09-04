import type { Course, CourseExport } from "@/api/course";

/**
 * The ONE resolution for a lesson cross-reference: what `m22` or `m19-l2` in prose points at.
 *
 * Every surface asks here — the annotator to decide whether a mention is real, the app for the route
 * and the hover title, the golden report for the permanent key — so a mention cannot mean two things
 * on two surfaces. The registry is built from whatever course structure the caller already has (the
 * course payload, the export, the manifest), all of which the backend renders from the id↔key
 * registry; a display renumbering therefore reaches every link by rebuilding this, never by editing
 * a resolver.
 *
 * A module mention resolves the way the app already navigates: a single-lesson module skips its
 * module page (see LessonPage's back link), so its mention goes straight to that lesson.
 */

export type RefKind = "module" | "lesson";

export interface RefTarget {
  kind: RefKind;
  /** The mentioned entity's display id, lowercased (`m22`, `m19-l2`). */
  id: string;
  /** Permanent identity, when the source carries one (the manifest); the id otherwise. */
  key: string;
  /** The mentioned entity's own title — a module mention shows the module's, never a lesson's. */
  title: string;
  /**
   * The mentioned entity's OWN summary: the module's for a module, the lesson's for a lesson.
   *
   * Empty where the source carrying the structure does not carry summaries (the print export, a test
   * fixture); the card then shows the title alone rather than an empty paragraph.
   */
  summary: string;
  /**
   * Which module the target belongs to. A lesson's card says so under its title, because "m19-l2 ·
   * Liquidity maps" means little without "m19 · Derivatives data" above it. A module is its own.
   */
  module: { id: string; title: string };
  /** Course-relative route the app navigates to; print surfaces ignore it. */
  path: string;
}

/** The slice of course structure a registry is built from; `key` only where the source knows it. */
export interface RefModule {
  id: string;
  key?: string;
  title: string;
  summary?: string;
  lessons: { id: string; key?: string; title: string; summary?: string }[];
}

export interface RefRegistry {
  /** The target a mention names, or null for an id-shaped token no entity answers to. */
  resolve(mention: string): RefTarget | null;
}

export function buildRefRegistry(modules: RefModule[]): RefRegistry {
  const targets = new Map<string, RefTarget>();
  for (const module of modules) {
    const only = module.lessons.length === 1 ? module.lessons[0] : null;
    const attribution = { id: module.id, title: module.title };
    targets.set(module.id, {
      kind: "module",
      id: module.id,
      key: module.key ?? module.id,
      title: module.title,
      summary: module.summary ?? "",
      module: attribution,
      path: only ? `/lessons/${only.id}` : `/modules/${module.id}`,
    });
    for (const lesson of module.lessons) {
      targets.set(lesson.id, {
        kind: "lesson",
        id: lesson.id,
        key: lesson.key ?? lesson.id,
        title: lesson.title,
        summary: lesson.summary ?? "",
        module: attribution,
        path: `/lessons/${lesson.id}`,
      });
    }
  }
  return { resolve: (mention) => targets.get(mention.toLowerCase()) ?? null };
}

/** The registry as the running app builds it, from the course payload it already fetched. */
export function refModulesFromCourse(course: Course): RefModule[] {
  return course.blocks.flatMap((block) =>
    block.modules.map((module) => ({
      id: module.id,
      title: module.title,
      summary: module.summary,
      lessons: module.lessons.map((lesson) => ({
        id: lesson.id,
        title: lesson.title,
        summary: lesson.summary,
      })),
    })),
  );
}

/** The registry as the PDF builds it, from the export document it typesets. */
export function refModulesFromExport(doc: CourseExport): RefModule[] {
  return doc.blocks.flatMap((block) =>
    block.modules.map((module) => ({
      id: module.id,
      title: module.title,
      // The print surfaces never open a card, so the export's summaries stay where they are rather
      // than being carried into a registry only the screen reads.
      lessons: module.lessons.map((lesson) => ({ id: lesson.id, title: lesson.title })),
    })),
  );
}
