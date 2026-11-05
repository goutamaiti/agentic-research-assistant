// Status is always conveyed by a text label and a symbol, never by colour alone.
const STATE_STYLES = {
  ok: { label: 'OK', symbol: '✓', className: 'bg-emerald-50 text-emerald-800 ring-emerald-600/30' },
  configured: {
    label: 'Configured (not contacted)',
    symbol: '•',
    className: 'bg-sky-50 text-sky-800 ring-sky-600/30',
  },
  not_configured: {
    label: 'Not configured',
    symbol: '!',
    className: 'bg-amber-50 text-amber-900 ring-amber-600/30',
  },
  error: { label: 'Error', symbol: '✕', className: 'bg-red-50 text-red-800 ring-red-600/30' },
}

const COMPONENT_NAMES = {
  database: 'Database (SQLite)',
  vector_store: 'Vector store (ChromaDB)',
  llm: 'Language model (Gemini)',
}

function StatusBadge({ state }) {
  const style = STATE_STYLES[state] ?? STATE_STYLES.error
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style.className}`}
    >
      <span aria-hidden="true">{style.symbol}</span>
      {style.label}
    </span>
  )
}

export default function HealthStatus({ health, error, loading, onRetry }) {
  return (
    <section
      aria-labelledby="health-heading"
      className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="flex items-center justify-between gap-4">
        <h2 id="health-heading" className="text-lg font-semibold text-slate-900">
          Backend status
        </h2>
        <button
          type="button"
          onClick={onRetry}
          disabled={loading}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? 'Checking…' : 'Check again'}
        </button>
      </div>

      {error && (
        <div role="alert" className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <p className="font-medium">Backend unavailable</p>
          <p>{error.message}</p>
          <p className="mt-1 text-red-700">
            Start the API with <code>uvicorn app.main:create_app --factory --reload</code> in <code>backend/</code>.
          </p>
        </div>
      )}

      {health && (
        <>
          <p className="mt-4 text-sm text-slate-600">
            Overall: <StatusBadge state={health.status === 'ok' ? 'ok' : 'error'} />{' '}
            <span className="ml-1">
              {health.app_name} v{health.version} · {health.environment}
            </span>
          </p>
          <ul className="mt-4 divide-y divide-slate-100">
            {Object.entries(health.components).map(([name, component]) => (
              <li key={name} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="text-sm text-slate-800">{COMPONENT_NAMES[name] ?? name}</span>
                <span className="flex items-center gap-2">
                  {component.detail && (
                    <span className="text-xs text-slate-500">{component.detail}</span>
                  )}
                  <StatusBadge state={component.status} />
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
