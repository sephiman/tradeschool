import { describe, expect, it } from "vitest";
import type { Course, CourseBlock, CourseModule } from "@/api/course";
import en from "@/i18n/en.json";
import es from "@/i18n/es.json";
import {
  blockLessons,
  courseLessons,
  formatReadingTime,
  moduleLessons,
  readingMinutes,
  remainingSeconds,
  totalSeconds,
  type TimedLesson,
} from "./readingTime";

/**
 * Reading time across the four surfaces.
 *
 * The backend serves SECONDS per lesson; everything else — module, block, course, and the string a
 * reader sees — is derived here. Two properties matter more than any single number:
 *
 * 1. **Sum seconds, round once.** Rounded minutes do not add up: three 89-second lessons are "~1 min"
 *    each and "~4 min" together. A reader who adds the visible block figures must land exactly on the
 *    course figure, and that only holds if minutes are computed from summed seconds at the very end.
 * 2. **One source, every level.** Course remaining, block remaining and module remaining all come from
 *    the same function over the same per-lesson values, so they cannot drift apart — the consistency is
 *    structural, not a coincidence three call sites keep up by hand.
 */

function lesson(readingSeconds: number, completed = false): TimedLesson {
  return { readingSeconds, completed };
}

/** i18next's interpolation, over the REAL catalogs: the tests below assert the string a reader sees,
 *  not a shape a stand-in invented — a catalog missing a key or a placeholder fails here. */
function translator(catalog: Record<string, unknown>) {
  const course = (catalog as { course: Record<string, string> }).course;
  return (key: string, params: Record<string, number>): string => {
    const template = course[key.replace("course.", "")];
    if (template === undefined) throw new Error(`missing catalog key ${key}`);
    return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(params[name]));
  };
}

const tEn = translator(en);
const tEs = translator(es);
const MINUTE = 60;
const HOUR = 60 * MINUTE;

/** A module carrying the given lessons. Only the fields the estimate reads are meaningful. */
function module(id: string, lessons: TimedLesson[]): CourseModule {
  return {
    id,
    order: 1,
    title: id,
    summary: "",
    assumes: [],
    unmetPrereqs: [],
    hasContent: lessons.length > 0,
    lessonsTotal: lessons.length,
    lessonsCompleted: lessons.filter((l) => l.completed).length,
    exercisesTotal: 0,
    exercisesPassed: 0,
    lessons: lessons.map((l, i) => ({
      id: `${id}-l${i + 1}`,
      order: i + 1,
      title: `${id} lesson ${i + 1}`,
      completed: l.completed,
      readingSeconds: l.readingSeconds,
      exercises: [],
    })),
  };
}

function block(id: string, modules: CourseModule[]): CourseBlock {
  return { id, order: 1, title: id, modules };
}

function course(blocks: CourseBlock[]): Course {
  return {
    locale: "en",
    started: true,
    course: { id: "c", title: "Course", description: "" },
    blocks,
  };
}

// Deliberately awkward numbers: every unread lesson is just under a minute and a half, so rounding
// early and rounding once give different answers at every level above the lesson. Three unread
// lessons of 89s = 267s: "~4 min" summed as seconds, "~3 min" if each were rounded first.
const AWKWARD = course([
  block("b1", [module("m1", [lesson(89), lesson(89, true)]), module("m2", [])]),
  block("b2", [module("m3", [lesson(89)])]),
  block("b3", [module("m4", [lesson(89), lesson(300, true)])]),
]);

describe("readingMinutes", () => {
  it("rounds a nonzero estimate to at least one minute", () => {
    // 20 seconds is a real, if short, read: it must not print as "~0 min".
    expect(readingMinutes(20)).toBe(1);
    expect(readingMinutes(1)).toBe(1);
    expect(readingMinutes(89)).toBe(1);
    expect(readingMinutes(100)).toBe(2);
  });

  it("returns null — no time figure at all — for nothing left to read", () => {
    // A finished module/block/course says nothing rather than "~0 min", and a module with no lessons
    // published has no estimate to show either.
    expect(readingMinutes(0)).toBeNull();
    expect(readingMinutes(-1)).toBeNull();
  });
});

describe("formatReadingTime", () => {
  it("says a sub-hour estimate in minutes", () => {
    expect(formatReadingTime(25 * MINUTE, tEn)).toBe("~25 min");
    expect(formatReadingTime(25 * MINUTE, tEs)).toBe("~25 min");
    // The boundary from below, and the 1-minute floor, still read as minutes.
    expect(formatReadingTime(59 * MINUTE, tEn)).toBe("~59 min");
    expect(formatReadingTime(20, tEn)).toBe("~1 min");
  });

  it("drops the minutes part on an exact hour", () => {
    // "~1 h 0 min" is a number with a hole in it; an exact hour is just an hour.
    expect(formatReadingTime(HOUR, tEn)).toBe("~1 h");
    expect(formatReadingTime(HOUR, tEs)).toBe("~1 h");
    expect(formatReadingTime(2 * HOUR, tEn)).toBe("~2 h");
    // Exact *after* the one rounding, too: 3599s is 60 minutes, so it is an hour, not "~59 min".
    expect(formatReadingTime(3599, tEn)).toBe("~1 h");
  });

  it("says an hour-and-more estimate as hours and minutes", () => {
    expect(formatReadingTime(5 * HOUR + 48 * MINUTE, tEn)).toBe("~5 h 48 min");
    expect(formatReadingTime(5 * HOUR + 48 * MINUTE, tEs)).toBe("~5 h 48 min");
    expect(formatReadingTime(HOUR + MINUTE, tEn)).toBe("~1 h 1 min");
    // The hours part is a SPLIT of the single rounded total, never a rounding of its own: 5h48
    // must not creep up to "~6 h".
    expect(formatReadingTime(5 * HOUR + 48 * MINUTE, tEn)).not.toContain("6 h");
  });

  it("shows nothing when there is nothing left, at any magnitude", () => {
    expect(formatReadingTime(0, tEn)).toBeNull();
    expect(formatReadingTime(-1, tEs)).toBeNull();
  });

  it("formats from the summed seconds, adding no second rounding", () => {
    // Three 89-second lessons: 267s -> 4 min. Rounding per lesson first would print "~3 min", and at
    // the hour scale the same error is a whole missing minute inside the hours form.
    const lessons = [lesson(89), lesson(89), lesson(89)];
    expect(formatReadingTime(totalSeconds(lessons), tEn)).toBe("~4 min");
    // 41 lessons of 89s = 3649s -> 61 min -> "~1 h 1 min"; per-lesson rounding would give 41 min.
    const many = Array.from({ length: 41 }, () => lesson(89));
    expect(readingMinutes(totalSeconds(many))).toBe(61);
    expect(formatReadingTime(totalSeconds(many), tEn)).toBe("~1 h 1 min");
  });
});

describe("aggregation sums seconds and rounds once", () => {
  it("never sums already-rounded minutes", () => {
    const lessons = [lesson(89), lesson(89), lesson(89)];
    // What a per-lesson rounding would produce, spelled out so the drift is visible:
    const naive = lessons.reduce((sum, l) => sum + (readingMinutes(l.readingSeconds) ?? 0), 0);
    expect(naive).toBe(3);
    // What the aggregate actually says: 267s -> 4.45 min -> 4.
    expect(totalSeconds(lessons)).toBe(267);
    expect(readingMinutes(totalSeconds(lessons))).toBe(4);
    expect(readingMinutes(totalSeconds(lessons))).not.toBe(naive);
  });

  it("builds the course figure from the blocks' seconds, not from their minutes", () => {
    const perBlock = AWKWARD.blocks.map((b) => remainingSeconds(blockLessons(b)));
    // Exact at every level, because seconds is the only thing being added: the course figure IS the
    // blocks' figures, summed before anything is rounded.
    expect(remainingSeconds(courseLessons(AWKWARD))).toBe(perBlock.reduce((a, b) => a + b, 0));
    expect(readingMinutes(remainingSeconds(courseLessons(AWKWARD)))).toBe(4);
    // Round each block first and the course loses a whole minute — the error this discipline removes.
    const roundedFirst = perBlock.reduce((sum, s) => sum + (readingMinutes(s) ?? 0), 0);
    expect(roundedFirst).toBe(3);
  });
});

describe("remaining = total − completed, at every level", () => {
  it("derives every level from the same per-lesson seconds", () => {
    const all = courseLessons(AWKWARD);
    const completedSeconds = totalSeconds(all.filter((l) => l.completed));

    // The definition, at course level...
    expect(remainingSeconds(all)).toBe(totalSeconds(all) - completedSeconds);
    // ...and equal to the plain sum of the uncompleted lessons' own seconds.
    expect(remainingSeconds(all)).toBe(
      all.filter((l) => !l.completed).reduce((sum, l) => sum + l.readingSeconds, 0),
    );

    // The same identity holds per block and per module, and the levels nest exactly.
    for (const b of AWKWARD.blocks) {
      const blockTotal = totalSeconds(blockLessons(b));
      const blockDone = totalSeconds(blockLessons(b).filter((l) => l.completed));
      expect(remainingSeconds(blockLessons(b))).toBe(blockTotal - blockDone);
      expect(remainingSeconds(blockLessons(b))).toBe(
        b.modules.reduce((sum, m) => sum + remainingSeconds(moduleLessons(m)), 0),
      );
    }
    expect(remainingSeconds(all)).toBe(
      AWKWARD.blocks.reduce((sum, b) => sum + remainingSeconds(blockLessons(b)), 0),
    );
  });

  it("shows no figure for a module, block or course that is entirely read", () => {
    const done = course([
      block("b1", [module("m1", [lesson(600, true), lesson(300, true)])]),
      block("b2", [module("m2", [lesson(450, true)])]),
    ]);
    for (const b of done.blocks) {
      for (const m of b.modules) expect(readingMinutes(remainingSeconds(moduleLessons(m)))).toBeNull();
      expect(readingMinutes(remainingSeconds(blockLessons(b)))).toBeNull();
    }
    expect(readingMinutes(remainingSeconds(courseLessons(done)))).toBeNull();
    // The time did not vanish — it is all *completed*, which is exactly why nothing is shown.
    expect(totalSeconds(courseLessons(done))).toBe(1350);
  });

  it("a partly-read module still shows only what is left", () => {
    // Asymmetric on purpose: the read lesson and the unread one must not be interchangeable, or a
    // remaining/completed mix-up would produce the same number and pass unnoticed.
    const m = module("m1", [lesson(600), lesson(300, true)]);
    expect(readingMinutes(remainingSeconds(moduleLessons(m)))).toBe(10);
    expect(readingMinutes(totalSeconds(moduleLessons(m)))).toBe(15);
  });
});

describe("a multi-lesson module page", () => {
  it("shows remaining in its header and each lesson's own full estimate in its rows", () => {
    // m09-shaped: two lessons, the first already read. The header is an aggregate (time LEFT), each row
    // is atomic (its own full time) — so the rows deliberately do NOT add up to the header, and a read
    // lesson still prints its cost instead of vanishing to "~0 min".
    const m = module("m09", [lesson(9 * 60, true), lesson(11 * 60)]);
    const rows = moduleLessons(m).map((l) => formatReadingTime(l.readingSeconds, tEn));
    expect(rows).toEqual(["~9 min", "~11 min"]);
    expect(formatReadingTime(remainingSeconds(moduleLessons(m)), tEn)).toBe("~11 min");
    // Both come from the same per-lesson seconds: the header is exactly the unread rows' total.
    expect(remainingSeconds(moduleLessons(m))).toBe(11 * 60);
    expect(totalSeconds(moduleLessons(m))).toBe(20 * 60);
  });
});

describe("a lesson is atomic", () => {
  it("shows its own full estimate whether or not it is completed", () => {
    // The lesson page uses totalSeconds (its own seconds), never remainingSeconds: "70% left of this
    // lesson" is not a thing the app knows, and a re-read costs what the first read cost.
    const read = lesson(420, true);
    const unread = lesson(420);
    expect(readingMinutes(totalSeconds([read]))).toBe(7);
    expect(readingMinutes(totalSeconds([unread]))).toBe(7);
    expect(readingMinutes(remainingSeconds([read]))).toBeNull();
  });
});
