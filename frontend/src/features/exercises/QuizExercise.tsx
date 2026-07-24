import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Answer, AttemptPayload, Deferred, OptionView } from "@/api/exercises";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

// In practice mode `onSubmit` is provided (select → submit → grade). In exam mode `deferred` is
// provided instead (capture-only: report every change, no submit button, no feedback).
type ControlProps = {
  pending?: boolean;
  onSubmit?: (answer: Answer) => void;
  deferred?: Deferred;
};

// Shared option styling — one visual language across every quiz sub-kind.
const optionOff = "border-border hover:border-primary/60 dark:border-gray-700";
const optionOn = "border-primary bg-indigo-50 dark:bg-indigo-950/40";
const optionBase =
  "flex w-full cursor-pointer items-start gap-2 rounded-md border p-3 text-left text-sm transition-colors";
const rowBase = "flex w-full items-center gap-2 rounded-md border p-3 text-sm";

function SubmitButton({ disabled, onSubmit }: { disabled: boolean; onSubmit?: () => void }) {
  const { t } = useTranslation();
  if (!onSubmit) return null; // exam mode: the runner owns submission
  return (
    <Button disabled={disabled} onClick={onSubmit}>
      {t("exercise.submit")}
    </Button>
  );
}

/** Dispatch on the quiz sub-kind. Each control lives in its own component so
 *  its local state (and hooks) mount/unmount cleanly with the sub-kind. */
export function QuizExercise({
  payload,
  pending,
  onSubmit,
  deferred,
}: { payload: AttemptPayload } & ControlProps) {
  const p: ControlProps = { pending, onSubmit, deferred };
  switch (payload.kind) {
    case "true_false":
      return <TrueFalse {...p} />;
    case "multi_select":
      return <MultiSelect options={payload.options ?? []} {...p} />;
    case "ordering":
      return <Ordering items={payload.items ?? []} {...p} />;
    case "matching":
      return <Matching lefts={payload.lefts ?? []} rights={payload.rights ?? []} {...p} />;
    case "single_choice":
    default:
      return <SingleChoice options={payload.options ?? []} {...p} />;
  }
}

function SingleChoice({ options, pending, onSubmit, deferred }: { options: OptionView[] } & ControlProps) {
  const [selected, setSelected] = useState<string | null>(
    deferred?.value && "optionId" in deferred.value ? deferred.value.optionId : null,
  );
  const choose = (id: string) => {
    setSelected(id);
    deferred?.onChange({ optionId: id });
  };
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
              onChange={() => choose(opt.id)}
            />
            <span>{opt.text}</span>
          </label>
        ))}
      </div>
      <SubmitButton
        disabled={!selected || !!pending}
        onSubmit={onSubmit && (() => selected && onSubmit({ optionId: selected }))}
      />
    </div>
  );
}

function TrueFalse({ pending, onSubmit, deferred }: ControlProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState<boolean | null>(
    deferred?.value && "value" in deferred.value ? deferred.value.value : null,
  );
  const choose = (v: boolean) => {
    setValue(v);
    deferred?.onChange({ value: v });
  };
  return (
    <div className="mt-3 space-y-3">
      <div className="flex gap-2">
        {[true, false].map((v) => (
          <button
            key={String(v)}
            type="button"
            aria-pressed={value === v}
            onClick={() => choose(v)}
            className={cn(
              "flex-1 rounded-md border px-4 py-3 text-sm font-medium transition-colors",
              value === v ? optionOn : optionOff,
            )}
          >
            {v ? t("exercise.true") : t("exercise.false")}
          </button>
        ))}
      </div>
      <SubmitButton
        disabled={value === null || !!pending}
        onSubmit={onSubmit && (() => value !== null && onSubmit({ value }))}
      />
    </div>
  );
}

function MultiSelect({ options, pending, onSubmit, deferred }: { options: OptionView[] } & ControlProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string[]>(
    deferred?.value && "optionIds" in deferred.value ? deferred.value.optionIds : [],
  );
  const toggle = (id: string) => {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    setSelected(next);
    deferred?.onChange({ optionIds: next });
  };
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
      <SubmitButton
        disabled={selected.length === 0 || !!pending}
        onSubmit={onSubmit && (() => onSubmit({ optionIds: selected }))}
      />
    </div>
  );
}

function Ordering({ items, pending, onSubmit, deferred }: { items: OptionView[] } & ControlProps) {
  const { t } = useTranslation();
  const initial =
    deferred?.value && "order" in deferred.value
      ? deferred.value.order.map((id) => items.find((i) => i.id === id)).filter((x): x is OptionView => !!x)
      : items;
  const [order, setOrder] = useState<OptionView[]>(initial.length === items.length ? initial : items);
  const move = (index: number, dir: -1 | 1) => {
    const j = index + dir;
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[index], next[j]] = [next[j], next[index]];
    setOrder(next);
    deferred?.onChange({ order: next.map((o) => o.id) });
  };
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
      <SubmitButton
        disabled={order.length === 0 || !!pending}
        onSubmit={onSubmit && (() => onSubmit({ order: order.map((o) => o.id) }))}
      />
    </div>
  );
}

function Matching({
  lefts,
  rights,
  pending,
  onSubmit,
  deferred,
}: { lefts: OptionView[]; rights: OptionView[] } & ControlProps) {
  const { t } = useTranslation();
  const [pairs, setPairs] = useState<Record<string, string>>(
    deferred?.value && "pairs" in deferred.value ? deferred.value.pairs : {},
  );
  const [activeLeft, setActiveLeft] = useState<string | null>(null);

  const rightText = (id: string) => rights.find((r) => r.id === id)?.text ?? "";
  const usedRights = new Set(Object.values(pairs));
  const allPaired = lefts.length > 0 && lefts.every((l) => pairs[l.id]);
  const commit = (next: Record<string, string>) => {
    setPairs(next);
    deferred?.onChange({ pairs: next });
  };

  const pickRight = (rightId: string) => {
    if (activeLeft === null) return;
    commit({ ...pairs, [activeLeft]: rightId });
    setActiveLeft(null);
  };
  const clearPair = (leftId: string) => {
    const next = { ...pairs };
    delete next[leftId];
    commit(next);
  };

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
      <SubmitButton disabled={!allPaired || !!pending} onSubmit={onSubmit && (() => onSubmit({ pairs }))} />
    </div>
  );
}
