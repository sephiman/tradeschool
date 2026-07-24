import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ToastHost } from "@/components/ui/ToastHost";
import { LoginPage } from "@/auth/LoginPage";
import { RegisterPage } from "@/auth/RegisterPage";
import { RequireAuth } from "@/auth/RequireAuth";
import { CoursePage } from "@/features/course/CoursePage";
import { ModulePage } from "@/features/course/ModulePage";
import { LessonPage } from "@/features/course/LessonPage";
import { StatsPage } from "@/features/stats/StatsPage";
import { ExamPage } from "@/features/exams/ExamPage";
import { ExamRunner } from "@/features/exams/ExamRunner";
import { ExamReview } from "@/features/exams/ExamReview";
import { ChartGallery } from "@/features/dev/ChartGallery";

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
                  <Route path="/" element={<Navigate to="/course" replace />} />
                  <Route path="/course" element={<CoursePage />} />
                  <Route path="/modules/:moduleId" element={<ModulePage />} />
                  <Route path="/lessons/:lessonId" element={<LessonPage />} />
                  <Route path="/stats" element={<StatsPage />} />
                  <Route path="/exams" element={<ExamPage />} />
                  <Route path="/exams/:examId" element={<ExamRunner />} />
                  <Route path="/exams/:examId/review" element={<ExamReview />} />
                  {/* Unadvertised review route; its data comes from the DEV_MODE-gated /api/dev endpoint. */}
                  <Route path="/dev/charts" element={<ChartGallery />} />
                  <Route path="*" element={<Navigate to="/course" replace />} />
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
