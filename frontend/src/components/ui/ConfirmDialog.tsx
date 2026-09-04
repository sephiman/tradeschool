import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

/**
 * A confirmation whose two answers are not "OK" and "Cancel".
 *
 * `window.confirm` — which this codebase uses for the reversible asks — can only offer those two
 * words, and cannot say which of them is the safe one. Where the destructive answer needs naming
 * ("Start a new one", against "Continue the open exam"), the reader has to be able to read the
 * consequence and pick the verb, so it gets a real dialog.
 *
 * The safe answer is the PRIMARY and holds focus on open; the destructive one is quiet and beside it.
 * That ordering is the whole point: a dialog whose destructive answer is the prominent one trains
 * people to press the prominent one.
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  onDismiss,
}: {
  title: string;
  children: ReactNode;
  /** The destructive answer. Named for what it does, never "OK". */
  confirmLabel: string;
  /** The safe answer, and the default. */
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  /**
   * Escape and a backdrop click. Defaults to the safe answer, and is separate from it because the
   * safe answer is not always inert — here it navigates, and dismissing a dialog must never move the
   * reader somewhere they did not ask to go.
   */
  onDismiss?: () => void;
}) {
  const safe = useRef<HTMLButtonElement>(null);
  const restoreTo = useRef<Element | null>(null);
  const dismiss = onDismiss ?? onCancel;

  useEffect(() => {
    restoreTo.current = document.activeElement;
    safe.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      (restoreTo.current as HTMLElement | null)?.focus?.();
    };
  }, [dismiss]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 motion-safe:animate-in motion-safe:fade-in"
      onClick={(event) => event.target === event.currentTarget && dismiss()}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-body"
        className={cn(
          "w-full max-w-sm rounded-lg border border-border bg-white p-5 shadow-xl",
          "dark:border-gray-700 dark:bg-gray-900 oled:border-oled-line-strong oled:bg-oled-bg",
        )}
      >
        <h2 id="confirm-dialog-title" className="text-base font-semibold">
          {title}
        </h2>
        <div id="confirm-dialog-body" className="mt-2 space-y-1 text-sm text-gray-600 dark:text-gray-300">
          {children}
        </div>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          {/* Destructive, and deliberately the quieter of the two: a red fill here would read as the
              recommended answer, which is the opposite of what this dialog is for. */}
          <Button
            variant="ghost"
            onClick={onConfirm}
            className="text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
          >
            {confirmLabel}
          </Button>
          <Button ref={safe} onClick={onCancel}>
            {cancelLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
