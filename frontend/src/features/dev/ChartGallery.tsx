import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getDevFigures,
  getDevInstances,
  type DivergenceGroundTruth,
  type GalleryItem,
  type GroundTruth,
  type PatternGroundTruth,
} from "@/api/dev";
import { CandleChart } from "@/components/charts/CandleChart";
import { divergenceMarkers, patternBands, patternMarkers } from "@/components/charts/markers";
import { Badge, Button, Card, Input, Select, Spinner } from "@/components/ui/primitives";
import { LessonFigure } from "@/features/course/LessonFigure";

const EXERCISES = ["m12-ex-1", "m12-ex-2", "m26-ex-1", "m30-ex-1", "m30-ex-2"];

/** Divergence ground truth carries a `divergence` string; pattern_chart carries a `label`. */
function isDivergence(gt: GroundTruth): gt is DivergenceGroundTruth {
  return typeof (gt as DivergenceGroundTruth)?.divergence === "string";
}
function isPattern(gt: GroundTruth): gt is PatternGroundTruth {
  return typeof (gt as PatternGroundTruth)?.label === "string";
}

/** Ground-truth badge text: divergence class, pattern label, or "?" if neither shape. */
function label(item: GalleryItem): string {
  const gt = item.groundTruth;
  if (isDivergence(gt)) return gt.divergence ?? "?";
  if (isPattern(gt)) return gt.label ?? "?";
  return "?";
}

/** Dev-only credibility gallery: many generated charts with their labels, in the production renderer. */
export function ChartGallery() {
  const [exerciseId, setExerciseId] = useState(EXERCISES[1]);
  const [draft, setDraft] = useState("");
  const [count, setCount] = useState(24);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["dev-instances", exerciseId, count],
    queryFn: () => getDevInstances(exerciseId, count),
    retry: false,
    meta: { silentError: true }, // handled inline below, not via a toast
  });

  const { data: figureIds } = useQuery({
    queryKey: ["dev-figures"],
    queryFn: getDevFigures,
    retry: false,
    meta: { silentError: true },
  });

  const loadDraft = () => {
    const id = draft.trim();
    if (id) setExerciseId(id);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-xl font-bold">Chart credibility gallery</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Dev-only. Ground-truth labels shown. Toggle the app theme to review light, dark and OLED.
          </p>
        </div>
        <label className="text-sm">
          Preset{" "}
          <Select value={exerciseId} onChange={(e) => setExerciseId(e.target.value)} className="w-auto py-1">
            {EXERCISES.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
            {!EXERCISES.includes(exerciseId) && (
              <option value={exerciseId}>{exerciseId}</option>
            )}
          </Select>
        </label>
        <label className="text-sm">
          Exercise id{" "}
          <span className="inline-flex gap-2 align-middle">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && loadDraft()}
              placeholder="e.g. m08-ex-1"
              className="w-40 py-1"
            />
            <Button variant="secondary" onClick={loadDraft} className="py-1">
              Load
            </Button>
          </span>
        </label>
        <label className="text-sm">
          Count{" "}
          <Select value={count} onChange={(e) => setCount(Number(e.target.value))} className="w-auto py-1">
            {[12, 24, 48, 60].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </label>
      </div>

      <p className="text-sm text-gray-500 dark:text-gray-400">
        Showing <code className="font-mono">{exerciseId}</code>
      </p>

      {isError ? (
        <Card className="p-6 text-sm">
          <p className="font-medium text-amber-700 dark:text-amber-300">
            The dev endpoints are disabled or the exercise id is unknown.
          </p>
          <p className="mt-2 text-gray-600 dark:text-gray-300">
            This gallery needs <code className="font-mono">DEV_MODE=true</code> on the backend, and a valid{" "}
            <code className="font-mono">exercise_id</code>. Set it in your <code className="font-mono">.env</code> and
            restart: <code className="font-mono">docker compose up -d --build</code>.
          </p>
        </Card>
      ) : isLoading || !data ? (
        <div className="flex justify-center py-16 text-gray-500">
          <Spinner />
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {data.items.map((item) => {
            const gt = item.groundTruth;
            const markers = isDivergence(gt) ? divergenceMarkers(gt) : patternMarkers(gt);
            const badge = label(item);
            return (
              <Card key={item.seed} className="p-2">
                <div className="mb-1 flex items-center justify-between px-1 text-xs">
                  <span className="font-mono text-gray-400">seed {item.seed}</span>
                  <div className="flex items-center gap-2">
                    <a
                      href={`/api/dev/charts/data?exercise_id=${exerciseId}&seed=${item.seed}&fmt=csv`}
                      className="text-gray-400 underline hover:text-primary"
                    >
                      CSV
                    </a>
                    <Badge tone={badge === "none" ? "neutral" : "indigo"}>{badge}</Badge>
                  </div>
                </div>
                {item.payload.series && (
                  <CandleChart
                    series={item.payload.series}
                    rsi={item.payload.rsi}
                    macd={item.payload.macd}
                    oi={item.payload.oi}
                    indicator={item.payload.indicator ?? "rsi"}
                    markers={markers}
                    overlays={item.payload.overlays}
                    levels={item.payload.levels}
                    // The gallery shows ground truth by design, so the zone IS drawn here — which is
                    // what makes it reviewable against the candles it claims to be read from.
                    bands={isDivergence(gt) ? [] : patternBands(gt)}
                    height={320}
                  />
                )}
              </Card>
            );
          })}
        </div>
      )}

      {figureIds && figureIds.length > 0 && (
        <section className="mt-10 border-t border-border pt-6 dark:border-gray-800 oled:border-oled-line">
          <h2 className="text-lg font-bold">Lesson figures ({figureIds.length})</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            The whole figure set. Toggle the app language (EN/ES) and theme (light/dark) to review
            annotation labels, level titles, and edge placement across both.
          </p>
          <div className="mt-3 grid gap-x-6 lg:grid-cols-2">
            {figureIds.map((fid) => (
              <div key={fid}>
                <p className="mt-4 font-mono text-xs text-gray-400">{fid}</p>
                <LessonFigure id={fid} />
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
