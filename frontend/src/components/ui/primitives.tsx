import {
  forwardRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type LabelHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";
import { cn } from "@/lib/cn";

/** Small non-interactive status/label pill. */
export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "amber" | "indigo" | "green" | "red";
  className?: string;
}) {
  // Untouched by OLED on purpose: a badge is content, not a surface. Its tint IS its separation, and
  // every one of these fills gains contrast against #000 rather than losing it — blacking them out
  // would turn a pre-attentive pill into an outline and cost the hierarchy for nothing.
  const tones = {
    neutral: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
    amber: "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200",
    indigo: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200",
    green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
    red: "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200",
  };
  return (
    <span className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }
>(({ className, variant = "primary", type = "button", ...props }, ref) => {
  // `primary` and `danger` are solid accent fills that stand on their own against black; only the
  // two that lean on a gray surface need the border to survive it.
  const variants = {
    primary: "bg-primary text-primary-foreground hover:bg-indigo-700",
    secondary:
      "bg-white border border-border text-gray-900 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-600 dark:hover:bg-gray-700 oled:bg-oled-bg oled:border-oled-line-strong oled:hover:bg-oled-hover",
    danger: "bg-red-600 text-white hover:bg-red-700",
    ghost: "bg-transparent text-gray-700 hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-gray-800 oled:hover:bg-oled-hover",
  };
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50 dark:focus:ring-offset-gray-900 oled:focus:ring-offset-oled-bg",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
});
Button.displayName = "Button";

const invalidRing = "border-red-500 ring-1 ring-red-500 focus:border-red-500 focus:ring-red-500 dark:border-red-500";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(
  ({ className, invalid, ...props }, ref) => (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        // A field on black has no fill to distinguish it from the page, so `line-strong` carries the
        // whole affordance; disabled darkens nothing (it is already black) and dims the border instead.
        "block w-full rounded-md border border-border bg-white px-3 py-2 text-sm shadow-sm placeholder:text-gray-400 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:bg-gray-100 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder:text-gray-500 dark:disabled:bg-gray-700 oled:border-oled-line-strong oled:bg-oled-bg oled:disabled:border-oled-line oled:disabled:bg-oled-bg",
        invalid && invalidRing,
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }>(
  ({ className, invalid, ...props }, ref) => (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "block w-full rounded-md border border-border bg-white px-3 py-2 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 oled:border-oled-line-strong oled:bg-oled-bg",
        invalid && invalidRing,
        className,
      )}
      {...props}
    />
  ),
);
Select.displayName = "Select";

export function Label({ className, ...props }: LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300", className)} {...props} />;
}

/**
 * On OLED the card's background step and `shadow-sm` both vanish, so its border is the only thing left
 * saying where it ends — it steps up to the lighter `line` token there.
 */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900 oled:border-oled-line oled:bg-oled-bg",
        className,
      )}
      {...props}
    />
  );
}

/**
 * A count-of-total rendered pre-attentively, beside the same figure in text.
 *
 * Deliberately monochrome — emerald/red would make a half-finished module a grade, and indigo is the
 * interactive accent. `aria-hidden`, since the fraction beside it already announces the value.
 */
export function MiniBar({ value, total, className }: { value: number; total: number; className?: string }) {
  const filled = total > 0 ? Math.min(100, Math.max(0, (value / total) * 100)) : 0;
  return (
    <span
      aria-hidden
      className={cn("inline-block h-1 w-10 shrink-0 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700", className)}
    >
      <span className="block h-full rounded-full bg-gray-500 dark:bg-gray-400" style={{ width: `${filled}%` }} />
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="loading"
      className={cn(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent",
        className,
      )}
    />
  );
}
