import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ExerciseType } from "@/api/course";
import type { Answer, AttemptPayload, Deferred, GradeResponse } from "@/api/exercises";
import { CandleChart } from "@/components/charts/CandleChart";
import { divergenceMarkers, patternBands, patternMarkers } from "@/components/charts/markers";
import { Button } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { AttemptResult } from "@/features/exercises/AttemptResult";

/** Interactive chart exercise. Divergence charts (`synthetic_chart`/`fixture_chart`) answer with a
 * `divergence`; the generic `pattern_chart` answers with a `label`. Choice buttons and the revealed
 * answer are localized (never raw injector ids), and overlays / price levels / OI all render.
 *
 * Practice passes onSubmit + result (grade inline). Exams pass `deferred` (capture-only); the exam
 * review passes a `result` to reveal the answer + markers, same as practice review. */
export function ChartExercise({
  type,
  payload,
  result,
  pending,
  onSubmit,
  deferred,
  hideVerdict = false,
}: {
  type: ExerciseType;
  payload: AttemptPayload;
  result: GradeResponse | null;
  pending?: boolean;
  onSubmit?: (answer: Answer) => void;
  deferred?: Deferred;
  hideVerdict?: boolean;
}) {
  const { t } = useTranslation();
  const isDivergence = type === "synthetic_chart" || type === "fixture_chart";
  const answerKey = isDivergence ? "divergence" : "label";
  const initialChoice =
    deferred?.value && answerKey in deferred.value
      ? (deferred.value as Record<string, string>)[answerKey]
      : null;
  const [selected, setSelected] = useState<string | null>(initialChoice);
  const choices = payload.choices ?? [];
  const choose = (choice: string) => {
    setSelected(choice);
    deferred?.onChange(isDivergence ? { divergence: choice } : { label: choice });
  };
  const labelNs = isDivergence ? "divergence" : "chartLabel";
  const label = (choice: string): string => t(`${labelNs}.${choice}`);

  const markers = !result
    ? []
    : isDivergence
      ? divergenceMarkers(result.correctAnswer)
      : patternMarkers(result.correctAnswer);
  // Shaded zones appear only once the answer is in — same rule as the markers, and for a stronger
  // reason: the question is "find the zone", so drawing it beforehand would BE the answer (m30).
  const bands = !result || isDivergence ? [] : patternBands(result.correctAnswer);

  const revealed =
    result && typeof (result.correctAnswer as { divergence?: string; label?: string })?.[answerKey] === "string"
      ? (result.correctAnswer as Record<string, string>)[answerKey]
      : null;

  return (
    <div className="mt-3 space-y-3">
      {payload.series && (
        <CandleChart
          series={payload.series}
          rsi={payload.rsi}
          macd={payload.macd}
          oi={payload.oi}
          cvd={payload.cvd}
          overlays={payload.overlays}
          levels={payload.levels}
          bands={bands}
          indicator={payload.indicator ?? "rsi"}
          markers={markers}
          rightOffset={8}
        />
      )}

      {!result ? (
        <>
          <div className="flex flex-wrap gap-2">
            {choices.map((choice) => (
              <button
                key={choice}
                type="button"
                onClick={() => choose(choice)}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-sm transition-colors",
                  selected === choice
                    ? "border-primary bg-indigo-50 dark:bg-indigo-950/40"
                    : "border-border hover:border-primary/60 dark:border-gray-700",
                )}
              >
                {label(choice)}
              </button>
            ))}
          </div>
          {onSubmit && (
            <Button
              disabled={!selected || !!pending}
              onClick={() => selected && onSubmit(isDivergence ? { divergence: selected } : { label: selected })}
            >
              {t("exercise.submit")}
            </Button>
          )}
        </>
      ) : (
        <AttemptResult
          correct={result.correct}
          correctAnswer={revealed ? { text: label(revealed) } : null}
          solutionSteps={result.solutionSteps}
          explanation={result.explanation}
          hideVerdict={hideVerdict}
        />
      )}
    </div>
  );
}
