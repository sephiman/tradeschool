import { COURSE_SLUG } from "@/api/client";

/**
 * Page URLs are course-scoped, mirroring the API: `/courses/{course}/…`.
 *
 * The segment is there so the address bar says which course you are in, and so a bookmarked lesson
 * survives the day a second course exists. Routes are declared with the LITERAL slug rather than a
 * `:course` param on purpose: the API client targets one course today, so a route that matched any
 * slug would render `/courses/anything/glossary` with this course's content — a URL that lies. When
 * a second course lands, the param and the threading arrive together (see content/README.md).
 */
export function coursePath(rest = ""): string {
  return `/courses/${COURSE_SLUG}${rest}`;
}

/** Where "home" is. One constant, because the wordmark, the nav and App.tsx's redirects all point at it. */
export const HOME_PATH = coursePath();

/** The primary navigation, in canonical order — inline in the header ≥ sm, in the avatar menu below. */
export const NAV_ITEMS = [
  { to: HOME_PATH, labelKey: "nav.course" },
  { to: coursePath("/glossary"), labelKey: "nav.glossary" },
  { to: coursePath("/exams"), labelKey: "nav.exams" },
  { to: coursePath("/stats"), labelKey: "nav.progress" },
] as const;
