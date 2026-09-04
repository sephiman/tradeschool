import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getCourse, type CourseBlock } from "@/api/course";
import {
  examHistory,
  getOpenExams,
  startExam,
  type ExamScope,
  type ExamSession,
} from "@/api/exams";
import { Badge, Button, Card, Spinner } from "@/components/ui/primitives";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { coursePath } from "@/components/layout/nav";

function pct(score: number | null): string {
  return score == null ? "—" : `${Math.round(score * 100)}%`;
}

/** The blocks an exam can be scoped to: one with no exercise bank anywhere in it is not one. */
function examinable(blocks: CourseBlock[] | undefined): CourseBlock[] {
  return (blocks ?? []).filter((b) => b.modules.some((m) => m.exercisesTotal > 0));
}

export function ExamPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage;
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: open } = useQuery({ queryKey: ["exam", "open", lang], queryFn: getOpenExams });
  const { data: course } = useQuery({ queryKey: ["course", lang], queryFn: getCourse });
  const { data: history, isLoading } = useQuery({ queryKey: ["exam", "history", lang], queryFn: examHistory });

  const start = useMutation({
    mutationFn: ({ scope, blockId }: { scope: ExamScope; blockId?: string }) => startExam(scope, blockId),
    onSuccess: (s: ExamSession) => {
      void qc.invalidateQueries({ queryKey: ["exam"] });
      navigate(coursePath(`/exams/${s.id}`));
    },
  });

  // What the reader asked to start, held back while they answer for the sitting it would abandon.
  const [pending, setPending] = useState<{ scope: ExamScope; blockId?: string } | null>(null);

  /**
   * The open sitting a start would destroy. The server abandons an open session of the SAME scope and
   * block and only that one, so this asks exactly when something is at stake and never otherwise — a
   * confirmation that fires when nothing would be lost is one readers learn to dismiss unread.
   */
  const conflicting = (scope: ExamScope, blockId?: string): ExamSession | null =>
    (open ?? []).find((s) => s.scope === scope && (s.blockId ?? undefined) === blockId) ?? null;

  /** Every start goes through here: ask if a sitting would be lost, otherwise just begin. */
  const requestStart = (scope: ExamScope, blockId?: string): void => {
    if (conflicting(scope, blockId)) setPending({ scope, blockId });
    else start.mutate({ scope, blockId });
  };

  const doomed = pending ? conflicting(pending.scope, pending.blockId) : null;

  const scopeName = (scope: ExamScope, blockTitle: string | null): string =>
    scope === "global" ? t("exam.global") : (blockTitle ?? t("exam.block"));

  const answered = (session: ExamSession): string =>
    t("exam.conflictAnswered", {
      done: session.questions.filter((q) => q.answered).length,
      total: session.questions.length,
    });

  return (
    <div className="space-y-8">
      {pending && doomed && (
        <ConfirmDialog
          title={t("exam.conflictTitle")}
          confirmLabel={t("exam.conflictStartNew")}
          cancelLabel={t("exam.conflictResume")}
          onConfirm={() => {
            const request = pending;
            setPending(null);
            start.mutate(request);
          }}
          onCancel={() => {
            setPending(null);
            navigate(coursePath(`/exams/${doomed.id}`));
          }}
          // Escape and the backdrop mean "I did not mean to press that", not "take me to the exam".
          onDismiss={() => setPending(null)}
        >
          <p className="font-medium text-gray-900 dark:text-gray-100">
            {scopeName(doomed.scope, doomed.blockTitle)} · {answered(doomed)}
          </p>
          <p>{t("exam.conflictBody")}</p>
        </ConfirmDialog>
      )}
      <div>
        <h1 className="text-2xl font-bold">{t("nav.exams")}</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("exam.intro")}</p>
      </div>

      {/* One card per open sitting: two scopes can be open at once, and the one that is not the
          newest used to be unreachable from here. */}
      {(open ?? []).map((sitting) => (
        <Card
          key={sitting.id}
          className="flex flex-wrap items-center justify-between gap-3 border-primary bg-primary/5 p-4 dark:bg-primary/10"
        >
          <div>
            <p className="text-xs font-medium tracking-wide text-primary uppercase">{t("exam.inProgress")}</p>
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {scopeName(sitting.scope, sitting.blockTitle)}
            </p>
          </div>
          <Button onClick={() => navigate(coursePath(`/exams/${sitting.id}`))}>{t("exam.resume")}</Button>
        </Card>
      ))}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
          {t("exam.startTitle")}
        </h2>
        <Card className="space-y-4 p-4">
          <div>
            <Button disabled={start.isPending} onClick={() => requestStart("global")}>
              {t("exam.startGlobal")}
            </Button>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t("exam.startGlobalHint")}</p>
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">{t("exam.startBlock")}</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {/* A block whose modules carry no exercise bank has nothing to grade — the epilogue
                  (block G) is one — and the server answers EXAM_EMPTY. Don't offer the button. */}
              {examinable(course?.blocks).map((b) => (
                <Button
                  key={b.id}
                  variant="secondary"
                  disabled={start.isPending}
                  onClick={() => requestStart("block", b.id)}
                  className="justify-start"
                >
                  {b.title}
                </Button>
              ))}
            </div>
          </div>
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
          {t("exam.historyTitle")}
        </h2>
        {isLoading ? (
          <div className="flex justify-center py-8 text-gray-500">
            <Spinner />
          </div>
        ) : !history?.length ? (
          <p className="text-sm text-gray-500 dark:text-gray-400">{t("exam.noHistory")}</p>
        ) : (
          <div className="space-y-2">
            {history.map((h) => (
              <Link key={h.id} to={coursePath(`/exams/${h.id}/review`)} className="block">
                <Card className="flex items-center justify-between gap-3 p-3 hover:border-primary">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{scopeName(h.scope, h.blockTitle)}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {h.finishedAt ? new Date(h.finishedAt).toLocaleDateString(lang) : "—"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {h.correct}/{h.total}
                    </span>
                    <Badge tone="indigo">{pct(h.score)}</Badge>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
