import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { coursePath, HOME_PATH } from "@/components/layout/nav";
import { ToastHost } from "@/components/ui/ToastHost";
import { LoginPage } from "@/auth/LoginPage";
import { RegisterPage } from "@/auth/RegisterPage";
import { RequireAuth } from "@/auth/RequireAuth";
import { CoursePage } from "@/features/course/CoursePage";
import { ModulePage } from "@/features/course/ModulePage";
import { LessonPage } from "@/features/course/LessonPage";
import { GlossaryPage } from "@/features/glossary/GlossaryPage";
import { StatsPage } from "@/features/stats/StatsPage";
import { ExamPage } from "@/features/exams/ExamPage";
import { ExamRunner } from "@/features/exams/ExamRunner";
import { ExamReview } from "@/features/exams/ExamReview";
import { ChartGallery } from "@/features/dev/ChartGallery";

/**
 * A pre-scoping URL a learner may have bookmarked, sent to its course-scoped equivalent.
 *
 * One component covers every legacy path because the rewrite is mechanical: the old path becomes the
 * remainder under the course. `/course` is the exception — it maps to the course root, not to
 * `/courses/{slug}/course`.
 */
function LegacyCourseRedirect() {
  const { pathname, search } = useLocation();
  const rest = pathname === "/course" ? "" : pathname;
  return <Navigate to={`${coursePath(rest)}${search}`} replace />;
}

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/*"
          element={
            <RequireAuth>
              <AppShell>
                <Routes>
                  <Route path="/" element={<Navigate to={HOME_PATH} replace />} />

                  {/* Course-scoped pages: the address bar names the course you are in. */}
                  <Route path={HOME_PATH} element={<CoursePage />} />
                  <Route path={coursePath("/modules/:moduleId")} element={<ModulePage />} />
                  <Route path={coursePath("/lessons/:lessonId")} element={<LessonPage />} />
                  <Route path={coursePath("/glossary")} element={<GlossaryPage />} />
                  <Route path={coursePath("/stats")} element={<StatsPage />} />
                  <Route path={coursePath("/exams")} element={<ExamPage />} />
                  <Route path={coursePath("/exams/:examId")} element={<ExamRunner />} />
                  <Route path={coursePath("/exams/:examId/review")} element={<ExamReview />} />

                  {/* Bookmarks from before the scoping. Redirect rather than serve, so the address
                      bar corrects itself and there is one URL per page. */}
                  <Route path="/course" element={<LegacyCourseRedirect />} />
                  <Route path="/modules/:moduleId" element={<LegacyCourseRedirect />} />
                  <Route path="/lessons/:lessonId" element={<LegacyCourseRedirect />} />
                  <Route path="/glossary" element={<LegacyCourseRedirect />} />
                  <Route path="/stats" element={<LegacyCourseRedirect />} />
                  <Route path="/exams/*" element={<LegacyCourseRedirect />} />

                  {/* Unadvertised review route; its data comes from the DEV_MODE-gated /api/dev endpoint. */}
                  <Route path="/dev/charts" element={<ChartGallery />} />
                  <Route path="*" element={<Navigate to={HOME_PATH} replace />} />
                </Routes>
              </AppShell>
            </RequireAuth>
          }
        />
      </Routes>
      <ToastHost />
    </>
  );
}
