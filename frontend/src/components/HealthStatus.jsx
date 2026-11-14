import StatusBadge from './StatusBadge.jsx'

const COMPONENT_NAMES = {
  database: 'Database (SQLite)',
  vector_store: 'Vector store (ChromaDB)',
  llm: 'Language model (Gemini)',
  embeddings: 'Embedding model',
  ocr: 'OCR for scanned pages (Tesseract)',
}

// One quiet line when everything works; opens up when something does not.
export default function HealthStatus({ health, error, loading, onRetry }) {
  if (error) {
    return (
      <section aria-labelledby="health-heading" className="notice" data-tone="bad" role="alert">
        <p id="health-heading" className="notice-title">Cannot reach the backend</p>
        <p>{error.message}</p>
        <p className="muted">
          Start the API with <code>uvicorn app.main:create_app --factory --reload</code> in <code>backend/</code>, then check again.
        </p>
        <button type="button" className="button" onClick={onRetry} disabled={loading}>
          {loading ? 'Checking' : 'Check again'}
        </button>
      </section>
    )
  }
  if (!health) return null
  const overall = health.status === 'ok' ? 'ok' : 'error'
  return (
    <details className="health" open={overall !== 'ok' ? true : undefined}>
      <summary>
        <StatusBadge
          status={overall}
          label={overall === 'ok' ? 'Backend ready' : 'Backend has problems'}
        />
      </summary>
      <p className="muted">
        {health.app_name} v{health.version}, {health.environment} environment
      </p>
      <ul className="health-list">
        {Object.entries(health.components).map(([name, component]) => (
          <li key={name}>
            <span>{COMPONENT_NAMES[name] ?? name}</span>
            {component.detail && <span className="muted">{component.detail}</span>}
            <StatusBadge status={component.status} />
          </li>
        ))}
      </ul>
      <button type="button" className="link-button" onClick={onRetry} disabled={loading}>
        {loading ? 'Checking' : 'Check again'}
      </button>
    </details>
  )
}
