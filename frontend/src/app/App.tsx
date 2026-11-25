import { ErrorBoundary } from './ErrorBoundary'
import { AppRouter } from './AppRouter'

export function App() {
  return (
    <ErrorBoundary>
      <AppRouter />
    </ErrorBoundary>
  )
}