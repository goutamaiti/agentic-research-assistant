import { useCallback, useEffect, useRef, useState } from 'react'
import ErrorNotice from '../components/ErrorNotice.jsx'
import HealthStatus from '../components/HealthStatus.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { api, getHealth } from '../services/api.js'

const ACTIVE = ['queued', 'processing']
const STAGE_LABELS = {
  upload_validation: 'Check the upload',
  document_extraction: 'Read the PDF',
  section_identification: 'Find the sections',
  retrieval_indexing: 'Index the text for search',
  knowledge_extraction: 'Extract claims',
  evidence_verification: 'Verify claims against quotes',
}

function Stages({ documentId, onDone }) {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let timer
    let cancelled = false
    const poll = async () => {
      try {
        const next = await api.getStatus(documentId)
        if (cancelled) return
        setStatus(next)
        setError(null)
        if (ACTIVE.includes(next.status)) timer = setTimeout(poll, 2000)
        else onDone?.()
      } catch (err) {
        if (!cancelled) setError(err)
      }
    }
    poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [documentId, onDone])

  if (error) return <ErrorNotice error={error} title="Progress could not be loaded" />
  if (!status) return <p className="muted small" role="status">Loading progress</p>
  return (
    <div className="stages">
      <p className="small">{status.status_detail}</p>
      <ol>
        {status.stages.map((stage, index) => (
          <li key={stage.stage} data-state={stage.status}>
            <span className="stage-n">{index + 1}</span>
            <span className="stage-label">{STAGE_LABELS[stage.stage] ?? stage.stage.replaceAll('_', ' ')}</span>
            <StatusBadge status={stage.status} />
            {stage.error && <span className="stage-error">{stage.error.message}</span>}
          </li>
        ))}
      </ol>
    </div>
  )
}

function PaperRow({ doc, selected, onSelect, navigate, onReanalyze, onDone }) {
  const analysed = ['analyzed', 'partially_analyzed'].includes(doc.status)
  const askable = !['uploaded', 'queued', 'processing', 'failed'].includes(doc.status)
  const busy = ACTIVE.includes(doc.status)
  return (
    <li className="paper">
      <div className="paper-main">
        <h3>
          {analysed ? (
            <a href={`#/analysis/${doc.id}`} onClick={(e) => { e.preventDefault(); navigate(`analysis/${doc.id}`) }}>
              {doc.title ?? doc.original_filename}
            </a>
          ) : (
            doc.title ?? doc.original_filename
          )}
        </h3>
        <p className="muted small">
          {doc.title ? `${doc.original_filename}, ` : ''}{doc.page_count} {doc.page_count === 1 ? 'page' : 'pages'}
        </p>
        <StatusBadge status={doc.status} />
      </div>
      <div className="paper-actions">
        {analysed && (
          <>
            <button type="button" className="link-button" onClick={() => navigate(`analysis/${doc.id}`)}>Open analysis</button>
            <button type="button" className="link-button" onClick={() => navigate(`evidence/${doc.id}`)}>Check evidence</button>
          </>
        )}
        {askable && (
          <button type="button" className="link-button" onClick={() => navigate(`assistant/${doc.id}`)}>Ask questions</button>
        )}
        {!busy && (
          <button type="button" className="link-button quiet" onClick={() => onReanalyze(doc.id)}>Analyse again</button>
        )}
        <button
          type="button"
          className="link-button quiet"
          aria-expanded={selected}
          onClick={() => onSelect(selected ? null : doc.id)}
        >
          {selected ? 'Hide progress' : 'Show progress'}
        </button>
      </div>
      {selected && <Stages documentId={doc.id} onDone={onDone} />}
    </li>
  )
}

export default function UploadPage({ navigate }) {
  const [documents, setDocuments] = useState([])
  const [loadedList, setLoadedList] = useState(false)
  const [selected, setSelected] = useState(null)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [fileName, setFileName] = useState('')
  const [health, setHealth] = useState(null)
  const [healthError, setHealthError] = useState(null)
  const [checking, setChecking] = useState(false)
  const fileInput = useRef(null)

  const refresh = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments())
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    } finally {
      setLoadedList(true)
    }
  }, [])

  const checkHealth = useCallback(async () => {
    setChecking(true)
    try {
      setHealth(await getHealth())
      setHealthError(null)
    } catch (err) {
      setHealthError(err)
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    checkHealth()
  }, [refresh, checkHealth])

  // Show live progress for anything already running when the page opens.
  useEffect(() => {
    if (selected === null) {
      const running = documents.find((d) => ACTIVE.includes(d.status))
      if (running) setSelected(running.id)
    }
  }, [documents, selected])

  const upload = async (event) => {
    event.preventDefault()
    const file = fileInput.current?.files?.[0]
    if (!file) {
      setMessage({ kind: 'error', text: 'Choose a PDF first.' })
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      const document = await api.uploadDocument(file)
      await api.analyze(document.id)
      setSelected(document.id)
      setMessage({ kind: 'ok', text: `Uploaded ${document.original_filename}. Analysis has started.` })
      fileInput.current.value = ''
      setFileName('')
    } catch (err) {
      const existing = err.code === 'duplicate_document' ? ' Open it from the list of papers.' : ''
      setMessage({ kind: 'error', text: err.message + existing })
    } finally {
      setBusy(false)
      refresh()
    }
  }

  const reanalyze = async (id) => {
    try {
      await api.analyze(id)
      setSelected(id)
      setMessage(null)
      refresh()
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }

  const onDrop = (event) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (file && fileInput.current) {
      const transfer = new DataTransfer()
      transfer.items.add(file)
      fileInput.current.files = transfer.files
      setFileName(file.name)
    }
  }

  return (
    <div className="home">
      <HealthStatus health={null} error={healthError} loading={checking} onRetry={checkHealth} />

      <div className="home-grid">
        <section className="intake" aria-labelledby="intake-heading">
          <h2 id="intake-heading">Analyse a paper</h2>
          <p>
            Upload one PDF, up to 30 MB. Every claim the assistant extracts is tied to a quote and a page number from the paper.
          </p>
          <form onSubmit={upload}>
            <label
              className="drop"
              data-dragging={dragging ? 'yes' : 'no'}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <input
                ref={fileInput}
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => setFileName(e.target.files?.[0]?.name ?? '')}
              />
              <span className="drop-main">{fileName || 'Drop a PDF here'}</span>
              <span className="drop-sub">{fileName ? 'Choose a different file' : 'or choose a file from your computer'}</span>
            </label>
            <button type="submit" disabled={busy} className="button primary">
              {busy ? 'Uploading' : 'Upload and analyse'}
            </button>
          </form>
          {message && message.kind === 'error' && <ErrorNotice error={{ message: message.text }} title="Upload failed" hint="Fix the problem above and try again." />}
          {message && message.kind === 'ok' && <p role="status" className="ok-text">{message.text}</p>}
        </section>

        <section className="library" aria-labelledby="library-heading">
          <h2 id="library-heading">Your papers</h2>
          {loadedList && documents.length === 0 && (
            <p className="muted">No papers yet. Upload a PDF to see its analysis here.</p>
          )}
          <ul className="papers">
            {documents.map((doc) => (
              <PaperRow
                key={doc.id}
                doc={doc}
                selected={selected === doc.id}
                onSelect={setSelected}
                navigate={navigate}
                onReanalyze={reanalyze}
                onDone={refresh}
              />
            ))}
          </ul>
        </section>
      </div>

      <HealthStatus health={health} error={null} loading={checking} onRetry={checkHealth} />
    </div>
  )
}
