/** The primary navigation, in canonical order. One source of truth: shown inline in the header when
 * there's room (≥ sm), and folded into the avatar menu below that width so the header never overflows. */
export const NAV_ITEMS = [
  { to: "/course", labelKey: "nav.course" },
  { to: "/exams", labelKey: "nav.exam" },
  { to: "/stats", labelKey: "nav.progress" },
] as const;
