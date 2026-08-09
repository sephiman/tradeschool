import { useEffect, useMemo } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { completeLesson, getCourse, getGlossary, getLesson, type ExerciseType } from "@/api/course";
import { listAttempts } from "@/api/exercises";
import { Badge, Button, Spinner } from "@/components/ui/primitives";
import { ExercisePlayer } from "@/features/exercises/ExercisePlayer";
import { LessonFigure } from "@/features/course/LessonFigure";
import { GlossaryTerm, TermPopoverHost } from "@/features/glossary/TermPopover";
import { buildTermIndex } from "@/lib/glossary/terms";
import { currentAndNext, flattenLessons, stepLabel } from "@/features/course/courseNav";
import { formatReadingTime } from "@/features/course/readingTime";
import { LessonMarkdown } from "@/lib/markdown";

export function LessonPage() {
  const { t, i18n } = useTranslation();
  const { lessonId = "" } = useParams();
  const { hash } = useLocation();
  const queryClient = useQueryClient();
  const lang = i18n.resolvedLanguage;

  const { data: lesson, isLoading } = useQuery({
    queryKey: ["lesson", lessonId, lang],
    queryFn: () => getLesson(lessonId),
  });
  const { data: course } = useQuery({ queryKey: ["course", lang], queryFn: getCourse });
  // One fetch for the whole session, cached across lessons: the definitions the tooltips show, and
  // the term list the annotator matches on. A lesson still renders while it is in flight — the prose
  // simply has no marks yet.
  const { data: glossary } = useQuery({
    queryKey: ["glossary", lang],
    queryFn: () => getGlossary(lang ?? "en"),
    staleTime: Infinity,
  });
  const terms = useMemo(
    () => (glossary ? buildTermIndex(glossary.terms, lang ?? "en") : []),
    [glossary, lang],
  );
  const entriesById = useMemo(
    () => new Map((glossary?.terms ?? []).map((entry) => [entry.id, entry])),
    [glossary],
  );

  // Canonical order across module boundaries, so the lesson knows where "back" and "next" lead.
  const nav = useMemo(
    () => (course ? currentAndNext(flattenLessons(course), lessonId) : null),
    [course, lessonId],
  );

  const complete = useMutation({
    mutationFn: () => completeLesson(lessonId),
    meta: { successMessage: "course.markedComplete" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["lesson", lessonId] });
      void queryClient.invalidateQueries({ queryKey: ["course"] });
    },
  });

  // A "review" link from Progress arrives as /lessons/:id#ex-:exerciseId. The browser cannot honour
  // the fragment on first paint — the markdown, and the exercise players inside it, mount only once
  // the lesson query resolves — so the scroll is done here instead, and repeated after the figures
  // and charts above the anchor have finished laying out and pushing it down the page.
  const highlightedExerciseId = hash.startsWith("#ex-") ? hash.slice("#ex-".length) : null;
  useEffect(() => {
    if (!lesson || !hash) return;
    const scroll = () => document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
    scroll();
    const settle = window.setTimeout(scroll, 700);
    return () => window.clearTimeout(settle);
  }, [lesson, hash]);

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
      ? { to: `/lessons/${nav.next.lessonId}`, label: stepLabel(nav.next, lesson.moduleId) }
      : { to: "/stats", label: t("nav.progress") };

  // A lesson is atomic, so it shows its OWN full estimate — "remaining" is meaningless inside one, and
  // a lesson already marked read still tells you what re-reading it costs.
  const readingTime = formatReadingTime(lesson.readingSeconds, t);

  return (
    <article className="mx-auto max-w-2xl">
      <div className="flex items-baseline justify-between gap-3">
        <Link to={backTo} className="text-sm text-primary hover:underline">
          ← {backLabel}
        </Link>
        {readingTime !== null && (
          <span className="text-xs text-gray-500 dark:text-gray-400">{readingTime}</span>
        )}
      </div>
      <div className="mt-4">
        <TermPopoverHost entries={entriesById}>
          <LessonMarkdown
            markdown={lesson.markdown}
            renderExercise={(id) => {
              const type = typeById.get(id);
              return type ? (
                <ExercisePlayer exerciseId={id} type={type} highlighted={id === highlightedExerciseId} />
              ) : null;
            }}
            renderFigure={(id) => <LessonFigure id={id} />}
            glossary={{ lessonId, terms }}
            renderTerm={(termId, children) => <GlossaryTerm termId={termId}>{children}</GlossaryTerm>}
          />
        </TermPopoverHost>
      </div>
      {/* End-of-lesson panel. The button is the *only* thing that marks a lesson read — nothing is
          inferred from scrolling or dwell time — so it says so rather than sitting unexplained. */}
      <div className="mt-8 rounded-lg border border-border p-4 dark:border-gray-800 oled:border-oled-line">
        <div className="flex flex-wrap items-center gap-3">
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
        {!lesson.completed && (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{t("course.markCompleteHint")}</p>
        )}
      </div>
    </article>
  );
}
