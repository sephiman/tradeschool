import type { Course, CourseBlock, CourseModule } from "@/api/course";

/**
 * Reading-time aggregation for every level of the course.
 *
 * Two rules, and both are structural rather than remembered:
 *
 * 1. **Seconds are the only source of truth.** The backend serves an estimate per lesson in seconds;
 *    a module, block or course figure is the SUM of those seconds, rounded exactly once, here. Summing
 *    already-rounded minutes drifts — three 89-second lessons print "1 min" each and "4 min" together,
 *    and a reader adding the visible numbers would get 3 — so no aggregate is ever built from minutes.
 * 2. **Every level goes through these same two functions over the same per-lesson values**, so a course
 *    total cannot disagree with the sum of its blocks: there is nothing else for either to be computed
 *    from.
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

/** Estimated seconds LEFT: the total minus the lessons already marked read. What every aggregate
 *  surface shows, because "how long is this course" is only useful as "how much is left of it". */
export function remainingSeconds(lessons: readonly TimedLesson[]): number {
  return totalSeconds(lessons.filter((lesson) => !lesson.completed));
}

/**
 * Seconds → the minutes to display, or `null` for "show no time figure at all".
 *
 * `null` (not 0) is the answer for a finished module/block/course: "~0 min" is noise on something the
 * reader has completed. A nonzero estimate never rounds down to nothing either — a two-paragraph
 * lesson is "~1 min", not "~0 min".
 */
export function readingMinutes(seconds: number): number | null {
  if (seconds <= 0) return null;
  return Math.max(1, Math.round(seconds / 60));
}

/** Just enough of i18next's `t` for this one string: a key plus numbers to interpolate. */
export type TranslateReadingTime = (key: string, params: Record<string, number>) => string;

/**
 * The string a reader sees, or `null` for "show nothing here".
 *
 * Past an hour, raw minutes stop being readable — "~320 min" is a number you have to divide — so the
 * estimate is said as hours and minutes ("~5 h 20 min"), and an exact hour drops the minutes part
 * ("~1 h", never "~1 h 0 min"). Below an hour it is unchanged ("~25 min").
 *
 * There is still exactly ONE rounding in the whole pipeline: `readingMinutes` turns summed seconds into
 * whole minutes, and this function only *splits* that integer (`floor` + `%`, both exact). Rounding the
 * hours would be a second rounding and would make ~5 h 48 min print as "~6 h".
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
