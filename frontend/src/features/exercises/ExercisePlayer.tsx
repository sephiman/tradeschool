import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { ExerciseType } from "@/api/course";
import { answerAttempt, createAttempt, type Answer, type AttemptInstance, type GradeResponse } from "@/api/exercises";
import { Badge, Button, Card } from "@/components/ui/primitives";
import { AttemptHistory } from "@/features/exercises/AttemptHistory";
import { AttemptResult } from "@/features/exercises/AttemptResult";
import { CalculationExercise } from "@/features/exercises/CalculationExercise";
import { ChartExercise } from "@/features/exercises/ChartExercise";
import { QuizExercise } from "@/features/exercises/QuizExercise";
import { Prose } from "@/lib/markdown";
import { cn } from "@/lib/cn";

const CHART_TYPES: ReadonlySet<ExerciseType> = new Set([
  "synthetic_chart",
  "fixture_chart",
  "pattern_chart",
]);

export function ExercisePlayer({
  exerciseId,
  type,
  highlighted = false,
}: {
  exerciseId: string;
  type: ExerciseType;
  /** Outlined because a link (today: Progress → review) pointed the learner at this exercise. */
  highlighted?: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [instance, setInstance] = useState<AttemptInstance | null>(null);
  const [result, setResult] = useState<GradeResponse | null>(null);

  const start = useMutation({
    mutationFn: () => createAttempt(exerciseId),
    meta: { silentSuccess: true },
    onSuccess: (inst) => {
      setResult(null);
      setInstance(inst);
    },
  });

  const answer = useMutation({
    mutationFn: (a: Answer) => answerAttempt(instance!.attemptId, a),
    meta: { silentSuccess: true },
    onSuccess: (res) => {
      setResult(res);
      void queryClient.invalidateQueries({ queryKey: ["attempts", exerciseId] });
    },
  });

  return (
    // The anchor a Progress "review" link addresses. `highlighted` is driven by the URL fragment
    // rather than CSS `:target`, which never resolves here: the player mounts after the lesson
    // query settles, by which point the browser has already given up on the fragment.
    <Card
      id={`ex-${exerciseId}`}
      className={cn("my-4 scroll-mt-4 p-4", highlighted && "ring-2 ring-primary")}
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-gray-400">{exerciseId}</span>
        <Badge tone="indigo">{t(`exerciseType.${type}`)}</Badge>
      </div>

      {!instance ? (
        <div className="mt-3">
          <Button onClick={() => start.mutate()} disabled={start.isPending}>
            {t("exercise.start")}
          </Button>
        </div>
      ) : (
        <div className="mt-3">
          <Prose markdown={instance.prompt} />
          {CHART_TYPES.has(instance.type) ? (
            <ChartExercise
              type={instance.type}
              payload={instance.payload}
              result={result}
              pending={answer.isPending}
              onSubmit={(a) => answer.mutate(a)}
            />
          ) : !result ? (
            instance.type === "quiz" ? (
              <QuizExercise
                payload={instance.payload}
                pending={answer.isPending}
                onSubmit={(a) => answer.mutate(a)}
              />
            ) : (
              <CalculationExercise
                options={instance.payload.options ?? []}
                unit={instance.payload.unit}
                formula={instance.payload.formula}
                pending={answer.isPending}
                onSubmit={(a) => answer.mutate(a)}
              />
            )
          ) : (
            <AttemptResult
              correct={result.correct}
              correctAnswer={result.correctAnswer}
              solutionSteps={result.solutionSteps}
              explanation={result.explanation}
            />
          )}
          {result && (
            <Button className="mt-4" variant="secondary" onClick={() => start.mutate()} disabled={start.isPending}>
              {t("exercise.tryAgain")}
            </Button>
          )}
        </div>
      )}
      <AttemptHistory exerciseId={exerciseId} />
    </Card>
  );
}
