import { Suspense, lazy } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { AuthDesignPage } from '../features/auth/AuthDesignPage'
import { StudentDiagnosticsPage } from '../features/diagnostics/StudentDiagnosticsPage'
import { FoundationStatusPage } from '../features/home/FoundationStatusPage'
import { KnowledgeLibraryPage } from '../features/knowledge/KnowledgeLibraryPage'
import { PackOnboardingPage } from '../features/onboarding/PackOnboardingPage'
import { PolicyAdminPage } from '../features/policy/PolicyAdminPage'
import { RemediationPage } from '../features/remediation/RemediationPage'
import { SourceAdminPage } from '../features/sources/SourceAdminPage'
import { StudentResultPage } from '../features/student/StudentResultPage'
import { StudentRunnerPage } from '../features/student/StudentRunnerPage'
import { ProductShell } from './ProductShell'

const QuestionStudioPage = lazy(() =>
  import('../features/studio/QuestionStudioPage').then((m) => ({ default: m.QuestionStudioPage })),
)
const TeacherDiagnosticsPage = lazy(() =>
  import('../features/diagnostics/TeacherDiagnosticsPage').then((m) => ({
    default: m.TeacherDiagnosticsPage,
  })),
)

function RouteFallback() {
  return <p role="status">Loading view…</p>
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<ProductShell />}>
          <Route index element={<FoundationStatusPage />} />
          <Route
            path="studio"
            element={
              <Suspense fallback={<RouteFallback />}>
                <QuestionStudioPage />
              </Suspense>
            }
          />
          <Route path="student" element={<StudentRunnerPage />} />
          <Route path="results" element={<StudentResultPage />} />
          <Route
            path="diagnostics/teacher"
            element={
              <Suspense fallback={<RouteFallback />}>
                <TeacherDiagnosticsPage />
              </Suspense>
            }
          />
          <Route path="diagnostics/student" element={<StudentDiagnosticsPage />} />
          <Route path="remediation" element={<RemediationPage />} />
          <Route path="knowledge" element={<KnowledgeLibraryPage />} />
          <Route path="sources" element={<SourceAdminPage />} />
          <Route path="onboarding" element={<PackOnboardingPage />} />
          <Route path="policy" element={<PolicyAdminPage />} />
          <Route path="auth-design" element={<AuthDesignPage />} />
          <Route
            path="*"
            element={
              <section className="panel">
                <h2>Unknown route</h2>
                <p role="status" data-testid="unknown-route">
                  This path is not part of the Day 18 demo shell. No feature actions are available.
                </p>
              </section>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}