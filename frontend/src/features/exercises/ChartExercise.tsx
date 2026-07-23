import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Answer, AttemptPayload, GradeResponse } from "@/api/exercises";
import { CandleChart } from "@/components/charts/CandleChart";
import { divergenceMarkers } from "@/components/charts/markers";
import { Button } from "@/components/ui/primitives";
import { AttemptResult } from "@/features/exercises/AttemptResult";
import { cn } from "@/lib/cn";

export function ChartExercise({
  payload,
  result,
  pending,
  onSubmit,
}: {
  payload: AttemptPayload;
  result: GradeResponse | null;
  pending: boolean;
  onSubmit: (answer: Answer) => void;
}) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string | null>(null);
  const choices = payload.choices ?? [];

  const divergence =
    result && typeof (result.correctAnswer as { divergence?: string })?.divergence === "string"
      ? (result.correctAnswer as { divergence: string }).divergence
      : null;

  return (
    <div className="mt-3 space-y-3">
      {payload.series && (
        <CandleChart
          series={payload.series}
          rsi={payload.rsi}
          macd={payload.macd}
          indicator={payload.indicator ?? "rsi"}
          markers={result ? divergenceMarkers(result.correctAnswer) : []}
        />
      )}

      {!result ? (
        <>
          <div className="flex flex-wrap gap-2">
            {choices.map((choice) => (
              <button
                key={choice}
                type="button"
                onClick={() => setSelected(choice)}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-sm transition-colors",
                  selected === choice
                    ? "border-primary bg-indigo-50 dark:bg-indigo-950/40"
                    : "border-border hover:border-primary/60 dark:border-gray-700",
                )}
              >
                {t(`divergence.${choice}`)}
              </button>
            ))}
          </div>
          <Button disabled={!selected || pending} onClick={() => selected && onSubmit({ divergence: selected })}>
            {t("exercise.submit")}
          </Button>
        </>
      ) : (
        <AttemptResult
          correct={result.correct}
          correctAnswer={divergence ? { text: t(`divergence.${divergence}`) } : null}
          solutionSteps={result.solutionSteps}
          explanation={result.explanation}
        />
      )}
    </div>
  );
}
