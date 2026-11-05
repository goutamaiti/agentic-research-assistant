import { useCallback, useEffect, useState } from 'react'
import HealthStatus from './components/HealthStatus.jsx'
import { getHealth } from './services/api.js'

// Phase 1 shell: confirms the frontend can reach the backend. The dashboard, upload,
// analysis, evidence and assistant pages are built in later phases.
export default function App() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const checkHealth = useCallback(async () => {
    setLoading(true)
    try {
      setHealth(await getHealth())
      setError(null)
    } catch (err) {
      setHealth(null)
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    checkHealth()
  }, [checkHealth])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-3xl px-4 py-5">
          <h1 className="text-xl font-semibold">Agentic Research Assistant</h1>
          <p className="mt-1 text-sm text-slate-600">
            Single-paper analysis with evidence-supported extraction and verification status.
          </p>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">
        <HealthStatus health={health} error={error} loading={loading} onRetry={checkHealth} />
      </main>
    </div>
  )
}
