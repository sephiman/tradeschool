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

/**
 * The 2026-08-10 renumbering vacated four module ids (m31–m34) and their lessons; a bookmark to one
 * redirects to its new id. The other sixteen renumbered ids were REUSED by the permutation, so those
 * old URLs now resolve to a different live module and cannot be told apart from new bookmarks — no
 * redirect is possible for them, only for the vacated four.
 */
const RENUMBERED_MODULES: Record<string, string> = { m31: "m15", m32: "m16", m33: "m28", m34: "m21" };
const RENUMBERED_LESSONS: Record<string, string> = {
  "m31-l1": "m15-l1",
  "m31-l2": "m15-l2",
  "m32-l1": "m16-l1",
  "m33-l1": "m28-l1",
  "m34-l1": "m21-l1",
  "m34-l2": "m21-l2",
};

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
                  {/* Vacated-id bookmarks (static segments outrank the :param routes below). */}
                  {Object.entries(RENUMBERED_MODULES).map(([old, now]) => (
                    <Route
                      key={old}
                      path={coursePath(`/modules/${old}`)}
                      element={<Navigate to={coursePath(`/modules/${now}`)} replace />}
                    />
                  ))}
                  {Object.entries(RENUMBERED_LESSONS).map(([old, now]) => (
                    <Route
                      key={old}
                      path={coursePath(`/lessons/${old}`)}
                      element={<Navigate to={coursePath(`/lessons/${now}`)} replace />}
                    />
                  ))}
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
