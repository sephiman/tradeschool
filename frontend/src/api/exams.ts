import { apiClient } from "@/api/client";
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
  const { data } = await apiClient.post<ExamSession>("/exams", { scope, blockId: blockId ?? null });
  return data;
}

export async function getCurrentExam(): Promise<ExamSession | null> {
  const { data } = await apiClient.get<ExamSession | null>("/exams/current");
  return data;
}

export async function getExam(examId: string): Promise<ExamSession> {
  const { data } = await apiClient.get<ExamSession>(`/exams/${examId}`);
  return data;
}

export async function answerExamQuestion(examId: string, attemptId: string, answer: Answer): Promise<void> {
  await apiClient.post(`/exams/${examId}/questions/${attemptId}/answer`, { answer });
}

export async function submitExam(examId: string): Promise<ExamSession> {
  const { data } = await apiClient.post<ExamSession>(`/exams/${examId}/submit`, {});
  return data;
}

export async function reviewExam(examId: string): Promise<ExamSession> {
  const { data } = await apiClient.get<ExamSession>(`/exams/${examId}/review`);
  return data;
}

export async function abandonExam(examId: string): Promise<void> {
  await apiClient.post(`/exams/${examId}/abandon`, {});
}

export async function examHistory(): Promise<ExamHistoryItem[]> {
  const { data } = await apiClient.get<ExamHistoryItem[]>("/exams");
  return data;
}
