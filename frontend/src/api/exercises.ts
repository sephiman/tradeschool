import { apiClient, COURSE_PATH } from "@/api/client";
import type { ExerciseType } from "@/api/course";

export type AttemptState = "open" | "answered" | "abandoned";

export type QuizKind =
  | "single_choice"
  | "true_false"
  | "multi_select"
  | "ordering"
  | "matching";

/** A selectable item: quiz/ordering/matching carry `text`, calculation carries `value`. */
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

/** A sloped line (m31). Public on the question, unlike a band — see `PriceDiagonal`. */
export interface PriceDiagonalPayload {
  start: number;
  end: number;
  start_price: number;
  end_price: number;
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
  formula?: string;
  // chart
  series?: ChartSeriesPayload;
  rsi?: number[];
  macd?: { line: number[]; signal: number[]; hist: number[] };
  oi?: number[];
  cvd?: number[];
  // The zero-centred pane (m32): a signed series and its optional per-bar state row.
  momentum?: number[];
  momentum_state?: number[];
  indicator?: "rsi" | "macd" | "oi" | "cvd" | "momentum" | "none";
  choices?: string[];
  // pattern_chart: price-pane overlays (name -> values aligned 1:1 with the series), levels and the
  // sloped lines m31 asks its questions against.
  overlays?: Record<string, number[]>;
  levels?: PriceLevelPayload[];
  diagonals?: PriceDiagonalPayload[];
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
  | { divergence: string } // divergence chart
  | { label: string }; // pattern chart

/** Deferred-grading mode (exams): answer-capture only, no submit button or feedback. */
export type Deferred = { value: Answer | null; onChange: (answer: Answer) => void };

export async function createAttempt(exerciseId: string): Promise<AttemptInstance> {
  const { data } = await apiClient.post<AttemptInstance>(`${COURSE_PATH}/exercises/${exerciseId}/attempts`);
  return data;
}

export async function answerAttempt(attemptId: string, answer: Answer): Promise<GradeResponse> {
  const { data } = await apiClient.post<GradeResponse>(`${COURSE_PATH}/attempts/${attemptId}/answer`, { answer });
  return data;
}

export async function getAttempt(attemptId: string): Promise<AttemptReview> {
  const { data } = await apiClient.get<AttemptReview>(`${COURSE_PATH}/attempts/${attemptId}`);
  return data;
}

export async function listAttempts(exerciseId: string): Promise<AttemptSummary[]> {
  const { data } = await apiClient.get<AttemptSummary[]>(`${COURSE_PATH}/attempts`, { params: { exercise_id: exerciseId } });
  return data;
}
