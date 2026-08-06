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
 * Off-screen capture of the charts that ARE the question, on the same stage the lesson figures use —
 * the app's own `CandleChart`, light theme, print resolution.
 *
 * Two differences from a figure, and both are the point:
 *
 * * **No markers, no bands.** A figure exists to show the resolution; an exercise exists to ask for
 *   it. The printed chart is the pre-answer instance exactly as the app draws it before you answer —
 *   already cut before the resolution, because the generated instance is — and the swings and shaded
 *   zones that give it away live only in the answer key.
 * * **One chart per exercise**, keyed by exercise id, so the document can look up the image for the
 *   question it is laying out.
 */

/** Chart-bearing exercises in print order. Chart capture is the expensive phase, so the caller counts
 *  these up front to report progress against a total it knows before it starts. */
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
        overlays={payload.overlays}
        levels={payload.levels}
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

/** Draw every chart exercise the book needs, keyed by exercise id.
 *
 *  Any failure throws, naming the exercise: a question printed without its chart is unanswerable, and
 *  an answer key entry for a question that is not there is worse than no book at all. */
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
