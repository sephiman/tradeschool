import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getCourse, type CourseModule } from "@/api/course";
import { Badge, Card, Spinner } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

function isComplete(m: CourseModule): boolean {
  return m.hasContent && m.lessonsTotal > 0 && m.lessonsCompleted >= m.lessonsTotal;
}

function ModuleCard({ module, suggested }: { module: CourseModule; suggested: boolean }) {
  const { t } = useTranslation();
  const complete = isComplete(module);
  // Advisory prereqs are soft: muted text, and never shown once the module is done.
  const showPrereqs = module.unmetPrereqs.length > 0 && !complete;

  const inner = (
    <Card className={cn("h-full p-4 transition-colors", suggested ? "border-primary ring-1 ring-primary" : module.hasContent ? "hover:border-primary" : "opacity-70")}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-semibold">
          <span className="text-gray-400">{module.id.toUpperCase()}</span> · {module.title}
        </h3>
        <div className="flex shrink-0 gap-1">
          {suggested && <Badge tone="indigo">{t("course.suggestedNext")}</Badge>}
          {complete && <Badge tone="green">{t("course.completed")}</Badge>}
          {!module.hasContent && <Badge tone="neutral">{t("course.comingSoon")}</Badge>}
        </div>
      </div>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{module.summary}</p>

      {module.hasContent && (
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          <span>{t("course.lessonProgress", { done: module.lessonsCompleted, total: module.lessonsTotal })}</span>
          {module.exercisesTotal > 0 && (
            <>
              {" · "}
              <span>{t("course.exerciseProgress", { done: module.exercisesPassed, total: module.exercisesTotal })}</span>
            </>
          )}
        </p>
      )}

      {showPrereqs && (
        <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
          {t("course.prereqNotice", { modules: module.unmetPrereqs.map((m) => m.toUpperCase()).join(", ") })}
        </p>
      )}
    </Card>
  );

  // A module with exactly one lesson has no useful intermediate page — jump straight to the lesson.
  // The module page is kept for the (data-model-supported) multi-lesson case.
  const target =
    module.lessonsTotal === 1 && module.lessons[0]
      ? `/lessons/${module.lessons[0].id}`
      : `/modules/${module.id}`;

  return module.hasContent ? (
    <Link to={target} className="block">
      {inner}
    </Link>
  ) : (
    <div>{inner}</div>
  );
}

export function CoursePage() {
  const { t } = useTranslation();
  const { data: course, isLoading } = useQuery({ queryKey: ["course"], queryFn: getCourse });

  // Suggested next = the first module in canonical order that isn't fully completed, whether or not
  // its content is published yet. It always points somewhere until the whole course is done.
  const suggestedModuleId = useMemo(() => {
    if (!course) return null;
    for (const block of course.blocks) {
      for (const module of block.modules) {
        if (!isComplete(module)) return module.id;
      }
    }
    return null;
  }, [course]);

  if (isLoading || !course) {
    return (
      <div className="flex justify-center py-16 text-gray-500">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">{t("nav.course")}</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{t("course.intro")}</p>
      </div>
      {course.blocks.map((block) => (
        <section key={block.id}>
          <h2 className="mb-3 text-sm font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
            {block.title}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {block.modules.map((module) => (
              <ModuleCard key={module.id} module={module} suggested={module.id === suggestedModuleId} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
