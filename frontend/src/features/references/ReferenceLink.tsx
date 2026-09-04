import { useEffect, useRef, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  POPOVER_PANEL_ID,
  POPOVER_TITLE_ID,
  usePopover,
} from "@/features/glossary/TermPopover";
import { coursePath } from "@/components/layout/nav";
import type { RefTarget } from "@/lib/refs/registry";
import { cn } from "@/lib/cn";

/**
 * A module or lesson mention in prose, and the card behind it.
 *
 * ONE component for both mark kinds and for every surface that carries prose — a lesson's body, an
 * exercise prompt, an exam question — because a reference means the same thing wherever it is read
 * and a second implementation would be a second answer to "what does m19-l2 say".
 *
 * The mention stays a real `<a href>`: middle-click, ⌘-click, "copy link address" and the status bar
 * are browser affordances a `<button>` would quietly take away, and a modified click falls straight
 * through to them. What a PLAIN activation does is open the card instead of navigating, and the card
 * carries the navigation as an explicit action. That is deliberate: the same mention appears inside
 * an exam question, where an accidental tap that yanks the learner off the question costs them the
 * answer — so the reader gets to read what m19-l2 is before deciding to go. The Android app made the
 * same call for the same reason.
 */

/** Marks the panel's navigation action, so the trigger can hand it focus when the card opens. */
const GO_ACTION = "data-reference-go";

function ReferenceCard({ target }: { target: RefTarget }) {
  const { t } = useTranslation();
  const isLesson = target.kind === "lesson";
  return (
    <>
      <p className="text-xs font-medium tracking-wide text-primary uppercase">
        {t(isLesson ? "reference.kindLesson" : "reference.kindModule")}
      </p>
      <p
        id={POPOVER_TITLE_ID}
        className="mt-0.5 font-semibold text-gray-900 dark:text-gray-100"
      >
        <span className="tabular-nums">{target.id.toUpperCase()}</span> ·{" "}
        {target.title}
      </p>
      {/* A lesson title says little on its own; the module it sits in is half of what identifies it.
          A module is its own attribution, so it does not repeat itself. */}
      {isLesson && (
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          {t("reference.inModule")}{" "}
          <span className="tabular-nums">{target.module.id.toUpperCase()}</span>{" "}
          · {target.module.title}
        </p>
      )}
      {target.summary && (
        <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">
          {target.summary}
        </p>
      )}
      <p className="mt-3">
        <Link
          {...{ [GO_ACTION]: "" }}
          to={coursePath(target.path)}
          className="font-medium text-primary hover:underline focus:outline-none focus-visible:rounded-xs focus-visible:ring-2 focus-visible:ring-primary"
        >
          {t(isLesson ? "reference.goToLesson" : "reference.goToModule")} →
        </Link>
      </p>
    </>
  );
}

export function ReferenceLink({
  target,
  children,
}: {
  target: RefTarget;
  children: ReactNode;
}) {
  const popover = usePopover();
  const ref = useRef<HTMLAnchorElement>(null);
  const held = useRef(false);
  // Set while this component is handing focus back after a dismissal, so the `focus` that lands on
  // the mention does not re-open the card the reader just closed.
  const restoring = useRef(false);
  const key = `ref:${target.id}`;
  const pinned = popover?.shownKey === key && popover.shownPinned;

  const card = <ReferenceCard target={target} />;
  const open = (pin: boolean) =>
    ref.current && popover?.show(key, card, ref.current, pin);

  useEffect(() => {
    if (pinned) {
      held.current = true;
      // The panel renders after the prose, so Tab would walk past it: focus is moved in instead, and
      // handed back below. Without this the action is on screen and unreachable from a keyboard.
      document
        .querySelector<HTMLElement>(`#${POPOVER_PANEL_ID} [${GO_ACTION}]`)
        ?.focus();
      return;
    }
    if (!held.current) return;
    held.current = false;
    // Escape (or a scroll) leaves focus on `body`; clicking elsewhere leaves it on that element, and
    // stealing it back from a reader who has moved on would be worse than not restoring it at all.
    const active = document.activeElement;
    if (active && active !== document.body) return;
    restoring.current = true;
    ref.current?.focus(); // synchronous, so the guard is still set when `onFocus` runs
    restoring.current = false;
  }, [pinned]);

  return (
    <Link
      ref={ref}
      to={coursePath(target.path)}
      data-reference-id={target.id}
      aria-describedby={
        popover?.shownKey === key && !pinned ? POPOVER_PANEL_ID : undefined
      }
      aria-expanded={pinned ? true : undefined}
      aria-controls={pinned ? POPOVER_PANEL_ID : undefined}
      onPointerEnter={(event) => event.pointerType === "mouse" && open(false)}
      onPointerLeave={(event) =>
        event.pointerType === "mouse" && popover?.hide(false)
      }
      onFocus={() => !restoring.current && !pinned && open(false)}
      onBlur={() => popover?.hide(false)}
      onClick={(event) => {
        // ⌘/Ctrl/Shift/Alt-click and middle-click are the reader asking the BROWSER for this link.
        if (
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey ||
          event.button !== 0
        ) {
          return;
        }
        event.preventDefault();
        if (ref.current) popover?.toggle(key, card, ref.current);
      }}
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
