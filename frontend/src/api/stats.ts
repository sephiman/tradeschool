import { apiClient } from "@/api/client";

export interface Coverage {
  publishedModules: number;
  totalModules: number;
  publishedLessons: number;
}

export interface Reading {
  lessonsCompleted: number;
  lessonsTotal: number;
  courseCompletion: number | null;
}

export interface ExerciseOverall {
  answered: number;
  correct: number;
  accuracy: number | null;
  firstAttemptAccuracy: number | null;
  avgAttemptsToSuccess: number | null;
}

export interface ModuleStat {
  id: string;
  title: string | null;
  blockId: string | null;
  lessonsTotal: number;
  lessonsCompleted: number;
  exercisesTotal: number;
  exercisesPassed: number;
  answered: number;
  accuracy: number | null;
  firstAttemptAccuracy: number | null;
}

export interface CostliestSection {
  moduleId: string;
  title: string | null;
  incorrect: number;
  answered: number;
  firstAttemptAccuracy: number | null;
}

export interface MeStats {
  coverage: Coverage;
  reading: Reading;
  exercise: ExerciseOverall;
  modules: ModuleStat[];
  costliestSections: CostliestSection[];
}

export interface GlobalModule {
  moduleId: string;
  title: string | null;
  attemptedByUsers: number;
  firstAttemptAccuracy: number | null;
}

export interface GlobalExercise {
  exerciseId: string;
  moduleId: string;
  attemptedByUsers: number;
  firstAttemptAccuracy: number | null;
}

export interface GlobalStats {
  exercises: GlobalExercise[];
  modules: GlobalModule[];
}

export async function getMeStats(): Promise<MeStats> {
  const { data } = await apiClient.get<MeStats>("/stats/me");
  return data;
}

export async function getGlobalStats(): Promise<GlobalStats> {
  const { data } = await apiClient.get<GlobalStats>("/stats/global");
  return data;
}
