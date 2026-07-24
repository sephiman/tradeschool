import { apiClient } from "@/api/client";
import type { AttemptPayload, PriceLevelPayload } from "@/api/exercises";

/** Divergence exercises grade to {divergence, swing1, swing2}. */
export interface DivergenceGroundTruth {
  divergence?: string;
  swing1?: number | null;
  swing2?: number | null;
}

/** pattern_chart exercises grade to {label, annotations, levels}. */
export interface PatternGroundTruth {
  label?: string;
  annotations?: Array<{ index: number; kind: string; label: string }>;
  levels?: PriceLevelPayload[];
}

/** Ground truth is exercise-type dependent; consumers narrow it at runtime. */
export type GroundTruth = DivergenceGroundTruth | PatternGroundTruth | Record<string, unknown>;

export interface GalleryItem {
  seed: number;
  prompt: string;
  payload: AttemptPayload;
  groundTruth: GroundTruth;
}

export interface GalleryResponse {
  exerciseId: string;
  type: string;
  items: GalleryItem[];
}

export async function getDevInstances(exerciseId: string, count: number): Promise<GalleryResponse> {
  const { data } = await apiClient.get<GalleryResponse>("/dev/instances", {
    params: { exercise_id: exerciseId, count },
  });
  return data;
}

/** Every lesson-figure id (dev-only), for reviewing the whole figure set in one place. */
export async function getDevFigures(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>("/dev/figures");
  return data;
}
