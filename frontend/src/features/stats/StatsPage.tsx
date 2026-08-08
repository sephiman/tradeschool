import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { getGlobalStats, getMeStats, type ModuleStat, type ReviewTarget } from "@/api/stats";
import { Card, MiniBar, Spinner } from "@/components/ui/primitives";
import { MIN_N_FOR_PERCENT, partitionModules, rate, rateShort } from "@/features/stats/format";
import { coursePath } from "@/components/layout/nav";

/** A census over a known total (lessons marked, exercises passed) — exact, so never a fraction. */
function censusPct(value: number | null): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

/** The first-attempt clause, always carrying its own denominator and its unit. */
function firstAttemptClause(t: TFunction, num: number, den: number): string {
  const r = rate(num, den);
  if (r.kind === "none") return "—";
  return r.kind === "fraction"
    ? t("stats.firstAttemptFraction", { num: r.num, total: r.den })
    : t("stats.firstAttemptPercent", { percent: r.percent, total: r.den });
}

function StatTile({ label, value, note, bar }: { label: string; value: string; note?: string; bar?: ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold tabular-nums">{value}</span>
        {bar}
      </div>
      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{label}</div>
      {note && <div className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{note}</div>}
    </Card>
  );
}

const MAX_REVIEW_LINKS = 4;

/** Links from "you struggle here" to the exercise inside its lesson — the ordinary practice player. */
function ReviewLinks({ moduleId, targets }: { moduleId: string; targets: ReviewTarget[] }) {
  const { t } = useTranslation();
  if (targets.length === 0) return null;
  const shown = targets.slice(0, MAX_REVIEW_LINKS);
  const extra = targets.length - shown.length;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {shown.map((r) => (
        <Link
          key={r.exerciseId}
          to={r.lessonId ? `/lessons/${r.lessonId}#ex-${r.exerciseId}` : `/modules/${moduleId}`}
          title={t(r.passed ? "stats.reviewSolved" : "stats.reviewPending")}
          className={
            r.passed
              ? "rounded border border-border px-1.5 py-0.5 font-mono text-xs text-gray-500 hover:border-primary hover:text-primary dark:border-gray-700 dark:text-gray-400"
              : "rounded border border-border px-1.5 py-0.5 font-mono text-xs text-primary hover:border-primary dark:border-gray-700"
          }
        >
          {r.exerciseId}
        </Link>
      ))}
      {extra > 0 && (
        <Link to={coursePath(`/modules/${moduleId}`)} className="text-xs text-primary hover:underline">
          {t("stats.reviewMore", { extra })}
        </Link>
      )}
    </span>
  );
}

function ModuleRow({ m }: { m: ModuleStat }) {
  return (
    <tr className="border-t border-border dark:border-gray-800 oled:border-oled-line">
      <td className="py-1.5 pr-2">{m.title ?? m.id}</td>
      <td className="py-1.5 pl-2">
        <span className="flex items-center justify-end gap-2 tabular-nums">
          <MiniBar value={m.lessonsCompleted} total={m.lessonsTotal} />
          {m.lessonsCompleted}/{m.lessonsTotal}
        </span>
      </td>
      <td className="py-1.5 pl-2">
        <span className="flex items-center justify-end gap-2 tabular-nums">
          <MiniBar value={m.exercisesPassed} total={m.exercisesTotal} />
          {m.exercisesPassed}/{m.exercisesTotal}
        </span>
      </td>
      <td className="py-1.5 pl-2 text-right tabular-nums">{rateShort(m.correct, m.answered)}</td>
      <td className="py-1.5 pl-2 text-right tabular-nums">{rateShort(m.firstCorrect, m.firstSeen)}</td>
      <td className="py-1.5 pl-2 text-right">
        <ReviewLinks moduleId={m.id} targets={m.toReview} />
      </td>
    </tr>
  );
}

const TABLE_COLUMNS = 6;

export function StatsPage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.resolvedLanguage;
  // Keyed by locale like every other page: module titles come back localized, so a language switch
  // has to refetch or the table keeps rendering the previous language's titles.
  const me = useQuery({ queryKey: ["stats", "me", lang], queryFn: getMeStats });
  const global = useQuery({ queryKey: ["stats", "global", lang], queryFn: getGlobalStats });
  const [showUntouched, setShowUntouched] = useState(false);

  if (me.isLoading || !me.data) {
    return (
      <div className="flex justify-center py-16 text-gray-500">
        <Spinner />
      </div>
    );
  }

  const { coverage, thresholds, reading, exercise, modules, costliestSections } = me.data;
  const hasActivity = reading.lessonsCompleted > 0 || exercise.answered > 0;
  const { touched, untouched } = partitionModules(modules);
  // The explainer only earns its space while something on screen is actually a fraction.
  const showSampleNote =
    rate(exercise.correct, exercise.answered).kind === "fraction" ||
    rate(exercise.firstCorrect, exercise.firstSeen).kind === "fraction";

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
            <h2 className="mb-1 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
              {t("stats.reading")}
            </h2>
            {/* Says what the counter measures, so "0/35" can't be read as "you have read nothing". */}
            <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">{t("stats.readingNote")}</p>
            <div className="grid grid-cols-2 gap-3">
              <StatTile
                label={t("stats.lessonsMarked")}
                value={`${reading.lessonsCompleted}/${reading.lessonsTotal}`}
                bar={<MiniBar value={reading.lessonsCompleted} total={reading.lessonsTotal} />}
              />
              <StatTile label={t("stats.courseMarked")} value={censusPct(reading.courseCompletion)} />
            </div>
          </section>

          <section>
            <h2 className="mb-1 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
              {t("stats.mastery")}
            </h2>
            {showSampleNote && (
              <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                {t("stats.smallSample", { min: MIN_N_FOR_PERCENT })}
              </p>
            )}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatTile label={t("stats.answered")} value={String(exercise.answered)} />
              <StatTile
                label={t("stats.accuracy")}
                value={rateShort(exercise.correct, exercise.answered)}
                note={t("stats.overAnswers", { count: exercise.answered })}
              />
              <StatTile
                label={t("stats.firstAttempt")}
                value={rateShort(exercise.firstCorrect, exercise.firstSeen)}
                note={t("stats.overExercises", { count: exercise.firstSeen })}
              />
              <StatTile
                label={t("stats.avgAttempts")}
                value={exercise.avgAttemptsToSuccess == null ? "—" : exercise.avgAttemptsToSuccess.toFixed(1)}
              />
            </div>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
              {t("stats.costliest")}
            </h2>
            {costliestSections.length === 0 ? (
              // An empty panel that admits it beats a confident ranking built on one data point.
              <Card className="p-4 text-sm text-gray-500 dark:text-gray-400">
                {t("stats.costliestNeedsData", { min: thresholds.minExercisesToRank })}
              </Card>
            ) : (
              <div className="space-y-2">
                {costliestSections.map((c) => (
                  <Card key={c.moduleId} className="p-3 text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                      <span className="font-medium">{c.title ?? c.moduleId}</span>
                      {/* One interpolated string, both denominators spelled out — the two halves
                          can no longer be read as sharing one. */}
                      <span className="text-gray-500 dark:text-gray-400">
                        {t("stats.costliestLine", {
                          wrong: c.incorrect,
                          answers: c.answered,
                          first: firstAttemptClause(t, c.firstCorrect, c.firstSeen),
                        })}
                      </span>
                    </div>
                    {c.toReview.length > 0 && (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span className="text-xs text-gray-400 dark:text-gray-500">{t("stats.review")}</span>
                        <ReviewLinks moduleId={c.moduleId} targets={c.toReview} />
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-1 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
              {t("stats.byModule")}
            </h2>
            <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">{t("stats.byModuleNote")}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-gray-500 dark:text-gray-400">
                  <tr>
                    <th className="py-1 pr-2">{t("stats.module")}</th>
                    <th className="py-1 pl-2 text-right">{t("stats.lessonsMarkedShort")}</th>
                    <th className="py-1 pl-2 text-right">{t("stats.exercisesPassed")}</th>
                    {/* Each rate column names its own denominator, so a row cannot be read as two
                        figures over one population — the "1 wrong · 100% first-attempt" trap. */}
                    <th className="py-1 pl-2 text-right align-bottom">
                      <span className="block">{t("stats.accuracy")}</span>
                      <span className="block font-normal text-gray-400 dark:text-gray-500">
                        {t("stats.unitAnswers")}
                      </span>
                    </th>
                    <th className="py-1 pl-2 text-right align-bottom">
                      <span className="block">{t("stats.firstAttempt")}</span>
                      <span className="block font-normal text-gray-400 dark:text-gray-500">
                        {t("stats.unitExercises")}
                      </span>
                    </th>
                    <th className="py-1 pl-2 text-right">{t("stats.review")}</th>
                  </tr>
                </thead>
                <tbody>
                  {touched.map((m) => (
                    <ModuleRow key={m.id} m={m} />
                  ))}
                  {/* Modules with nothing in them collapse to one line, so the few rows that carry
                      the learner's actual story are not buried under two dozen "0/x — —". */}
                  {untouched.length > 0 && (
                    <tr className="border-t border-border dark:border-gray-800 oled:border-oled-line">
                      <td colSpan={TABLE_COLUMNS} className="py-1.5">
                        <button
                          type="button"
                          aria-expanded={showUntouched}
                          onClick={() => setShowUntouched((v) => !v)}
                          className="text-xs text-gray-500 hover:text-primary dark:text-gray-400"
                        >
                          {showUntouched ? "▾" : "▸"} {t("stats.notStarted", { count: untouched.length })}
                        </button>
                      </td>
                    </tr>
                  )}
                  {showUntouched && untouched.map((m) => <ModuleRow key={m.id} m={m} />)}
                </tbody>
              </table>
            </div>
          </section>

          {/* The cohort view lives behind the same activity guard as everything above it, so a
              brand-new account still sees one "nothing yet" card rather than two. */}
          {global.data && (
            <section>
              <h2 className="mb-1 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
                {t("stats.globalTitle")}
              </h2>
              {/* The hint carries both denominators for the whole list, the way byModuleNote does
                  for the table: the rate is over first attempts, the headcount is over people. */}
              <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                {t("stats.globalHint", { min: global.data.thresholds.minLearners })}
              </p>
              {global.data.modules.length === 0 ? (
                // Same honest empty state as "your costliest sections". Below the gate this panel
                // would not be aggregate at all: at two learners you subtract yourself and read the
                // other one's results off the row.
                <Card className="p-4 text-sm text-gray-500 dark:text-gray-400">
                  {t("stats.globalNeedsData", { min: global.data.thresholds.minLearners })}
                </Card>
              ) : (
                <div className="space-y-1">
                  {global.data.modules.slice(0, 5).map((m) => (
                    <div key={m.moduleId} className="flex items-center justify-between gap-2 text-sm">
                      <span>{m.title ?? m.moduleId}</span>
                      <span className="text-gray-500 tabular-nums dark:text-gray-400">
                        {rateShort(m.firstCorrect, m.firstSeen)} · {t("stats.nUsers", { count: m.learners })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
