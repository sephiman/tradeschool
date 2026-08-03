import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getModule } from "@/api/course";
import { formatReadingTime, remainingSeconds } from "@/features/course/readingTime";
import { Badge, Card, Spinner } from "@/components/ui/primitives";

export function ModulePage() {
  const { t, i18n } = useTranslation();
  const { moduleId = "" } = useParams();
  const { data: module, isLoading } = useQuery({
    queryKey: ["module", moduleId, i18n.resolvedLanguage],
    queryFn: () => getModule(moduleId),
  });

  if (isLoading || !module) {
    return (
      <div className="flex justify-center py-16 text-gray-500">
        <Spinner />
      </div>
    );
  }

  // The same number the module's card on the course page shows: time left, from the same per-lesson
  // seconds, hidden entirely once the module is read.
  const timeLeft = formatReadingTime(remainingSeconds(module.lessons), t);

  return (
    <div className="space-y-6">
      <div>
        <Link to="/course" className="text-sm text-primary hover:underline">
          ← {t("nav.course")}
        </Link>
        <h1 className="mt-2 text-2xl font-bold">{module.title}</h1>
        <p className="mt-1 text-gray-500 dark:text-gray-400">{module.summary}</p>
        {timeLeft !== null && (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{timeLeft}</p>
        )}
      </div>

      {module.unmetPrereqs.length > 0 && module.lessons.some((l) => !l.completed) && (
        <p className="text-sm text-gray-400 dark:text-gray-500">
          {t("course.prereqNoticeLong")} {module.unmetPrereqs.map((p) => p.title ?? p.id).join(", ")}.
        </p>
      )}

      <div className="space-y-2">
        {module.lessons.map((lesson) => (
          <Link key={lesson.id} to={`/lessons/${lesson.id}`} className="block">
            <Card className="flex items-center justify-between gap-3 p-4 hover:border-primary">
              <span className="font-medium">{lesson.title}</span>
              {/* Each row carries the lesson's OWN full estimate — the same number its page shows, and
                  the reason the header's remaining total can be smaller: a read lesson still costs what
                  it costs, it just no longer counts as time left. */}
              <span className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {formatReadingTime(lesson.readingSeconds, t)}
                </span>
                {lesson.completed && <Badge tone="green">{t("course.completed")}</Badge>}
              </span>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
