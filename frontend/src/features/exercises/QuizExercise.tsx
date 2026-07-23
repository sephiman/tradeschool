import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Answer, AttemptPayload, OptionView } from "@/api/exercises";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

type SubmitProps = { pending: boolean; onSubmit: (answer: Answer) => void };

// Shared option styling — one visual language across every quiz sub-kind.
const optionOff = "border-border hover:border-primary/60 dark:border-gray-700";
const optionOn = "border-primary bg-indigo-50 dark:bg-indigo-950/40";
const optionBase =
  "flex w-full cursor-pointer items-start gap-2 rounded-md border p-3 text-left text-sm transition-colors";
const rowBase = "flex w-full items-center gap-2 rounded-md border p-3 text-sm";

/** Dispatch on the quiz sub-kind. Each control lives in its own component so
 *  its local state (and hooks) mount/unmount cleanly with the sub-kind. */
export function QuizExercise({
  payload,
  pending,
  onSubmit,
}: { payload: AttemptPayload } & SubmitProps) {
  switch (payload.kind) {
    case "true_false":
      return <TrueFalse pending={pending} onSubmit={onSubmit} />;
    case "multi_select":
      return <MultiSelect options={payload.options ?? []} pending={pending} onSubmit={onSubmit} />;
    case "ordering":
      return <Ordering items={payload.items ?? []} pending={pending} onSubmit={onSubmit} />;
    case "matching":
      return <Matching lefts={payload.lefts ?? []} rights={payload.rights ?? []} pending={pending} onSubmit={onSubmit} />;
    case "single_choice":
    default:
      return <SingleChoice options={payload.options ?? []} pending={pending} onSubmit={onSubmit} />;
  }
}

/** Pick exactly one — unchanged behaviour from before sub-kinds existed. */
function SingleChoice({ options, pending, onSubmit }: { options: OptionView[] } & SubmitProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <div className="mt-3 space-y-3">
      <div className="space-y-2">
        {options.map((opt) => (
          <label key={opt.id} className={cn(optionBase, selected === opt.id ? optionOn : optionOff)}>
            <input
              type="radio"
              name="quiz-option"
              className="mt-0.5"
              checked={selected === opt.id}
              onChange={() => setSelected(opt.id)}
            />
            <span>{opt.text}</span>
          </label>
        ))}
      </div>
      <Button disabled={!selected || pending} onClick={() => selected && onSubmit({ optionId: selected })}>
        {t("exercise.submit")}
      </Button>
    </div>
  );
}

/** True / False — two tappable buttons, then submit. */
function TrueFalse({ pending, onSubmit }: SubmitProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState<boolean | null>(null);

  return (
    <div className="mt-3 space-y-3">
      <div className="flex gap-2">
        {[true, false].map((v) => (
          <button
            key={String(v)}
            type="button"
            aria-pressed={value === v}
            onClick={() => setValue(v)}
            className={cn(
              "flex-1 rounded-md border px-4 py-3 text-sm font-medium transition-colors",
              value === v ? optionOn : optionOff,
            )}
          >
            {v ? t("exercise.true") : t("exercise.false")}
          </button>
        ))}
      </div>
      <Button disabled={value === null || pending} onClick={() => value !== null && onSubmit({ value })}>
        {t("exercise.submit")}
      </Button>
    </div>
  );
}

/** Pick all that apply — checkbox toggles, then submit. */
function MultiSelect({ options, pending, onSubmit }: { options: OptionView[] } & SubmitProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <div className="mt-3 space-y-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">{t("exercise.selectAllThatApply")}</p>
      <div className="space-y-2">
        {options.map((opt) => {
          const on = selected.includes(opt.id);
          return (
            <label key={opt.id} className={cn(optionBase, on ? optionOn : optionOff)}>
              <input type="checkbox" className="mt-0.5" checked={on} onChange={() => toggle(opt.id)} />
              <span>{opt.text}</span>
            </label>
          );
        })}
      </div>
      <Button disabled={selected.length === 0 || pending} onClick={() => onSubmit({ optionIds: selected })}>
        {t("exercise.submit")}
      </Button>
    </div>
  );
}

/** Arrange into a sequence — tap up/down arrows (no native drag). */
function Ordering({ items, pending, onSubmit }: { items: OptionView[] } & SubmitProps) {
  const { t } = useTranslation();
  const [order, setOrder] = useState<OptionView[]>(items);
  const move = (index: number, dir: -1 | 1) =>
    setOrder((prev) => {
      const j = index + dir;
      if (j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[j]] = [next[j], next[index]];
      return next;
    });

  return (
    <div className="mt-3 space-y-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">{t("exercise.reorderHint")}</p>
      <ol className="space-y-2">
        {order.map((item, index) => (
          <li key={item.id} className={cn(rowBase, optionOff, "justify-between")}>
            <span className="flex items-center gap-2">
              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                {index + 1}
              </span>
              <span>{item.text}</span>
            </span>
            <span className="flex shrink-0 gap-1">
              <button
                type="button"
                aria-label={t("exercise.moveUp")}
                disabled={index === 0}
                onClick={() => move(index, -1)}
                className="rounded border border-border px-2 py-1 text-sm leading-none disabled:opacity-40 dark:border-gray-700"
              >
                ↑
              </button>
              <button
                type="button"
                aria-label={t("exercise.moveDown")}
                disabled={index === order.length - 1}
                onClick={() => move(index, 1)}
                className="rounded border border-border px-2 py-1 text-sm leading-none disabled:opacity-40 dark:border-gray-700"
              >
                ↓
              </button>
            </span>
          </li>
        ))}
      </ol>
      <Button disabled={order.length === 0 || pending} onClick={() => onSubmit({ order: order.map((o) => o.id) })}>
        {t("exercise.submit")}
      </Button>
    </div>
  );
}

/** Pair each left with a right — tap a left, then tap its match (tap-only). */
function Matching({
  lefts,
  rights,
  pending,
  onSubmit,
}: { lefts: OptionView[]; rights: OptionView[] } & SubmitProps) {
  const { t } = useTranslation();
  const [pairs, setPairs] = useState<Record<string, string>>({});
  const [activeLeft, setActiveLeft] = useState<string | null>(null);

  const rightText = (id: string) => rights.find((r) => r.id === id)?.text ?? "";
  const usedRights = new Set(Object.values(pairs));
  const allPaired = lefts.length > 0 && lefts.every((l) => pairs[l.id]);

  const pickRight = (rightId: string) => {
    if (activeLeft === null) return;
    setPairs((prev) => ({ ...prev, [activeLeft]: rightId }));
    setActiveLeft(null);
  };
  const clearPair = (leftId: string) =>
    setPairs((prev) => {
      const next = { ...prev };
      delete next[leftId];
      return next;
    });

  return (
    <div className="mt-3 space-y-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">{t("exercise.matchHint")}</p>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          {lefts.map((l) => {
            const paired = pairs[l.id];
            const active = activeLeft === l.id;
            return (
              <div key={l.id}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => setActiveLeft(active ? null : l.id)}
                  className={cn(rowBase, "justify-between text-left", active ? optionOn : optionOff)}
                >
                  <span>{l.text}</span>
                  {paired && (
                    <span className="ml-2 shrink-0 rounded bg-indigo-100 px-1.5 py-0.5 text-xs font-medium text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200">
                      {rightText(paired)}
                    </span>
                  )}
                </button>
                {paired && (
                  <button
                    type="button"
                    onClick={() => clearPair(l.id)}
                    className="mt-1 text-xs text-gray-400 hover:text-red-600"
                  >
                    {t("exercise.clearPair")}
                  </button>
                )}
              </div>
            );
          })}
        </div>
        <div className="space-y-2">
          {rights.map((r) => {
            const used = usedRights.has(r.id);
            return (
              <button
                key={r.id}
                type="button"
                disabled={activeLeft === null}
                onClick={() => pickRight(r.id)}
                className={cn(
                  rowBase,
                  "justify-between text-left disabled:cursor-not-allowed disabled:opacity-60",
                  used ? "border-primary/40 bg-indigo-50/60 dark:bg-indigo-950/30" : optionOff,
                )}
              >
                <span>{r.text}</span>
                {used && (
                  <span className="ml-2 text-emerald-600 dark:text-emerald-400" aria-hidden>
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
      <Button disabled={!allPaired || pending} onClick={() => onSubmit({ pairs })}>
        {t("exercise.submit")}
      </Button>
    </div>
  );
}
