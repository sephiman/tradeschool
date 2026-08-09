import type { PrintExercise, PrintExercises } from "@/api/course";
import { CandleChart } from "@/components/charts/CandleChart";
import {
  captureChart,
  stackCanvases,
  toPng,
  withPrintPixelRatio,
  type CaptureProgress,
  PAIRED_STAGE_HEIGHT,
  STAGE_HEIGHT,
} from "@/lib/pdf/figures";

/**
 * Off-screen capture of the charts that ARE the question, on the lesson figures' stage.
 *
 * Unlike a figure: NO markers or bands — those give the answer away and live only in the key — and one
 * IMAGE per exercise, keyed by exercise id. m20-l2's two frames are stacked into that single image
 * rather than published as a pair, so the printed-exercise / answer-key bijection is untouched.
 */

/** Chart-bearing exercises in print order, counted up front so progress has a known total. */
export function chartExercises(print: PrintExercises): PrintExercise[] {
  return print.lessons.flatMap((lesson) => lesson.exercises.filter((exercise) => exercise.isChart));
}

async function captureOne(exercise: PrintExercise): Promise<string> {
  const payload = exercise.payload;
  if (!payload.series) throw new Error(`exercise ${exercise.id}: chart payload has no series`);
  const what = `exercise ${exercise.id}`;
  const context = payload.context;
  const height = context ? PAIRED_STAGE_HEIGHT : STAGE_HEIGHT;
  const main = await captureChart(
    (onReady) => (
      <CandleChart
        series={payload.series!}
        rsi={payload.rsi}
        macd={payload.macd}
        oi={payload.oi}
        cvd={payload.cvd}
        momentum={payload.momentum ? { values: payload.momentum, state: payload.momentum_state } : undefined}
        overlays={payload.overlays}
        levels={payload.levels}
        // Present, unlike `bands`: the sloped line is what m31's question is asked AGAINST, so a
        // printed chart without it is a question with nothing to answer.
        diagonals={payload.diagonals}
        // Deliberately absent: `markers` and `bands` are the answer.
        indicator={payload.indicator ?? "rsi"}
        height={height}
        rightOffset={8}
        theme="light"
        onReady={onReady}
      />
    ),
    what,
    height,
  );
  if (!context) return toPng(main, what);
  // The coarser frame (m20-l2). Same height as the panel it accompanies, because one of the questions
  // is which of the two contains the other and a shrunken panel would answer it by size.
  const companion = await captureChart(
    (onReady) => (
      <CandleChart series={context.series} indicator="none" height={height} rightOffset={8} theme="light" onReady={onReady} />
    ),
    `${what} (context panel)`,
    height,
  );
  return context.position === "above"
    ? stackCanvases(companion, main, what)
    : stackCanvases(main, companion, what);
}

/** Draw every chart exercise the book needs, keyed by id. Any failure throws, naming the exercise. */
export async function captureExerciseCharts(
  exercises: PrintExercise[],
  onProgress?: (progress: CaptureProgress) => void,
): Promise<Map<string, string>> {
  const captured = new Map<string, string>();
  return withPrintPixelRatio(async () => {
    for (const [index, exercise] of exercises.entries()) {
      onProgress?.({ done: index, total: exercises.length });
      captured.set(exercise.id, await captureOne(exercise));
    }
    onProgress?.({ done: exercises.length, total: exercises.length });
    return captured;
  });
}
