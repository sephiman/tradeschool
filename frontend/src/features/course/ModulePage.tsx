import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getModule } from "@/api/course";
import { Badge, Card, Spinner } from "@/components/ui/primitives";

export function ModulePage() {
  const { t } = useTranslation();
  const { moduleId = "" } = useParams();
  const { data: module, isLoading } = useQuery({
    queryKey: ["module", moduleId],
    queryFn: () => getModule(moduleId),
  });

  if (isLoading || !module) {
    return (
      <div className="flex justify-center py-16 text-gray-500">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link to="/course" className="text-sm text-primary hover:underline">
          ← {t("nav.course")}
        </Link>
        <h1 className="mt-2 text-2xl font-bold">{module.title}</h1>
        <p className="mt-1 text-gray-500 dark:text-gray-400">{module.summary}</p>
      </div>

      {module.unmetPrereqs.length > 0 && module.lessons.some((l) => !l.completed) && (
        <p className="text-sm text-gray-400 dark:text-gray-500">
          {t("course.prereqNoticeLong")} {module.unmetPrereqs.map((p) => p.title ?? p.id).join(", ")}.
        </p>
      )}

      <div className="space-y-2">
        {module.lessons.map((lesson) => (
          <Link key={lesson.id} to={`/lessons/${lesson.id}`} className="block">
            <Card className="flex items-center justify-between p-4 hover:border-primary">
              <span className="font-medium">{lesson.title}</span>
              {lesson.completed && <Badge tone="green">{t("course.completed")}</Badge>}
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
