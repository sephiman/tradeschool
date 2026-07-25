import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getCourse } from "@/api/course";
import {
  examHistory,
  getCurrentExam,
  startExam,
  type ExamScope,
  type ExamSession,
} from "@/api/exams";
import { Badge, Button, Card, Spinner } from "@/components/ui/primitives";

function pct(score: number | null): string {
  return score == null ? "—" : `${Math.round(score * 100)}%`;
}

export function ExamPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage;
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: current } = useQuery({ queryKey: ["exam", "current", lang], queryFn: getCurrentExam });
  const { data: course } = useQuery({ queryKey: ["course", lang], queryFn: getCourse });
  const { data: history, isLoading } = useQuery({ queryKey: ["exam", "history", lang], queryFn: examHistory });

  const start = useMutation({
    mutationFn: ({ scope, blockId }: { scope: ExamScope; blockId?: string }) => startExam(scope, blockId),
    onSuccess: (s: ExamSession) => {
      void qc.invalidateQueries({ queryKey: ["exam"] });
      navigate(`/exams/${s.id}`);
    },
  });

  const scopeName = (scope: ExamScope, blockTitle: string | null): string =>
    scope === "global" ? t("exam.global") : (blockTitle ?? t("exam.block"));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">{t("nav.exams")}</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("exam.intro")}</p>
      </div>

      {current && (
        <Card className="flex flex-wrap items-center justify-between gap-3 border-primary bg-primary/5 p-4 dark:bg-primary/10">
          <div>
            <p className="text-xs font-medium tracking-wide text-primary uppercase">{t("exam.inProgress")}</p>
            <p className="text-sm text-gray-600 dark:text-gray-300">
              {scopeName(current.scope, current.blockTitle)}
            </p>
          </div>
          <Button onClick={() => navigate(`/exams/${current.id}`)}>{t("exam.resume")}</Button>
        </Card>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
          {t("exam.startTitle")}
        </h2>
        <Card className="space-y-4 p-4">
          <div>
            <Button disabled={start.isPending} onClick={() => start.mutate({ scope: "global" })}>
              {t("exam.startGlobal")}
            </Button>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{t("exam.startGlobalHint")}</p>
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">{t("exam.startBlock")}</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {course?.blocks.map((b) => (
                <Button
                  key={b.id}
                  variant="secondary"
                  disabled={start.isPending}
                  onClick={() => start.mutate({ scope: "block", blockId: b.id })}
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
              <Link key={h.id} to={`/exams/${h.id}/review`} className="block">
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
