import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { completeLesson, getCourse, getLesson, type ExerciseType } from "@/api/course";
import { listAttempts } from "@/api/exercises";
import { Badge, Button, Spinner } from "@/components/ui/primitives";
import { ExercisePlayer } from "@/features/exercises/ExercisePlayer";
import { LessonFigure } from "@/features/course/LessonFigure";
import { LessonMarkdown } from "@/lib/markdown";

export function LessonPage() {
  const { t, i18n } = useTranslation();
  const { lessonId = "" } = useParams();
  const queryClient = useQueryClient();
  const lang = i18n.resolvedLanguage;

  const { data: lesson, isLoading } = useQuery({
    queryKey: ["lesson", lessonId, lang],
    queryFn: () => getLesson(lessonId),
  });
  const { data: course } = useQuery({ queryKey: ["course", lang], queryFn: getCourse });

  // Canonical order across module boundaries, so the lesson knows where "back" and "next" lead.
  const nav = useMemo(() => {
    if (!course) return null;
    const flat = course.blocks.flatMap((b) =>
      b.modules.flatMap((m) =>
        m.lessons.map((l) => ({
          lessonId: l.id,
          lessonTitle: l.title,
          moduleId: m.id,
          moduleTitle: m.title,
          lessonsTotal: m.lessonsTotal,
        })),
      ),
    );
    const i = flat.findIndex((x) => x.lessonId === lessonId);
    return { current: i >= 0 ? flat[i] : null, next: i >= 0 ? (flat[i + 1] ?? null) : null };
  }, [course, lessonId]);

  const complete = useMutation({
    mutationFn: () => completeLesson(lessonId),
    meta: { successMessage: "course.markedComplete" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lesson", lessonId] });
      void queryClient.invalidateQueries({ queryKey: ["course"] });
    },
  });

  const typeById = useMemo(() => {
    const map = new Map<string, ExerciseType>();
    lesson?.exercises.forEach((e) => map.set(e.id, e.type));
    return map;
  }, [lesson]);

  // Reading completion is an explicit user action and never gated on exercises. As a soft nudge,
  // if any embedded exercise is still untried we ask for confirmation — but never block.
  async function onMarkComplete() {
    const ids = lesson?.exercises.map((e) => e.id) ?? [];
    if (ids.length > 0) {
      const lists = await Promise.all(ids.map((id) => listAttempts(id)));
      const anyUntried = lists.some((l) => l.length === 0);
      if (anyUntried && !window.confirm(t("course.markCompleteConfirm"))) return;
    }
    complete.mutate();
  }

  if (isLoading || !lesson) {
    return (
      <div className="flex justify-center py-16 text-gray-500">
        <Spinner />
      </div>
    );
  }

  // Single-lesson modules skip their page, so "back" returns to the course, not the skipped module.
  const singleLesson = !nav?.current || nav.current.lessonsTotal <= 1;
  const backTo = singleLesson ? "/course" : `/modules/${lesson.moduleId}`;
  const backLabel = singleLesson ? t("nav.course") : lesson.moduleTitle;
  // The next step is the next lesson in canonical order (across modules); on the last, the Progress page.
  const nextStep = !nav
    ? null
    : nav.next
      ? {
          to: `/lessons/${nav.next.lessonId}`,
          label:
            nav.next.moduleId !== lesson.moduleId
              ? `${nav.next.moduleId.toUpperCase()} · ${nav.next.moduleTitle}`
              : nav.next.lessonTitle,
        }
      : { to: "/stats", label: t("nav.progress") };

  return (
    <article className="mx-auto max-w-2xl">
      <Link to={backTo} className="text-sm text-primary hover:underline">
        ← {backLabel}
      </Link>
      <div className="mt-4">
        <LessonMarkdown
          markdown={lesson.markdown}
          renderExercise={(id) => {
            const type = typeById.get(id);
            return type ? <ExercisePlayer exerciseId={id} type={type} /> : null;
          }}
          renderFigure={(id) => <LessonFigure id={id} />}
        />
      </div>
      <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-border pt-6 dark:border-gray-800">
        {lesson.completed ? (
          <Badge tone="green">{t("course.completed")}</Badge>
        ) : (
          <Button onClick={() => void onMarkComplete()} disabled={complete.isPending}>
            {t("course.markComplete")}
          </Button>
        )}
        {nextStep && (
          <Link to={nextStep.to} className="ml-auto text-sm font-medium text-primary hover:underline">
            {t("course.next", { step: nextStep.label })} →
          </Link>
        )}
      </div>
    </article>
  );
}
