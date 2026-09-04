import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { ExerciseType } from "@/api/course";
import type { Answer } from "@/api/exercises";
import { abandonExam, answerExamQuestion, getExam, submitExam } from "@/api/exams";
import { Button, Card, Spinner } from "@/components/ui/primitives";
import { CalculationExercise } from "@/features/exercises/CalculationExercise";
import { ChartExercise } from "@/features/exercises/ChartExercise";
import { QuizExercise } from "@/features/exercises/QuizExercise";
import { cn } from "@/lib/cn";
import { Prose } from "@/lib/markdown";
import { coursePath } from "@/components/layout/nav";
import { ProseReferenceHost } from "@/features/references/ProseReferenceHost";

const CHART_TYPES: ReadonlySet<ExerciseType> = new Set(["synthetic_chart", "fixture_chart", "pattern_chart"]);

export function ExamRunner() {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage;
  const { examId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: exam, isLoading, isError } = useQuery({
    queryKey: ["exam", examId, lang],
    queryFn: () => getExam(examId),
    retry: false,
  });

  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [current, setCurrent] = useState(0);
  const seeded = useRef(false);

  useEffect(() => {
    if (exam && !seeded.current) {
      seeded.current = true;
      const seed: Record<string, Answer> = {};
      for (const q of exam.questions) if (q.givenAnswer) seed[q.attemptId] = q.givenAnswer;
      setAnswers(seed);
    }
  }, [exam]);

  // A closed/unknown session can't be run — send the learner back to the landing.
  useEffect(() => {
    if (isError) navigate(coursePath("/exams"), { replace: true });
  }, [isError, navigate]);

  const answerMut = useMutation({
    mutationFn: ({ attemptId, answer }: { attemptId: string; answer: Answer }) =>
      answerExamQuestion(examId, attemptId, answer),
    meta: { silentSuccess: true },
  });
  const submit = useMutation({
    mutationFn: () => submitExam(examId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["exam"] });
      navigate(coursePath(`/exams/${examId}/review`), { replace: true });
    },
  });
  const abandon = useMutation({
    mutationFn: () => abandonExam(examId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["exam"] });
      navigate(coursePath("/exams"), { replace: true });
    },
  });

  if (isLoading || !exam) {
    return (
      <div className="flex justify-center py-16 text-gray-500">
        <Spinner />
      </div>
    );
  }

  const questions = exam.questions;
  const q = questions[current];
  const answeredCount = questions.filter((x) => answers[x.attemptId] !== undefined).length;
  const unanswered = questions.length - answeredCount;

  const setAnswer = (attemptId: string, a: Answer) => {
    setAnswers((prev) => ({ ...prev, [attemptId]: a }));
    answerMut.mutate({ attemptId, answer: a });
  };

  const onSubmit = () => {
    const msg = unanswered > 0 ? t("exam.submitConfirmUnanswered", { count: unanswered }) : t("exam.submitConfirm");
    if (window.confirm(msg)) submit.mutate();
  };
  const onAbandon = () => {
    if (window.confirm(t("exam.abandonConfirm"))) abandon.mutate();
  };

  const deferred = { value: answers[q.attemptId] ?? null, onChange: (a: Answer) => setAnswer(q.attemptId, a) };

  return (
    <ProseReferenceHost>
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-lg font-semibold">
          {exam.scope === "global" ? t("exam.global") : (exam.blockTitle ?? t("exam.block"))}
        </h1>
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {t("exam.answeredOf", { done: answeredCount, total: questions.length })}
        </span>
      </div>

      {/* Progress strip — tappable question markers; answered filled, current ringed. Phone-friendly. */}
      <div className="flex flex-wrap gap-1.5">
        {questions.map((x, i) => {
          const isAnswered = answers[x.attemptId] !== undefined;
          return (
            <button
              key={x.attemptId}
              type="button"
              aria-label={`${i + 1}`}
              aria-current={i === current}
              onClick={() => setCurrent(i)}
              className={cn(
                "h-8 w-8 rounded-md border text-xs font-medium tabular-nums transition-colors",
                i === current && "ring-2 ring-primary ring-offset-1 dark:ring-offset-gray-900 oled:ring-offset-oled-bg",
                isAnswered
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border text-gray-600 hover:border-primary/60 dark:border-gray-700 dark:text-gray-300",
              )}
            >
              {i + 1}
            </button>
          );
        })}
      </div>

      <Card className="p-4">
        <p className="text-xs text-gray-400">
          <span className="font-mono">{q.moduleId.toUpperCase()}</span> · {q.moduleTitle}
        </p>
        <div className="mt-2">
          <Prose markdown={q.prompt} />
        </div>
        {CHART_TYPES.has(q.type) ? (
          <ChartExercise key={q.attemptId} type={q.type} payload={q.payload} result={null} deferred={deferred} />
        ) : q.type === "quiz" ? (
          <QuizExercise key={q.attemptId} payload={q.payload} deferred={deferred} />
        ) : (
          <CalculationExercise
            key={q.attemptId}
            options={q.payload.options ?? []}
            unit={q.payload.unit}
            formula={q.payload.formula}
            deferred={deferred}
          />
        )}
      </Card>

      <div className="flex items-center justify-between gap-2">
        <Button variant="secondary" disabled={current === 0} onClick={() => setCurrent((i) => i - 1)}>
          ← {t("exam.prev")}
        </Button>
        {current < questions.length - 1 ? (
          <Button variant="secondary" onClick={() => setCurrent((i) => i + 1)}>
            {t("exam.next")} →
          </Button>
        ) : (
          <Button disabled={submit.isPending} onClick={onSubmit}>
            {t("exam.submit")}
          </Button>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-border pt-4 dark:border-gray-800 oled:border-oled-line">
        <button
          type="button"
          onClick={onAbandon}
          className="text-xs text-gray-400 hover:text-red-600 dark:text-gray-500"
        >
          {t("exam.abandon")}
        </button>
        <Button variant="ghost" disabled={submit.isPending} onClick={onSubmit}>
          {t("exam.submit")}
        </Button>
      </div>
    </div>
    </ProseReferenceHost>
  );
}
