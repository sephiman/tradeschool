import type { IChartApi } from "lightweight-charts";
import type { PrintExercise, PrintExercises } from "@/api/course";
import { CandleChart } from "@/components/charts/CandleChart";
import {
  makeStage,
  mount,
  nextFrame,
  toPng,
  waitFor,
  withPrintPixelRatio,
  type CaptureProgress,
  type Mounted,
  STAGE_HEIGHT,
  STAGE_WIDTH,
} from "@/lib/pdf/figures";

/**
 * Off-screen capture of the charts that ARE the question, on the lesson figures' stage.
 *
 * Unlike a figure: NO markers or bands — those give the answer away and live only in the key — and one
 * chart per exercise, keyed by exercise id.
 */

/** Chart-bearing exercises in print order, counted up front so progress has a known total. */
export function chartExercises(print: PrintExercises): PrintExercise[] {
  return print.lessons.flatMap((lesson) => lesson.exercises.filter((exercise) => exercise.isChart));
}

async function captureOne(exercise: PrintExercise): Promise<string> {
  const payload = exercise.payload;
  if (!payload.series) throw new Error(`exercise ${exercise.id}: chart payload has no series`);
  const stage = makeStage(STAGE_WIDTH, STAGE_HEIGHT);
  let mounted: Mounted | null = null;
  try {
    const ready: { chart: IChartApi | null } = { chart: null };
    mounted = await mount(
      stage,
      <CandleChart
        series={payload.series}
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
        height={STAGE_HEIGHT}
        rightOffset={8}
        theme="light"
        onReady={(chart) => {
          ready.chart = chart;
        }}
      />,
    );
    await waitFor(() => ready.chart !== null, mounted.failure, `exercise ${exercise.id}`);
    await nextFrame(); // one more, so the panes have laid out before we ask for a bitmap
    return toPng(ready.chart!.takeScreenshot(), `exercise ${exercise.id}`);
  } finally {
    mounted?.root.unmount();
    stage.remove();
  }
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
