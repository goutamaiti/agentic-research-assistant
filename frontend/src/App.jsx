import { useCallback, useEffect, useState } from 'react'
import AnalysisPage from './pages/AnalysisPage.jsx'
import AssistantPage from './pages/AssistantPage.jsx'
import EvidencePage from './pages/EvidencePage.jsx'
import UploadPage from './pages/UploadPage.jsx'

// Minimal hash routing: #/ , #/analysis/<id>, #/evidence/<id>, #/assistant/<id>.
function parseHash() {
  const [page = '', documentId = null] = window.location.hash.replace(/^#\/?/, '').split('/')
  return { page, documentId }
}

const TABS = [
  ['analysis', 'Analysis'],
  ['evidence', 'Evidence'],
  ['assistant', 'Assistant'],
]

export default function App() {
  const [route, setRoute] = useState(parseHash)

  useEffect(() => {
    const onChange = () => setRoute(parseHash())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = useCallback((path) => {
    window.location.hash = `/${path}`
  }, [])

  const { page, documentId } = route
  let content = <UploadPage navigate={navigate} />
  if (documentId && page === 'analysis') content = <AnalysisPage documentId={documentId} />
  if (documentId && page === 'evidence') content = <EvidencePage documentId={documentId} />
  if (documentId && page === 'assistant') content = <AssistantPage documentId={documentId} />

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <button type="button" onClick={() => navigate('')} className="text-left">
            <h1 className="text-xl font-semibold">Agentic Research Assistant</h1>
            <p className="text-sm text-slate-600">Single-paper analysis with evidence-supported extraction.</p>
          </button>
          {documentId && (
            <nav className="flex gap-1" aria-label="Paper views">
              {TABS.map(([name, label]) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => navigate(`${name}/${documentId}`)}
                  aria-current={page === name ? 'page' : undefined}
                  className={`rounded-md px-3 py-1.5 text-sm ${page === name ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'}`}
                >
                  {label}
                </button>
              ))}
            </nav>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-8">{content}</main>
    </div>
  )
}
