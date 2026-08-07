import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import type { CourseMeta } from "@/api/course";
import { Button, Spinner } from "@/components/ui/primitives";
import type { PdfLabels } from "@/lib/pdf/document";
import { downloadPdf, generateCoursePdf, type GenerateProgress } from "@/lib/pdf/generate";
import { pdfLabels } from "@/lib/pdf/labels";

/**
 * The whole course as one printable PDF, in the language being browsed.
 *
 * Slow enough to report phases rather than spin, and a failure stays on the page. Every printed word is
 * resolved here and handed over as `labels`, which keeps `lib/pdf/` free of i18next.
 */
export function ExportPdfButton({ course }: { course: CourseMeta }) {
  const { t, i18n } = useTranslation();
  const [progress, setProgress] = useState<GenerateProgress | null>(null);
  const locale = i18n.resolvedLanguage === "es" ? "es" : "en";

  const labels: PdfLabels = pdfLabels(
    t,
    t("course.pdfGenerated", {
      language: t("course.pdfLanguage"),
      date: new Date().toLocaleDateString(locale === "es" ? "es-ES" : "en-GB"),
    }),
  );

  const exportPdf = useMutation({
    // Success is the file landing in the downloads folder; failure is reported in place, below.

    meta: { silentSuccess: true, silentError: true },
    mutationFn: async () => {
      const generated = await generateCoursePdf({
        locale,
        courseId: course.id,
        courseTitle: course.title,
        courseDescription: course.description,
        labels,
        date: new Date(),
        onProgress: setProgress,
      });
      downloadPdf(generated);
    },
    onSettled: () => setProgress(null),
  });

  const phaseLabel = (): string => {
    if (!progress) return t("course.pdfBusy");
    const { phase, done, total } = progress;
    if (phase === "figures" && total > 0) return t("course.pdfFigures", { done, total });
    if (phase === "charts" && total > 0) return t("course.pdfCharts", { done, total });
    if (phase === "exercises") return t("course.pdfExercises");
    if (phase === "typeset") return t("course.pdfTypesetting");
    return t("course.pdfPreparing");
  };

  return (
    <div className="sm:text-right">
      <Button
        variant="secondary"
        onClick={() => exportPdf.mutate()}
        disabled={exportPdf.isPending}
        aria-busy={exportPdf.isPending}
        title={t("course.pdfHint")}
      >
        {exportPdf.isPending && <Spinner className="mr-2 h-4 w-4" />}
        {exportPdf.isPending ? phaseLabel() : t("course.pdfAction")}
      </Button>
      {exportPdf.isError && (
        <p role="alert" className="mt-2 max-w-xs text-xs text-red-600 sm:ml-auto dark:text-red-400">
          {t("course.pdfFailed", {
            reason: exportPdf.error instanceof Error ? exportPdf.error.message : String(exportPdf.error),
          })}{" "}
          <button
            type="button"
            className="font-medium underline"
            onClick={() => exportPdf.mutate()}
          >
            {t("course.pdfRetry")}
          </button>
        </p>
      )}
    </div>
  );
}
