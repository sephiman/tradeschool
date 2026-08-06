import { apiClient } from "@/api/client";
// Type-only, so the pair `exercises.ts` -> `course.ts` -> `exercises.ts` never becomes a runtime cycle:
// a printed exercise carries exactly the payload an attempt would, and describing it twice would let
// the page and the screen drift apart.
import type { AttemptPayload, QuizKind } from "@/api/exercises";

export type ExerciseType =
  | "quiz"
  | "calculation"
  | "synthetic_chart"
  | "fixture_chart"
  | "pattern_chart";

export interface ExerciseRef {
  id: string;
  type: ExerciseType;
}

export interface CourseLesson {
  id: string;
  order: number;
  title: string;
  completed: boolean;
  /** Estimated reading time for THIS lesson in this locale, in seconds. Every module/block/course
   *  figure the UI shows is a sum of these — see features/course/readingTime.ts. */
  readingSeconds: number;
  exercises: ExerciseRef[];
}

export interface CourseModule {
  id: string;
  order: number;
  title: string;
  summary: string;
  assumes: string[];
  unmetPrereqs: string[];
  hasContent: boolean;
  lessonsTotal: number;
  lessonsCompleted: number;
  exercisesTotal: number;
  exercisesPassed: number;
  lessons: CourseLesson[];
}

export interface CourseBlock {
  id: string;
  order: number;
  title: string;
  modules: CourseModule[];
}

export interface CourseMeta {
  id: string;
  title: string;
  description: string;
}

export interface Course {
  locale: string;
  /** Whether the learner has begun (any lesson completed or any exercise attempted). */
  started: boolean;
  /** Root course identity (localized) — drives the course-page header. */
  course: CourseMeta;
  blocks: CourseBlock[];
}

export interface LessonDetail {
  id: string;
  title: string;
  moduleId: string;
  moduleTitle: string;
  blockId: string;
  markdown: string;
  completed: boolean;
  readingSeconds: number;
  exercises: ExerciseRef[];
}

export interface PrereqRef {
  id: string;
  title: string | null;
}

export interface ModuleDetail {
  id: string;
  title: string;
  summary: string;
  assumes: PrereqRef[];
  unmetPrereqs: PrereqRef[];
  lessons: { id: string; order: number; title: string; completed: boolean; readingSeconds: number }[];
}

export async function getCourse(): Promise<Course> {
  const { data } = await apiClient.get<Course>("/course");
  return data;
}

export async function getLesson(lessonId: string): Promise<LessonDetail> {
  const { data } = await apiClient.get<LessonDetail>(`/lessons/${lessonId}`);
  return data;
}

export async function completeLesson(lessonId: string): Promise<void> {
  await apiClient.post(`/lessons/${lessonId}/complete`);
}

export async function getModule(moduleId: string): Promise<ModuleDetail> {
  const { data } = await apiClient.get<ModuleDetail>(`/modules/${moduleId}`);
  return data;
}

/** The whole course as theory in ONE language — the shape `/course/export?lang=…` serves. Lesson
 *  markdown arrives with the `::exercise` directives already stripped server-side. */
export interface CourseExportLesson {
  id: string;
  title: string;
  markdown: string;
}

export interface CourseExportModule {
  id: string;
  title: string;
  summary: string;
  lessons: CourseExportLesson[];
}

export interface CourseExportBlock {
  id: string;
  title: string;
  modules: CourseExportModule[];
}

export interface CourseExport {
  locale: string;
  blocks: CourseExportBlock[];
}

/** The single-locale export document. `lang` is explicit: the PDF is built for the language being
 *  browsed, and an absent `lang` would hand back the bilingual document instead. */
export async function getCourseExport(locale: string): Promise<CourseExport> {
  const { data } = await apiClient.get<CourseExport>("/course/export", { params: { lang: locale } });
  return data;
}

/**
 * The course's exercises as they are PRINTED — the shape `/course/print/exercises?lang=…` serves.
 *
 * One frozen instance per exercise (generated at a seed derived from its id, so every export prints
 * the same book) plus the answer to *that* instance, which is what the answer key at the back is made
 * of. This is the one endpoint that hands over solutions; see its docstring for why that is the deal
 * an answer key strikes.
 */
export interface PrintAnswer {
  kind: QuizKind | "calculation" | "chart";
  /** Which printed options are correct (single_choice, multi_select, calculation). */
  optionIds?: string[];
  /** ordering: the printed item ids in their correct sequence. */
  order?: string[];
  /** matching: printed left id -> printed right id. */
  pairs?: Record<string, string>;
  /** true_false. */
  value?: boolean;
  /** calculation: the correct option's value, its unit, and the worked steps. */
  numericValue?: string;
  unit?: string | null;
  steps?: string[];
  /** chart: the raw label (localized here, never by the server) and the bars it is read at. */
  label?: string;
  anchors?: PrintAnchor[];
  zones?: PrintZone[];
  explanation?: string | null;
}

/** A ground-truth bar, priced out of the printed series — the key's link to the printed chart. */
export interface PrintAnchor {
  index: number;
  time: number;
  kind: string;
  label: string;
  price: number;
}

export interface PrintZone {
  low: number;
  high: number;
  kind: string;
  label: string;
}

export interface PrintExercise {
  id: string;
  /** The reader-facing label, derived from the id: `m11-ex-5` prints as `11.5`. */
  number: string;
  type: ExerciseType;
  isChart: boolean;
  seed: number;
  prompt: string;
  /** Exactly what an attempt would show — no markers, no zones, cut before the resolution. */
  payload: AttemptPayload;
  answer: PrintAnswer;
}

export interface PrintLesson {
  lessonId: string;
  moduleId: string;
  exercises: PrintExercise[];
}

export interface PrintExclusion {
  id: string;
  number: string;
  lessonId: string;
  type: string;
  reason: string;
}

export interface PrintExercises {
  locale: string;
  lessons: PrintLesson[];
  excluded: PrintExclusion[];
}

export async function getPrintExercises(locale: string): Promise<PrintExercises> {
  const { data } = await apiClient.get<PrintExercises>("/course/print/exercises", {
    params: { lang: locale },
  });
  return data;
}

export interface FigurePanel {
  series: { time: number[]; open: number[]; high: number[]; low: number[]; close: number[]; volume: number[] };
  rsi?: number[];
  macd?: { line: number[]; signal: number[]; hist: number[] };
  oi?: number[];
  cvd?: number[];
  overlays?: Record<string, number[]>;
  levels?: { price: number; label: string; kind: string }[];
  /** Shaded zones. A figure draws them; an exercise payload never carries them (m30). */
  bands?: { low: number; high: number; label: string; kind: string }[];
  indicator: "rsi" | "macd" | "oi" | "cvd" | "none";
  annotations: { index: number; kind: string; label: string }[];
}

export interface FigureData {
  id: string;
  kind: "chart" | "svg";
  caption: string;
  svg?: string;
  panels?: FigurePanel[];
}

export async function getFigure(figureId: string): Promise<FigureData> {
  const { data } = await apiClient.get<FigureData>(`/figures/${figureId}`);
  return data;
}
