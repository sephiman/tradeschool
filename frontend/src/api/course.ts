import { apiClient } from "@/api/client";

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
