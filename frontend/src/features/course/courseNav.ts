import type { Course } from "@/api/course";

/** One lesson flattened into canonical course order, with the context needed for navigation. */
export interface FlatLesson {
  lessonId: string;
  lessonTitle: string;
  moduleId: string;
  moduleTitle: string;
  lessonsTotal: number;
  completed: boolean;
}

/** Every lesson in canonical order (block → module → lesson), across module boundaries. */
export function flattenLessons(course: Course): FlatLesson[] {
  return course.blocks.flatMap((b) =>
    b.modules.flatMap((m) =>
      m.lessons.map((l) => ({
        lessonId: l.id,
        lessonTitle: l.title,
        moduleId: m.id,
        moduleTitle: m.title,
        lessonsTotal: m.lessonsTotal,
        completed: l.completed,
      })),
    ),
  );
}

/** The current lesson and the one after it (null at the end), by canonical order. */
export function currentAndNext(
  flat: FlatLesson[],
  lessonId: string,
): { current: FlatLesson | null; next: FlatLesson | null } {
  const i = flat.findIndex((x) => x.lessonId === lessonId);
  return { current: i >= 0 ? flat[i] : null, next: i >= 0 ? (flat[i + 1] ?? null) : null };
}

/** Where "Continue" resumes: the first not-yet-completed lesson in canonical order (null if done). */
export function resumeTarget(flat: FlatLesson[]): FlatLesson | null {
  return flat.find((l) => !l.completed) ?? null;
}

/** Human label for a nav target. Within the same module → the lesson title; otherwise "M03 · Module". */
export function stepLabel(entry: FlatLesson, fromModuleId?: string): string {
  return fromModuleId && entry.moduleId === fromModuleId
    ? entry.lessonTitle
    : `${entry.moduleId.toUpperCase()} · ${entry.moduleTitle}`;
}
