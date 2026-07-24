import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Answer, Deferred, OptionView } from "@/api/exercises";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

// Practice passes onSubmit (select → submit → grade); exams pass `deferred` (capture-only, no button).
export function CalculationExercise({
  options,
  unit,
  pending,
  onSubmit,
  deferred,
}: {
  options: OptionView[];
  unit?: string | null;
  pending?: boolean;
  onSubmit?: (answer: Answer) => void;
  deferred?: Deferred;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string | null>(
    deferred?.value && "optionId" in deferred.value ? deferred.value.optionId : null,
  );
  const choose = (id: string) => {
    setSelected(id);
    deferred?.onChange({ optionId: id });
  };

  return (
    <div className="mt-3 space-y-3">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {options.map((opt) => (
          <button
            key={opt.id}
            type="button"
            aria-pressed={selected === opt.id}
            onClick={() => choose(opt.id)}
            className={cn(
              "rounded-md border px-4 py-3 text-left text-sm font-medium tabular-nums transition-colors",
              selected === opt.id
                ? "border-primary bg-indigo-50 dark:bg-indigo-950/40"
                : "border-border hover:border-primary/60 dark:border-gray-700",
            )}
          >
            {opt.value}
            {unit ? <span className="ml-1 text-gray-500 dark:text-gray-400">{unit}</span> : null}
          </button>
        ))}
      </div>
      {onSubmit && (
        <Button disabled={!selected || !!pending} onClick={() => selected && onSubmit({ optionId: selected })}>
          {t("exercise.submit")}
        </Button>
      )}
    </div>
  );
}
