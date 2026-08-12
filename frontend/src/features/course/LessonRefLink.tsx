import { useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { POPOVER_PANEL_ID, usePopover } from "@/features/glossary/TermPopover";
import { coursePath } from "@/components/layout/nav";
import type { RefTarget } from "@/lib/refs/registry";
import { cn } from "@/lib/cn";

/**
 * A lesson/module mention in prose, as the annotator marked it: a real link, quietly dressed.
 *
 * Same dotted rule as a glossary term, because both are "there is more behind this word" — but this
 * one NAVIGATES. Hover (mouse) and focus borrow the glossary's one panel to say where it goes
 * ("M22 · Gestión del riesgo"); on touch there is no preview, the tap simply goes, and the title is
 * the first thing on the page that opens.
 */
export function LessonRefLink({ target, children }: { target: RefTarget; children: ReactNode }) {
  const popover = usePopover();
  const ref = useRef<HTMLAnchorElement>(null);
  const key = `ref:${target.id}`;

  const card = (
    <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
      <span className="tabular-nums">{target.id.toUpperCase()}</span> · {target.title}
    </p>
  );
  const open = () => ref.current && popover?.show(key, card, ref.current, false);

  return (
    <Link
      ref={ref}
      to={coursePath(target.path)}
      aria-describedby={popover?.shownKey === key ? POPOVER_PANEL_ID : undefined}
      onPointerEnter={(event) => event.pointerType === "mouse" && open()}
      onPointerLeave={(event) => event.pointerType === "mouse" && popover?.hide(false)}
      onFocus={open}
      onBlur={() => popover?.hide(false)}
      className={cn(
        "border-b border-dotted border-gray-400 tabular-nums",
        "hover:border-gray-600 focus:outline-none focus-visible:rounded-xs focus-visible:ring-2 focus-visible:ring-primary",
        "dark:border-gray-500 dark:hover:border-gray-300 oled:border-oled-line-strong oled:hover:border-gray-400",
      )}
    >
      {children}
    </Link>
  );
}
