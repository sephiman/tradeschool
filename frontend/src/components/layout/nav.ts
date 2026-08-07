/** Where "home" is. One constant, because the wordmark, the nav and App.tsx's redirects all point at it. */
export const HOME_PATH = "/course";

/** The primary navigation, in canonical order — inline in the header ≥ sm, in the avatar menu below. */
export const NAV_ITEMS = [
  { to: HOME_PATH, labelKey: "nav.course" },
  { to: "/exams", labelKey: "nav.exams" },
  { to: "/stats", labelKey: "nav.progress" },
] as const;
