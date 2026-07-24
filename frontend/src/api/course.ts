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

export interface Course {
  locale: string;
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
  lessons: { id: string; order: number; title: string; completed: boolean }[];
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

export interface FigurePanel {
  series: { time: number[]; open: number[]; high: number[]; low: number[]; close: number[]; volume: number[] };
  rsi?: number[];
  macd?: { line: number[]; signal: number[]; hist: number[] };
  oi?: number[];
  overlays?: Record<string, number[]>;
  levels?: { price: number; label: string; kind: string }[];
  indicator: "rsi" | "macd" | "oi" | "none";
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
