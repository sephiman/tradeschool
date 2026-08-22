import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Answer, Deferred, OptionView } from "@/api/exercises";
import { Button } from "@/components/ui/primitives";
import { FormulaReminder } from "@/features/exercises/FormulaReminder";
import { InlineCalculator } from "@/features/exercises/InlineCalculator";
import { cn } from "@/lib/cn";
import { matchOptionValue } from "@/lib/numbers";

// Practice passes onSubmit (select → submit → grade); exams pass `deferred` (capture-only, no button).
export function CalculationExercise({
  options,
  unit,
  formula,
  pending,
  onSubmit,
  deferred,
}: {
  options: OptionView[];
  unit?: string | null;
  formula?: string | null;
  pending?: boolean;
  onSubmit?: (answer: Answer) => void;
  deferred?: Deferred;
}) {
  const { t, i18n } = useTranslation();
  const [showCalc, setShowCalc] = useState(false);
  const [selected, setSelected] = useState<string | null>(
    deferred?.value && "optionId" in deferred.value ? deferred.value.optionId : null,
  );

  const choose = (id: string) => {
    setSelected(id);
    deferred?.onChange({ optionId: id });
  };

  const handleUseResult = (calcVal: string) => {
    // The calculator's own display is raw JS; the option labels arrive formatted for the locale
    // ("70.000", "35,00"), so they have to be read back through the locale before comparing.
    const valNum = parseFloat(calcVal);
    if (isNaN(valNum)) return;
    const match = matchOptionValue(options, valNum, i18n.language);
    if (match) {
      choose(match.id);
    }
  };

  return (
    <div className="mt-3 space-y-3">
      {/* Top tools strip: Formula reminder & Calculator toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2.5 dark:border-gray-800 oled:border-oled-line">
        <FormulaReminder formula={formula} />
        <button
          type="button"
          onClick={() => setShowCalc((prev) => !prev)}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-white px-2.5 py-1 text-xs font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-750 oled:border-oled-line-strong oled:bg-oled-bg oled:hover:bg-oled-hover"
        >
          <span>🧮</span>
          <span>{showCalc ? t("exercise.hideCalculator") : t("exercise.calculator")}</span>
        </button>
      </div>

      {/* Inline calculator panel */}
      {showCalc && (
        <div className="flex justify-center py-1">
          <InlineCalculator onUseResult={handleUseResult} />
        </div>
      )}

      {/* Options grid */}
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
