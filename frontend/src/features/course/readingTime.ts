import type { Course, CourseBlock, CourseModule } from "@/api/course";

/**
 * Reading-time aggregation for every level of the course.
 *
 * Seconds are the only source of truth: every aggregate is a SUM of per-lesson seconds rounded exactly
 * once, here, because summing already-rounded minutes drifts. Every level goes through these same two
 * functions, so a course total cannot disagree with the sum of its blocks.
 */

/** A lesson as the estimate sees it: its own seconds, and whether the reader is done with it. */
export interface TimedLesson {
  readingSeconds: number;
  completed: boolean;
}

/** Every lesson in the course, in one flat list (the course-level input). */
export function courseLessons(course: Course): TimedLesson[] {
  return course.blocks.flatMap(blockLessons);
}

/** Every lesson in one block (the block-level input). */
export function blockLessons(block: CourseBlock): TimedLesson[] {
  return block.modules.flatMap(moduleLessons);
}

/** Every lesson in one module (the module-level input). */
export function moduleLessons(module: CourseModule): TimedLesson[] {
  return module.lessons;
}

/** Total estimated seconds, completion ignored. What an atomic surface (a lesson page) shows. */
export function totalSeconds(lessons: readonly TimedLesson[]): number {
  return lessons.reduce((sum, lesson) => sum + lesson.readingSeconds, 0);
}

/** Estimated seconds LEFT: the total minus the lessons already marked read. */
export function remainingSeconds(lessons: readonly TimedLesson[]): number {
  return totalSeconds(lessons.filter((lesson) => !lesson.completed));
}

/**
 * Seconds → the minutes to display, or `null` for "show no time figure at all".
 *
 * `null`, not 0, for something finished; and a nonzero estimate never rounds down to "~0 min".
 */
export function readingMinutes(seconds: number): number | null {
  if (seconds <= 0) return null;
  return Math.max(1, Math.round(seconds / 60));
}

/** Just enough of i18next's `t` for this one string: a key plus numbers to interpolate. */
export type TranslateReadingTime = (key: string, params: Record<string, number>) => string;

/**
 * The string a reader sees ("~25 min", "~5 h 20 min", "~1 h"), or `null` for "show nothing here".
 *
 * Only SPLITS `readingMinutes`' integer — rounding the hours here would be a second rounding, printing
 * ~5 h 48 min as "~6 h".
 */
export function formatReadingTime(seconds: number, t: TranslateReadingTime): string | null {
  const total = readingMinutes(seconds);
  if (total === null) return null;
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (hours === 0) return t("course.readingTime", { minutes });
  if (minutes === 0) return t("course.readingTimeHours", { hours });
  return t("course.readingTimeHoursMinutes", { hours, minutes });
}
