import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import type { ExerciseType } from "@/api/course";
import { reviewExam, type ExamQuestion } from "@/api/exams";
import { Badge, Card, Spinner } from "@/components/ui/primitives";
import { AttemptResult } from "@/features/exercises/AttemptResult";
import { ChartExercise } from "@/features/exercises/ChartExercise";
import { cn } from "@/lib/cn";
import { Prose } from "@/lib/markdown";
import { coursePath } from "@/components/layout/nav";
import { ProseReferenceHost } from "@/features/references/ProseReferenceHost";

const CHART_TYPES: ReadonlySet<ExerciseType> = new Set(["synthetic_chart", "fixture_chart", "pattern_chart"]);

function pct(score: number | null): string {
  return score == null ? "—" : `${Math.round(score * 100)}%`;
}

/** Best-effort readable rendering of the learner's own answer, using the question payload. */
function answerText(q: ExamQuestion, t: TFunction): string {
  const a = q.givenAnswer;
  if (!a) return t("exam.unanswered");
  const opts = q.payload.options ?? [];
  const text = (id: string): string => {
    const o = opts.find((x) => x.id === id);
    return o ? String(o.text ?? o.value ?? id) : id;
  };
  if ("optionId" in a) return text(a.optionId);
  if ("optionIds" in a) return a.optionIds.map(text).join(", ");
  if ("value" in a) return a.value ? t("exercise.true") : t("exercise.false");
  if ("order" in a) {
    const items = q.payload.items ?? [];
    return a.order.map((id) => String(items.find((i) => i.id === id)?.text ?? id)).join(" → ");
  }
  if ("pairs" in a) {
    const lefts = q.payload.lefts ?? [];
    const rights = q.payload.rights ?? [];
    return Object.entries(a.pairs)
      .map(([l, r]) => `${lefts.find((x) => x.id === l)?.text ?? l} → ${rights.find((x) => x.id === r)?.text ?? r}`)
      .join("; ");
  }
  if ("divergence" in a) return t(`divergence.${a.divergence}`);
  if ("label" in a) return t(`chartLabel.${a.label}`);
  return "";
}

function StatusBadge({ q, t }: { q: ExamQuestion; t: TFunction }) {
  if (q.unanswered) return <Badge tone="neutral">{t("exam.unanswered")}</Badge>;
  return q.isCorrect ? (
    <Badge tone="green">{t("exercise.correct")}</Badge>
  ) : (
    <Badge tone="red">{t("exercise.incorrect")}</Badge>
  );
}

export function ExamReview() {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage;
  const { examId = "" } = useParams();

  const { data: exam, isLoading, isError } = useQuery({
    queryKey: ["exam", examId, "review", lang],
    queryFn: () => reviewExam(examId),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-gray-500">
        <Spinner />
      </div>
    );
  }
  if (isError || !exam || !exam.result) {
    return (
      <div className="py-16 text-center text-gray-500">
        <p>{t("exam.notFound")}</p>
        <Link to={coursePath("/exams")} className="text-sm text-primary hover:underline">
          ← {t("nav.exams")}
        </Link>
      </div>
    );
  }

  const r = exam.result;
  const scopeName = exam.scope === "global" ? t("exam.global") : (exam.blockTitle ?? t("exam.block"));

  return (
    <ProseReferenceHost>
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <Link to={coursePath("/exams")} className="text-sm text-primary hover:underline">
          ← {t("nav.exams")}
        </Link>
        <h1 className="mt-2 text-2xl font-bold">{scopeName}</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {exam.finishedAt ? new Date(exam.finishedAt).toLocaleDateString(lang) : ""}
        </p>
      </div>

      {/* Score — plain, honest numbers. No pass/fail, no badges/confetti. */}
      <Card className="p-4">
        <div className="flex items-baseline gap-3">
          <span className="text-3xl font-bold tabular-nums">{pct(r.score)}</span>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {t("exam.scoreLine", { correct: r.correct, total: r.total })}
          </span>
        </div>

        {r.blocks.length > 1 && (
          <div className="mt-4 space-y-1">
            <p className="text-xs font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
              {t("exam.byBlock")}
            </p>
            {r.blocks.map((b) => (
              <div key={b.blockId} className="flex items-center justify-between text-sm">
                <span className="text-gray-600 dark:text-gray-300">{b.title}</span>
                <span className="tabular-nums text-gray-500 dark:text-gray-400">
                  {pct(b.score)} <span className="text-xs">({b.correct}/{b.total})</span>
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 space-y-1">
          <p className="text-xs font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
            {t("exam.byModule")}
          </p>
          {r.modules.map((m) => (
            <div key={m.moduleId} className="flex items-center gap-2 text-sm">
              <span
                aria-hidden
                className={cn(
                  "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
                  m.unanswered
                    ? "bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400"
                    : m.correct
                      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
                      : "bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300",
                )}
              >
                {m.unanswered ? "◦" : m.correct ? "✓" : "✗"}
              </span>
              <span className="text-gray-600 dark:text-gray-300">{m.title}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Per-question review — your answer, the correct answer, and the worked solution, in bulk. */}
      <div className="space-y-4">
        {exam.questions.map((q) => {
          const result = {
            attemptId: q.attemptId,
            correct: !!q.isCorrect,
            correctAnswer: q.correctAnswer,
            solutionSteps: q.solutionSteps,
            explanation: q.explanation,
          };
          return (
            <Card key={q.attemptId} className="p-4">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs text-gray-400">
                  <span className="font-mono">{q.moduleId.toUpperCase()}</span> · {q.moduleTitle}
                </p>
                <StatusBadge q={q} t={t} />
              </div>
              <div className="mt-2">
                <Prose markdown={q.prompt} />
              </div>
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                <span className="font-medium">{t("exam.yourAnswer")}:</span>{" "}
                <span className={cn(q.unanswered && "text-gray-400 italic dark:text-gray-500")}>
                  {answerText(q, t)}
                </span>
              </p>
              {CHART_TYPES.has(q.type) ? (
                <ChartExercise type={q.type} payload={q.payload} result={result} hideVerdict={!!q.unanswered} />
              ) : (
                <AttemptResult
                  correct={result.correct}
                  correctAnswer={result.correctAnswer}
                  solutionSteps={result.solutionSteps}
                  explanation={result.explanation}
                  hideVerdict={!!q.unanswered}
                />
              )}
            </Card>
          );
        })}
      </div>
    </div>
    </ProseReferenceHost>
  );
}
