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
  /** Distinct exercises with at least one answered attempt — the first-attempt denominator. */
  firstSeen: number;
  firstCorrect: number;
  avgAttemptsToSuccess: number | null;
}

/** An exercise the learner got wrong at least once, and where to go to try it again. */
export interface ReviewTarget {
  exerciseId: string;
  lessonId: string | null;
  incorrect: number;
  /** Solved since — shown as solved rather than implying unfinished business. */
  passed: boolean;
}

export interface ModuleStat {
  id: string;
  title: string | null;
  blockId: string | null;
  lessonsTotal: number;
  lessonsCompleted: number;
  exercisesTotal: number;
  exercisesPassed: number;
  /** Answered attempts — the `accuracy` denominator. Distinct from `firstSeen`. */
  answered: number;
  correct: number;
  accuracy: number | null;
  firstAttemptAccuracy: number | null;
  firstSeen: number;
  firstCorrect: number;
  exercisesFailed: number;
  toReview: ReviewTarget[];
}

export interface CostliestSection {
  moduleId: string;
  title: string | null;
  incorrect: number;
  answered: number;
  correct: number;
  firstAttemptAccuracy: number | null;
  firstSeen: number;
  firstCorrect: number;
  exercisesFailed: number;
  toReview: ReviewTarget[];
}

export interface Thresholds {
  /** Distinct exercises a module needs answered before it may be ranked as "costliest". */
  minExercisesToRank: number;
}

export interface MeStats {
  coverage: Coverage;
  thresholds: Thresholds;
  reading: Reading;
  exercise: ExerciseOverall;
  modules: ModuleStat[];
  costliestSections: CostliestSection[];
}

export interface GlobalThresholds {
  /** Distinct learners a row needs before the global panel is allowed to show it at all. */
  minLearners: number;
}

/**
 * `learners` and `firstSeen` are two populations, not one: a learner who answered four of a module's
 * exercises is four first-attempt observations but one person. The rate goes over `firstSeen`; the
 * headcount printed next to it is `learners`.
 */
export interface GlobalModule {
  moduleId: string;
  title: string | null;
  learners: number;
  firstSeen: number;
  firstCorrect: number;
  firstAttemptAccuracy: number | null;
}

export interface GlobalExercise {
  exerciseId: string;
  moduleId: string;
  learners: number;
  firstSeen: number;
  firstCorrect: number;
  firstAttemptAccuracy: number | null;
}

export interface GlobalStats {
  thresholds: GlobalThresholds;
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
