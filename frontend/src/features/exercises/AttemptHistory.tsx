import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getAttempt, listAttempts, type AttemptReview } from "@/api/exercises";
import { CandleChart } from "@/components/charts/CandleChart";
import { divergenceMarkers } from "@/components/charts/markers";
import { AttemptResult } from "@/features/exercises/AttemptResult";
import { formatDateTime } from "@/lib/dates";
import { Prose } from "@/lib/markdown";
import { cn } from "@/lib/cn";

const CHART_TYPES = new Set(["synthetic_chart", "fixture_chart"]);

/** Chart answers are {divergence,…} objects — render the translated label, not the object. */
function reviewCorrectAnswer(review: AttemptReview, t: (k: string) => string): unknown {
  if (CHART_TYPES.has(review.type)) {
    const div = (review.correctAnswer as { divergence?: string })?.divergence;
    return div ? { text: t(`divergence.${div}`) } : null;
  }
  return review.correctAnswer;
}

export function AttemptHistory({ exerciseId }: { exerciseId: string }) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<string | null>(null);

  const { data: attempts } = useQuery({
    queryKey: ["attempts", exerciseId],
    queryFn: () => listAttempts(exerciseId),
  });
  const { data: review } = useQuery({
    queryKey: ["attempt", selected],
    queryFn: () => getAttempt(selected as string),
    enabled: selected != null,
  });

  const answered = (attempts ?? []).filter((a) => a.state === "answered");
  if (answered.length === 0) return null;

  return (
    <details className="mt-4 border-t border-border pt-3 dark:border-gray-800">
      <summary className="cursor-pointer text-sm font-medium text-gray-600 dark:text-gray-300">
        {t("exercise.history", { count: answered.length })}
      </summary>
      <ul className="mt-2 space-y-1">
        {answered.map((a, index) => (
          <li key={a.attemptId}>
            <button
              type="button"
              onClick={() => setSelected(a.attemptId === selected ? null : a.attemptId)}
              className="flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <span className="text-gray-500 dark:text-gray-400">
                {formatDateTime(a.createdAt)}
                {index === answered.length - 1 ? ` · ${t("exercise.firstAttempt")}` : ""}
              </span>
              <span className={cn("font-medium", a.isCorrect ? "text-emerald-600" : "text-red-600")}>
                {a.isCorrect ? t("exercise.correct") : t("exercise.incorrect")}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {review && review.attemptId === selected && (
        // Scoped strictly to this expanded item — its own chart instance, independent of any
        // fresh attempt in progress above; collapsing unmounts it and cleans up.
        <div className="mt-2 rounded-md bg-gray-50 p-3 dark:bg-gray-900/50">
          <Prose markdown={review.prompt} />
          {CHART_TYPES.has(review.type) && review.payload.series && (
            <div className="mt-2">
              <CandleChart
                series={review.payload.series}
                rsi={review.payload.rsi}
                macd={review.payload.macd}
                indicator={review.payload.indicator ?? "rsi"}
                markers={divergenceMarkers(review.correctAnswer)}
                height={320}
              />
            </div>
          )}
          <AttemptResult
            correct={review.isCorrect ?? false}
            correctAnswer={reviewCorrectAnswer(review, t)}
            solutionSteps={review.solutionSteps}
            explanation={review.explanation}
          />
        </div>
      )}
    </details>
  );
}
