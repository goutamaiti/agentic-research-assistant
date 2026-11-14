import { useCallback, useEffect, useState } from 'react'
import AnalysisPage from './pages/AnalysisPage.jsx'
import AssistantPage from './pages/AssistantPage.jsx'
import EvidencePage from './pages/EvidencePage.jsx'
import UploadPage from './pages/UploadPage.jsx'
import { ACCESS_REQUIRED_EVENT, api, setAccessPassword } from './services/api.js'

// Minimal hash routing: #/ , #/analysis/<id>, #/evidence/<id>, #/assistant/<id>.
function parseHash() {
  const [page = '', documentId = null] = window.location.hash.replace(/^#\/?/, '').split('/')
  return { page, documentId }
}

function AccessForm() {
  const [value, setValue] = useState('')
  const submit = (event) => {
    event.preventDefault()
    setAccessPassword(value)
    window.location.reload()
  }
  return (
    <form onSubmit={submit} className="access">
      <h2>This deployment is password protected</h2>
      <p className="muted">Enter the password you were given to open the workspace.</p>
      <label htmlFor="access-password">Password</label>
      <input
        id="access-password"
        type="password"
        autoComplete="current-password"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <button type="submit" disabled={!value} className="button primary">
        Open workspace
      </button>
    </form>
  )
}

const TABS = [
  ['analysis', 'Analysis'],
  ['evidence', 'Evidence'],
  ['assistant', 'Assistant'],
]

function PaperBar({ documentId, page, navigate }) {
  const [title, setTitle] = useState(null)
  useEffect(() => {
    let cancelled = false
    setTitle(null)
    api
      .getDocument(documentId)
      .then((doc) => !cancelled && setTitle(doc.title ?? doc.original_filename))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [documentId])

  return (
    <div className="paperbar">
      <div className="paperbar-title">
        <a href="#/" className="back">All papers</a>
        {page !== 'analysis' && <p title={title ?? undefined}>{title ?? ' '}</p>}
      </div>
      <nav aria-label="Paper views" className="tabs">
        {TABS.map(([name, label]) => (
          <a
            key={name}
            href={`#/${name}/${documentId}`}
            aria-current={page === name ? 'page' : undefined}
            onClick={(event) => {
              event.preventDefault()
              navigate(`${name}/${documentId}`)
            }}
          >
            {label}
          </a>
        ))}
      </nav>
    </div>
  )
}

export default function App() {
  const [route, setRoute] = useState(parseHash)
  const [needsPassword, setNeedsPassword] = useState(false)

  useEffect(() => {
    const onDenied = () => setNeedsPassword(true)
    window.addEventListener(ACCESS_REQUIRED_EVENT, onDenied)
    return () => window.removeEventListener(ACCESS_REQUIRED_EVENT, onDenied)
  }, [])

  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const navigate = useCallback((path) => {
    window.location.hash = `/${path}`
  }, [])

  const { page, documentId } = route
  const inPaper = documentId && TABS.some(([name]) => name === page)
  let content = <UploadPage navigate={navigate} />
  if (inPaper && page === 'analysis') content = <AnalysisPage documentId={documentId} />
  if (inPaper && page === 'evidence') content = <EvidencePage documentId={documentId} />
  if (inPaper && page === 'assistant') content = <AssistantPage documentId={documentId} />
  if (needsPassword) content = <AccessForm />

  useEffect(() => {
    const names = { analysis: 'Analysis', evidence: 'Evidence', assistant: 'Assistant' }
    document.title = `${inPaper ? `${names[page]} – ` : ''}Agentic Research Assistant`
  }, [inPaper, page])

  return (
    <>
      <a href="#main" className="skip" onClick={(e) => { e.preventDefault(); document.getElementById('main')?.focus() }}>
        Skip to content
      </a>
      <header className="masthead">
        <div className="wrap">
          <a href="#/" className="wordmark" onClick={(e) => { e.preventDefault(); navigate('') }}>
            <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" focusable="false">
              <rect x="2" y="2" width="12" height="18" rx="1.5" fill="var(--page)" stroke="currentColor" strokeWidth="1.6" />
              <rect x="5" y="9" width="6" height="3.2" fill="var(--marker)" />
              <path d="M16 11h5" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            Agentic Research Assistant
          </a>
        </div>
      </header>
      {inPaper && !needsPassword && (
        <div className="wrap">
          <PaperBar documentId={documentId} page={page} navigate={navigate} />
        </div>
      )}
      <main id="main" tabIndex={-1} className="wrap main">
        {content}
      </main>
    </>
  )
}
