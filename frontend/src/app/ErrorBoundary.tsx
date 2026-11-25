import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('UI error boundary', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <main className="shell error-boundary" role="alert">
          <h1>Something went wrong in this view</h1>
          <p>Product features remain unavailable until reloaded. No data was sent.</p>
          <pre className="error-pre">{this.state.error.message}</pre>
          <button type="button" className="btn" onClick={() => this.setState({ error: null })}>
            Dismiss
          </button>
        </main>
      )
    }
    return this.props.children
  }
}