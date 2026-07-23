import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getGlobalStats, getMeStats } from "@/api/stats";
import { Card, Spinner } from "@/components/ui/primitives";

function pct(value: number | null): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-4">
      <div className="text-2xl font-bold tabular-nums">{value}</div>
      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{label}</div>
    </Card>
  );
}

export function StatsPage() {
  const { t } = useTranslation();
  const me = useQuery({ queryKey: ["stats", "me"], queryFn: getMeStats });
  const global = useQuery({ queryKey: ["stats", "global"], queryFn: getGlobalStats });

  if (me.isLoading || !me.data) {
    return (
      <div className="flex justify-center py-16 text-gray-500">
        <Spinner />
      </div>
    );
  }

  const { coverage, reading, exercise, modules, costliestSections } = me.data;
  const hasActivity = reading.lessonsCompleted > 0 || exercise.answered > 0;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">{t("nav.progress")}</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("stats.intro")}</p>
        <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
          {t("stats.coverage", { published: coverage.publishedModules, total: coverage.totalModules })}
        </p>
      </div>

      {!hasActivity ? (
        <Card className="p-6 text-sm text-gray-500 dark:text-gray-400">{t("stats.empty")}</Card>
      ) : (
        <>
          {/* Reading (completion) and mastery (exercises) are shown as two separate rows. */}
          <section>
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
              {t("stats.reading")}
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <StatTile label={t("stats.courseCompletion")} value={pct(reading.courseCompletion)} />
              <StatTile
                label={t("stats.lessonsRead")}
                value={`${reading.lessonsCompleted}/${reading.lessonsTotal}`}
              />
            </div>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
              {t("stats.mastery")}
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile label={t("stats.answered")} value={String(exercise.answered)} />
              <StatTile label={t("stats.accuracy")} value={pct(exercise.accuracy)} />
              <StatTile label={t("stats.firstAttempt")} value={pct(exercise.firstAttemptAccuracy)} />
              <StatTile
                label={t("stats.avgAttempts")}
                value={exercise.avgAttemptsToSuccess == null ? "—" : exercise.avgAttemptsToSuccess.toFixed(1)}
              />
            </div>
          </section>

          {costliestSections.length > 0 && (
            <section>
              <h2 className="mb-2 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
                {t("stats.costliest")}
              </h2>
              <div className="space-y-2">
                {costliestSections.map((c) => (
                  <Card key={c.moduleId} className="flex items-center justify-between p-3 text-sm">
                    <span className="font-medium">{c.title ?? c.moduleId}</span>
                    <span className="text-gray-500 dark:text-gray-400">
                      {t("stats.incorrectCount", { count: c.incorrect })} · {t("stats.firstAttempt")}{" "}
                      {pct(c.firstAttemptAccuracy)}
                    </span>
                  </Card>
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
              {t("stats.byModule")}
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-gray-500 dark:text-gray-400">
                  <tr>
                    <th className="py-1">{t("nav.course")}</th>
                    <th className="py-1 text-right">{t("stats.lessonsRead")}</th>
                    <th className="py-1 text-right">{t("stats.exercisesPassed")}</th>
                    <th className="py-1 text-right">{t("stats.accuracy")}</th>
                    <th className="py-1 text-right">{t("stats.firstAttempt")}</th>
                  </tr>
                </thead>
                <tbody>
                  {modules.map((m) => (
                    <tr key={m.id} className="border-t border-border dark:border-gray-800">
                      <td className="py-1.5">{m.title ?? m.id}</td>
                      <td className="py-1.5 text-right tabular-nums">
                        {m.lessonsCompleted}/{m.lessonsTotal}
                      </td>
                      <td className="py-1.5 text-right tabular-nums">
                        {m.exercisesPassed}/{m.exercisesTotal}
                      </td>
                      <td className="py-1.5 text-right tabular-nums">{pct(m.accuracy)}</td>
                      <td className="py-1.5 text-right tabular-nums">{pct(m.firstAttemptAccuracy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {global.data && global.data.modules.length > 0 && (
        <section>
          <h2 className="mb-1 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
            {t("stats.globalTitle")}
          </h2>
          <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">{t("stats.globalHint")}</p>
          <div className="space-y-1">
            {global.data.modules.slice(0, 5).map((m) => (
              <div key={m.moduleId} className="flex items-center justify-between text-sm">
                <span>{m.title ?? m.moduleId}</span>
                <span className="text-gray-500 dark:text-gray-400">
                  {pct(m.firstAttemptAccuracy)} · {t("stats.nUsers", { count: m.attemptedByUsers })}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
