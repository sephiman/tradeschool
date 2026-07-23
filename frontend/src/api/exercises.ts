import { apiClient } from "@/api/client";
import type { ExerciseType } from "@/api/course";

export type AttemptState = "open" | "answered" | "abandoned";

export type QuizKind =
  | "single_choice"
  | "true_false"
  | "multi_select"
  | "ordering"
  | "matching";

/**
 * A selectable item in an exercise payload. Quiz options and ordering/matching
 * items carry `text`; calculation options carry `value`. Which field is present
 * depends on the exercise kind, so both are optional here.
 */
export interface OptionView {
  id: string;
  text?: string;
  value?: string | number;
}

export interface ChartSeriesPayload {
  time: number[];
  open: number[];
  high: number[];
  low: number[];
  close: number[];
  volume: number[];
}

export interface PriceLevelPayload {
  price: number;
  label: string;
  kind: string;
}

export interface AttemptPayload {
  // quiz — every quiz payload carries `kind`; calculation carries "multiple_choice".
  kind?: QuizKind | "multiple_choice";
  options?: OptionView[]; // single_choice, multi_select, calculation
  items?: OptionView[]; // ordering (already shuffled)
  lefts?: OptionView[]; // matching — left column (shuffled)
  rights?: OptionView[]; // matching — right column (shuffled)
  // calculation
  unit?: string | null;
  // chart
  series?: ChartSeriesPayload;
  rsi?: number[];
  macd?: { line: number[]; signal: number[]; hist: number[] };
  oi?: number[];
  indicator?: "rsi" | "macd" | "oi" | "none";
  choices?: string[];
  // pattern_chart: price-pane overlays (name -> values aligned 1:1 with the series) and levels.
  overlays?: Record<string, number[]>;
  levels?: PriceLevelPayload[];
}

export interface AttemptInstance {
  attemptId: string;
  exerciseId: string;
  type: ExerciseType;
  prompt: string;
  payload: AttemptPayload;
  state: AttemptState;
}

export interface GradeResponse {
  attemptId: string;
  correct: boolean;
  correctAnswer: unknown;
  solutionSteps: string[];
  explanation: string | null;
}

export interface AttemptReview extends AttemptInstance {
  givenAnswer: Record<string, unknown> | null;
  isCorrect: boolean | null;
  correctAnswer: unknown;
  solutionSteps: string[];
  explanation: string | null;
  createdAt: string;
  answeredAt: string | null;
}

export interface AttemptSummary {
  attemptId: string;
  exerciseId: string;
  state: AttemptState;
  isCorrect: boolean | null;
  createdAt: string;
  answeredAt: string | null;
}

export type Answer =
  | { optionId: string } // single_choice, calculation
  | { optionIds: string[] } // multi_select
  | { value: boolean } // true_false
  | { order: string[] } // ordering
  | { pairs: Record<string, string> } // matching
  | { divergence: string }; // chart

export async function createAttempt(exerciseId: string): Promise<AttemptInstance> {
  const { data } = await apiClient.post<AttemptInstance>(`/exercises/${exerciseId}/attempts`);
  return data;
}

export async function answerAttempt(attemptId: string, answer: Answer): Promise<GradeResponse> {
  const { data } = await apiClient.post<GradeResponse>(`/attempts/${attemptId}/answer`, { answer });
  return data;
}

export async function getAttempt(attemptId: string): Promise<AttemptReview> {
  const { data } = await apiClient.get<AttemptReview>(`/attempts/${attemptId}`);
  return data;
}

export async function listAttempts(exerciseId: string): Promise<AttemptSummary[]> {
  const { data } = await apiClient.get<AttemptSummary[]>(`/attempts`, { params: { exercise_id: exerciseId } });
  return data;
}
