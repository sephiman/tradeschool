import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { GlossaryEntry } from "@/api/course";
import { coursePath } from "@/components/layout/nav";
import { cn } from "@/lib/cn";

/**
 * The card a marked term — or any other in-prose affordance — shows: hovered on a mouse, tapped on a
 * touch screen.
 *
 * ONE panel for the whole page, positioned over the element that asked for it — a lesson marks dozens
 * of terms and a popover each would be dozens of subscriptions and dozens of nodes. The split between
 * hover and tap is read off the pointer EVENT rather than a media query, so a hybrid laptop gets
 * whichever the reader actually used.
 *
 * A hovered panel follows the pointer away; a tapped one is pinned and stays until it is dismissed,
 * which is the whole difference between the two surfaces. The host shows whatever content it is
 * handed — the glossary's definition card, a lesson reference's title line — so a second affordance
 * reuses the machinery instead of growing its own.
 */

const PANEL_ID = "glossary-term-popover";
/** Every card's own title carries this id, so the panel can name itself with one `aria-labelledby`. */
const PANEL_TITLE_ID = "glossary-term-popover-title";
/** Panel width, and the margin it keeps from the viewport edge. */
const PANEL_WIDTH = 320;
const EDGE = 8;

interface Shown {
  /** What the panel is showing, so a toggle on the same anchor closes rather than reopens. */
  key: string;
  content: ReactNode;
  anchor: DOMRect;
  /** Tapped, not hovered: it survives the pointer leaving and needs an explicit dismissal. */
  pinned: boolean;
}

interface TermPopoverApi {
  shownKey: string | null;
  /** Tapped or activated rather than hovered — the state in which the panel holds focus. */
  shownPinned: boolean;
  show(key: string, content: ReactNode, anchor: HTMLElement, pinned: boolean): void;
  hide(force: boolean): void;
  toggle(key: string, content: ReactNode, anchor: HTMLElement): void;
  entries: Map<string, GlossaryEntry>;
}

const TermPopoverContext = createContext<TermPopoverApi | null>(null);

/** The one panel's API, for affordances outside this file (the lesson-reference links). */
export function usePopover(): TermPopoverApi | null {
  return useContext(TermPopoverContext);
}

/** The id the panel renders under, so a trigger can point `aria-describedby` at it while shown. */
export const POPOVER_PANEL_ID = PANEL_ID;

/** The id a card puts on its own title line; the panel is labelled by whatever is showing. */
export const POPOVER_TITLE_ID = PANEL_TITLE_ID;

/** Where the panel goes: under the term, flipped above when the term sits low, clamped on both sides. */
function place(anchor: DOMRect): { left: number; top?: number; bottom?: number } {
  const maxLeft = Math.max(EDGE, window.innerWidth - PANEL_WIDTH - EDGE);
  const left = Math.min(Math.max(EDGE, anchor.left), maxLeft);
  const below = window.innerHeight - anchor.bottom;
  return below < 220 && anchor.top > below
    ? { left, bottom: window.innerHeight - anchor.top + 6 }
    : { left, top: anchor.bottom + 6 };
}

function OriginLink({ origin, title }: { origin: string | null; title: string | null }) {
  const { t } = useTranslation();
  if (!origin) return null;
  return (
    <Link
      to={coursePath(`/lessons/${origin}`)}
      className="text-primary hover:underline"
    >
      {t("glossary.originLabel")} <span className="tabular-nums">{origin.toUpperCase()}</span>
      {title ? ` · ${title}` : ""}
    </Link>
  );
}

/** The definition itself: a single sense, or a homonym's numbered senses with their own origins. */
function TermCard({ entry, entries }: { entry: GlossaryEntry; entries: Map<string, GlossaryEntry> }) {
  const { t } = useTranslation();
  // An alias owns no words: the canonical entry it points at does, and that is what a reader needs
  // here rather than a second hop.
  const canonical = entry.aliasOf ? entries.get(entry.aliasOf.id) : undefined;
  const defining = canonical ?? entry;

  return (
    <>
      <p id={PANEL_TITLE_ID} className="font-semibold text-gray-900 dark:text-gray-100">
        {entry.term}
      </p>
      {entry.aliasOf && (
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          {t("glossary.aliasHint")} <span className="font-medium">{entry.aliasOf.term}</span>
        </p>
      )}
      {defining.definition && (
        <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{defining.definition}</p>
      )}
      {(defining.senses ?? []).map((sense, index) => (
        <p key={sense.origin + index} className="mt-1.5 text-sm text-gray-700 dark:text-gray-300">
          <span className="font-semibold text-primary">{t("glossary.sense", { index: index + 1 })}</span>
          {sense.definition}
        </p>
      ))}
      <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
        <OriginLink origin={defining.origin} title={defining.originTitle} />
        <Link
          to={coursePath(`/glossary#${defining.id}`)}
          className="text-primary hover:underline"
        >
          {t("glossary.fullEntry")}
        </Link>
      </p>
    </>
  );
}

export function TermPopoverHost({
  entries,
  children,
}: {
  entries: Map<string, GlossaryEntry>;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const [shown, setShown] = useState<Shown | null>(null);
  const panel = useRef<HTMLDivElement>(null);

  const show = useCallback((key: string, content: ReactNode, anchor: HTMLElement, pinned: boolean) => {
    setShown({ key, content, anchor: anchor.getBoundingClientRect(), pinned });
  }, []);

  // `force` is what separates the two surfaces: a pointer leaving must not close a pinned panel.
  const hide = useCallback((force: boolean) => {
    setShown((current) => (current === null || force || !current.pinned ? null : current));
  }, []);

  const toggle = useCallback((key: string, content: ReactNode, anchor: HTMLElement) => {
    setShown((current) =>
      current?.pinned && current.key === key
        ? null
        : { key, content, anchor: anchor.getBoundingClientRect(), pinned: true },
    );
  }, []);

  useEffect(() => {
    if (shown === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") hide(true);
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (panel.current?.contains(target ?? null)) return;
      if (target?.closest?.("[data-glossary-term]")) return; // the trigger's own click toggles it
      hide(true);
    };
    // A scrolled page leaves the panel behind its term; closing beats drifting.
    const onScroll = () => hide(true);
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [shown, hide]);

  const api = useMemo<TermPopoverApi>(
    () => ({
      shownKey: shown?.key ?? null,
      shownPinned: shown?.pinned ?? false,
      show,
      hide,
      toggle,
      entries,
    }),
    [shown, show, hide, toggle, entries],
  );

  return (
    <TermPopoverContext.Provider value={api}>
      {children}
      {shown && (
        <div
          ref={panel}
          id={PANEL_ID}
          // A hovered panel is a tooltip; a pinned one holds a focusable action (a reference's "go
          // to", a glossary card's links) and is a non-modal dialog, which is what makes that action
          // reachable rather than merely present.
          role={shown.pinned ? "dialog" : "tooltip"}
          aria-labelledby={PANEL_TITLE_ID}
          style={{ position: "fixed", width: PANEL_WIDTH, maxWidth: `calc(100vw - ${EDGE * 2}px)`, ...place(shown.anchor) }}
          className="z-50 rounded-lg border border-border bg-white p-3 shadow-lg dark:border-gray-700 dark:bg-gray-900 oled:border-oled-line-strong oled:bg-oled-bg"
        >
          {shown.content}
          {shown.pinned && (
            // Touch has no "move the pointer away", so a pinned panel carries its own way out.
            <button
              type="button"
              onClick={() => hide(true)}
              aria-label={t("glossary.closeDefinition")}
              className="absolute top-1 right-2 text-lg leading-none text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            >
              ×
            </button>
          )}
        </div>
      )}
    </TermPopoverContext.Provider>
  );
}

/**
 * A marked term in the prose.
 *
 * Discreet on purpose: a dotted rule under the word and nothing else — no colour change, no weight
 * change, so a lesson with forty marked terms still reads as prose. It is a real `<button>`, so it is
 * in the tab order and opens on focus for a keyboard reader.
 */
export function GlossaryTerm({ termId, children }: { termId: string; children: ReactNode }) {
  const popover = useContext(TermPopoverContext);
  const ref = useRef<HTMLButtonElement>(null);
  const entry = popover?.entries.get(termId);
  if (!popover || !entry) return <>{children}</>;

  const card = <TermCard entry={entry} entries={popover.entries} />;
  const open = (pinned: boolean) => ref.current && popover.show(termId, card, ref.current, pinned);
  return (
    <button
      ref={ref}
      type="button"
      data-glossary-term={termId}
      aria-describedby={popover.shownKey === termId ? PANEL_ID : undefined}
      onPointerEnter={(event) => event.pointerType === "mouse" && open(false)}
      onPointerLeave={(event) => event.pointerType === "mouse" && popover.hide(false)}
      onFocus={() => open(false)}
      onBlur={() => popover.hide(false)}
      onClick={() => ref.current && popover.toggle(termId, card, ref.current)}
      className={cn(
        "cursor-help border-b border-dotted border-gray-400 bg-transparent p-0 text-left font-[inherit] text-[inherit]",
        "hover:border-gray-600 focus:outline-none focus-visible:rounded-xs focus-visible:ring-2 focus-visible:ring-primary",
        "dark:border-gray-500 dark:hover:border-gray-300 oled:border-oled-line-strong oled:hover:border-gray-400",
      )}
    >
      {children}
    </button>
  );
}
