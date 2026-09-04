import { apiClient, COURSE_PATH } from "@/api/client";
import type { ExerciseType } from "@/api/course";
import type { Answer, AttemptPayload } from "@/api/exercises";

export type ExamScope = "global" | "block";
export type ExamStatus = "open" | "submitted" | "abandoned";

export interface ExamQuestion {
  index: number;
  attemptId: string;
  moduleId: string;
  moduleTitle: string;
  blockId: string;
  blockTitle: string;
  exerciseId: string;
  type: ExerciseType;
  prompt: string;
  payload: AttemptPayload;
  answered: boolean;
  givenAnswer: Answer | null;
  // Reveal-only (submitted review):
  isCorrect: boolean | null;
  unanswered: boolean | null;
  correctAnswer: unknown;
  solutionSteps: string[];
  explanation: string | null;
}

export interface ExamResultBlock {
  blockId: string;
  title: string;
  correct: number;
  total: number;
  score: number | null;
}

export interface ExamResultModule {
  moduleId: string;
  title: string;
  blockId: string;
  correct: boolean;
  unanswered: boolean;
}

export interface ExamResult {
  score: number | null;
  correct: number;
  total: number;
  blocks: ExamResultBlock[];
  modules: ExamResultModule[];
}

export interface ExamSession {
  id: string;
  scope: ExamScope;
  blockId: string | null;
  blockTitle: string | null;
  status: ExamStatus;
  createdAt: string;
  finishedAt: string | null;
  result: ExamResult | null;
  questions: ExamQuestion[];
}

export interface ExamHistoryItem {
  id: string;
  scope: ExamScope;
  blockId: string | null;
  blockTitle: string | null;
  createdAt: string;
  finishedAt: string | null;
  score: number | null;
  correct: number;
  total: number;
}

export async function startExam(scope: ExamScope, blockId?: string): Promise<ExamSession> {
  const { data } = await apiClient.post<ExamSession>(`${COURSE_PATH}/exams`, { scope, blockId: blockId ?? null });
  return data;
}

/**
 * EVERY open sitting, newest first.
 *
 * This replaced a `/current` that answered with the newest one alone. Starting an exam only closes an
 * open one of the same scope, so a global and a block exam can be open at once — and the older of the
 * two then had no route in the UI that could reach it, to resume or to abandon.
 */
export async function getOpenExams(): Promise<ExamSession[]> {
  const { data } = await apiClient.get<ExamSession[]>(`${COURSE_PATH}/exams/open`);
  return data;
}

export async function getExam(examId: string): Promise<ExamSession> {
  const { data } = await apiClient.get<ExamSession>(`${COURSE_PATH}/exams/${examId}`);
  return data;
}

export async function answerExamQuestion(examId: string, attemptId: string, answer: Answer): Promise<void> {
  await apiClient.post(`${COURSE_PATH}/exams/${examId}/questions/${attemptId}/answer`, { answer });
}

export async function submitExam(examId: string): Promise<ExamSession> {
  const { data } = await apiClient.post<ExamSession>(`${COURSE_PATH}/exams/${examId}/submit`, {});
  return data;
}

export async function reviewExam(examId: string): Promise<ExamSession> {
  const { data } = await apiClient.get<ExamSession>(`${COURSE_PATH}/exams/${examId}/review`);
  return data;
}

export async function abandonExam(examId: string): Promise<void> {
  await apiClient.post(`${COURSE_PATH}/exams/${examId}/abandon`, {});
}

export async function examHistory(): Promise<ExamHistoryItem[]> {
  const { data } = await apiClient.get<ExamHistoryItem[]>(`${COURSE_PATH}/exams`);
  return data;
}
