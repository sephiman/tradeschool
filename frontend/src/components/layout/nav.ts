/** Where "home" is. One constant, because three things point at it — the header wordmark, the first
 * nav item, and the redirects in App.tsx — and a course that moved would otherwise take the logo
 * somewhere the nav no longer goes. */
export const HOME_PATH = "/course";

/** The primary navigation, in canonical order. One source of truth: shown inline in the header when
 * there's room (≥ sm), and folded into the avatar menu below that width so the header never overflows. */
export const NAV_ITEMS = [
  { to: HOME_PATH, labelKey: "nav.course" },
  { to: "/exams", labelKey: "nav.exams" },
  { to: "/stats", labelKey: "nav.progress" },
] as const;
