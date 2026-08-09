import { apiClient, COURSE_PATH } from "@/api/client";
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
  /** This lesson's reading time in seconds; every aggregate is a sum of these (see readingTime.ts). */
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
  const { data } = await apiClient.get<Course>(COURSE_PATH);
  return data;
}

export async function getLesson(lessonId: string): Promise<LessonDetail> {
  const { data } = await apiClient.get<LessonDetail>(`${COURSE_PATH}/lessons/${lessonId}`);
  return data;
}

export async function completeLesson(lessonId: string): Promise<void> {
  await apiClient.post(`${COURSE_PATH}/lessons/${lessonId}/complete`);
}

export async function getModule(moduleId: string): Promise<ModuleDetail> {
  const { data } = await apiClient.get<ModuleDetail>(`${COURSE_PATH}/modules/${moduleId}`);
  return data;
}

/** The shape `…/{course}/export?lang=…` serves: theory only, `::exercise` stripped server-side. */
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

/** One meaning of a term the course genuinely uses in more than one sense (`premium` has three). */
export interface GlossarySense {
  origin: string;
  originTitle: string | null;
  definition: string;
}

export interface GlossaryEntry {
  id: string;
  term: string;
  /** The lesson that teaches it. Absent only on a pure homonym, where each sense carries its own. */
  origin: string | null;
  originTitle: string | null;
  definition?: string;
  senses?: GlossarySense[];
  /** A second name the course uses: renders as a pointer, never as a repeated definition. */
  aliasOf?: { id: string; term: string };
  // --- what the annotator may link. Absent means the default; see lib/glossary/terms.ts.
  /** `false` opts the term out of prose annotation entirely (a word too common to link). */
  link?: boolean;
  /** The surface forms to look for, where the derived default is wrong for this locale. */
  match?: string[];
  /** Lessons where this term is never marked, on top of its own origin. */
  linkExcept?: string[];
}

export interface Glossary {
  locale: string;
  terms: GlossaryEntry[];
}

export async function getGlossary(locale: string): Promise<Glossary> {
  const { data } = await apiClient.get<Glossary>(`${COURSE_PATH}/glossary`, { params: { lang: locale } });
  return data;
}

export interface CourseExport {
  locale: string;
  blocks: CourseExportBlock[];
  /** Carried in the export so the PDF builds from one document, with no second request. */
  glossary: GlossaryEntry[];
}

/** The single-locale export document. `lang` must be explicit — omitting it returns the bilingual one. */
export async function getCourseExport(locale: string): Promise<CourseExport> {
  const { data } = await apiClient.get<CourseExport>(`${COURSE_PATH}/export`, { params: { lang: locale } });
  return data;
}

/**
 * The shape `…/{course}/print/exercises?lang=…` serves: one frozen instance per exercise plus its answer.
 *
 * The one endpoint that hands over solutions — see its server-side docstring.
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
  const { data } = await apiClient.get<PrintExercises>(`${COURSE_PATH}/print/exercises`, {
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
  /** The zero-centred pane (m32): a signed series and its optional per-bar state row. */
  momentum?: number[];
  momentum_state?: number[];
  overlays?: Record<string, number[]>;
  levels?: { price: number; label: string; kind: string }[];
  /** Sloped lines (m31), projected to the figure's own right edge so the break is judged against them. */
  diagonals?: { start: number; end: number; start_price: number; end_price: number; label: string; kind: string }[];
  /** Shaded zones. A figure draws them; an exercise payload never carries them (m30). */
  bands?: { low: number; high: number; label: string; kind: string }[];
  indicator: "rsi" | "macd" | "oi" | "cvd" | "momentum" | "none";
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
  const { data } = await apiClient.get<FigureData>(`${COURSE_PATH}/figures/${figureId}`);
  return data;
}
