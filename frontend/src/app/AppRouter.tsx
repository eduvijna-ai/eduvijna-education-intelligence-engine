import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { AuthDesignPage } from '../features/auth/AuthDesignPage'
import { StudentDiagnosticsPage } from '../features/diagnostics/StudentDiagnosticsPage'
import { TeacherDiagnosticsPage } from '../features/diagnostics/TeacherDiagnosticsPage'
import { FoundationStatusPage } from '../features/home/FoundationStatusPage'
import { KnowledgeLibraryPage } from '../features/knowledge/KnowledgeLibraryPage'
import { PackOnboardingPage } from '../features/onboarding/PackOnboardingPage'
import { PolicyAdminPage } from '../features/policy/PolicyAdminPage'
import { RemediationPage } from '../features/remediation/RemediationPage'
import { SourceAdminPage } from '../features/sources/SourceAdminPage'
import { QuestionStudioPage } from '../features/studio/QuestionStudioPage'
import { StudentResultPage } from '../features/student/StudentResultPage'
import { StudentRunnerPage } from '../features/student/StudentRunnerPage'
import { ProductShell } from './ProductShell'

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<ProductShell />}>
          <Route index element={<FoundationStatusPage />} />
          <Route path="studio" element={<QuestionStudioPage />} />
          <Route path="student" element={<StudentRunnerPage />} />
          <Route path="results" element={<StudentResultPage />} />
          <Route path="diagnostics/teacher" element={<TeacherDiagnosticsPage />} />
          <Route path="diagnostics/student" element={<StudentDiagnosticsPage />} />
          <Route path="remediation" element={<RemediationPage />} />
          <Route path="knowledge" element={<KnowledgeLibraryPage />} />
          <Route path="sources" element={<SourceAdminPage />} />
          <Route path="onboarding" element={<PackOnboardingPage />} />
          <Route path="policy" element={<PolicyAdminPage />} />
          <Route path="auth-design" element={<AuthDesignPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}