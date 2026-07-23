import type { ReactNode } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { Prose } from "@/lib/markdown";

function isObj(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asStringArray(value: unknown): string[] | null {
  return Array.isArray(value) ? value.map((x) => String(x)) : null;
}

/**
 * `correctAnswer` arrives in one of several server shapes depending on the
 * exercise kind. Narrow with guards and render each readably (human text for
 * matching/ordering, not raw ids).
 */
function renderCorrectAnswer(value: unknown, t: TFunction): ReactNode {
  if (value == null) return null;
  if (typeof value === "string") return value;
  if (!isObj(value)) return String(value);

  // matching — { pairs, readable: [{left, right}] }
  if (Array.isArray(value.readable)) {
    return (
      <ul className="mt-1 space-y-0.5">
        {value.readable.map((entry, i) => {
          const pair = isObj(entry) ? entry : {};
          return (
            <li key={i} className="flex flex-wrap items-center gap-1">
              <span>{String(pair.left ?? "")}</span>
              <span className="text-gray-400">→</span>
              <span className="font-medium">{String(pair.right ?? "")}</span>
            </li>
          );
        })}
      </ul>
    );
  }

  const texts = asStringArray(value.texts);
  // ordering — { order, texts }: sequence matters, render numbered.
  if (texts && "order" in value) {
    return (
      <ol className="mt-1 list-decimal space-y-0.5 pl-5">
        {texts.map((text, i) => (
          <li key={i}>{text}</li>
        ))}
      </ol>
    );
  }
  // multi_select — { optionIds, texts }
  if (texts) {
    return (
      <ul className="mt-1 list-disc space-y-0.5 pl-5">
        {texts.map((text, i) => (
          <li key={i}>{text}</li>
        ))}
      </ul>
    );
  }

  // single_choice / chart — { text } (and { optionId })
  if (typeof value.text === "string") return value.text;
  // true_false — { value: boolean }
  if (typeof value.value === "boolean") return value.value ? t("exercise.true") : t("exercise.false");
  // calculation — { optionId, value }
  if (value.value != null) return String(value.value);

  return null;
}

export function AttemptResult({
  correct,
  correctAnswer,
  solutionSteps,
  explanation,
}: {
  correct: boolean;
  correctAnswer: unknown;
  solutionSteps: string[];
  explanation: string | null;
}) {
  const { t } = useTranslation();
  const answer = renderCorrectAnswer(correctAnswer, t);

  return (
    <div className="mt-4 space-y-3">
      <div
        className={cn(
          "rounded-md px-3 py-2 text-sm font-medium",
          correct
            ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200"
            : "bg-red-100 text-red-800 dark:bg-red-950/50 dark:text-red-200",
        )}
      >
        {correct ? t("exercise.correct") : t("exercise.incorrect")}
      </div>

      {answer != null && (
        <div className="text-sm text-gray-700 dark:text-gray-300">
          <span className="font-medium">{t("exercise.correctAnswer")}:</span>
          {typeof answer === "string" ? <span> {answer}</span> : answer}
        </div>
      )}

      {solutionSteps.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">
            {t("exercise.solution")}
          </p>
          <pre className="overflow-x-auto rounded-md bg-gray-100 p-3 font-mono text-xs leading-relaxed text-gray-800 dark:bg-gray-800 dark:text-gray-200">
            {solutionSteps.join("\n")}
          </pre>
        </div>
      )}

      {explanation && (
        <div className="text-sm text-gray-700 dark:text-gray-300">
          <Prose markdown={explanation} />
        </div>
      )}
    </div>
  );
}
