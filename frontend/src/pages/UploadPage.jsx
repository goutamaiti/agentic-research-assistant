import { useCallback, useEffect, useRef, useState } from 'react'
import HealthStatus from '../components/HealthStatus.jsx'
import StatusBadge from '../components/StatusBadge.jsx'
import { api, getHealth } from '../services/api.js'

const ACTIVE = ['queued', 'processing']
const STAGE_LABELS = {
  upload_validation: 'Upload validation',
  document_extraction: 'Document extraction',
  section_identification: 'Section identification',
  retrieval_indexing: 'Retrieval indexing',
  knowledge_extraction: 'Knowledge extraction',
  evidence_verification: 'Evidence verification',
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

  if (error) return <p className="text-sm text-red-700">{error.message}</p>
  if (!status) return <p className="text-sm text-slate-500">Loading status…</p>
  return (
    <div className="mt-3 space-y-2">
      <p className="text-sm text-slate-700">{status.status_detail}</p>
      <ol className="divide-y divide-slate-100 rounded-md border border-slate-200">
        {status.stages.map((stage) => (
          <li key={stage.stage} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
            <span>{STAGE_LABELS[stage.stage] ?? stage.stage}</span>
            <span className="flex items-center gap-2">
              {stage.error && <span className="text-xs text-red-700">{stage.error.message}</span>}
              <StatusBadge status={stage.status} />
            </span>
          </li>
        ))}
      </ol>
    </div>
  )
}

export default function UploadPage({ navigate }) {
  const [documents, setDocuments] = useState([])
  const [selected, setSelected] = useState(null)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState(null)
  const [healthError, setHealthError] = useState(null)
  const fileInput = useRef(null)

  const refresh = useCallback(async () => {
    try {
      setDocuments(await api.listDocuments())
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }, [])

  const checkHealth = useCallback(async () => {
    try {
      setHealth(await getHealth())
      setHealthError(null)
    } catch (err) {
      setHealthError(err)
    }
  }, [])

  useEffect(() => {
    refresh()
    checkHealth()
  }, [refresh, checkHealth])

  const upload = async (event) => {
    event.preventDefault()
    const file = fileInput.current?.files?.[0]
    if (!file) return
    setBusy(true)
    setMessage(null)
    try {
      const document = await api.uploadDocument(file)
      await api.analyze(document.id)
      setSelected(document.id)
      setMessage({ kind: 'ok', text: `Uploaded ${document.original_filename}; analysis started.` })
      fileInput.current.value = ''
    } catch (err) {
      const existing = err.code === 'duplicate_document' ? ' Open it from the list below.' : ''
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
      refresh()
    } catch (err) {
      setMessage({ kind: 'error', text: err.message })
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">Upload a research paper</h2>
        <p className="mt-1 text-sm text-slate-600">One PDF per workspace (max 30 MB).</p>
        <form onSubmit={upload} className="mt-4 flex flex-wrap items-center gap-3">
          <input ref={fileInput} type="file" accept="application/pdf,.pdf" className="text-sm" />
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {busy ? 'Uploading…' : 'Upload and analyse'}
          </button>
        </form>
        {message && (
          <p role="status" className={`mt-3 text-sm ${message.kind === 'error' ? 'text-red-700' : 'text-emerald-800'}`}>
            {message.text}
          </p>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">Paper workspaces</h2>
        {documents.length === 0 && <p className="mt-2 text-sm text-slate-500">No papers yet.</p>}
        <ul className="mt-3 divide-y divide-slate-100">
          {documents.map((doc) => (
            <li key={doc.id} className="py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button type="button" className="text-left" onClick={() => setSelected(doc.id === selected ? null : doc.id)}>
                  <span className="font-medium text-slate-900">{doc.title ?? doc.original_filename}</span>
                  <span className="ml-2 text-xs text-slate-500">{doc.page_count} pages</span>
                </button>
                <span className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={doc.status} />
                  {['analyzed', 'partially_analyzed'].includes(doc.status) && (
                    <>
                      <button type="button" className="text-sm text-sky-700 underline" onClick={() => navigate(`analysis/${doc.id}`)}>Analysis</button>
                      <button type="button" className="text-sm text-sky-700 underline" onClick={() => navigate(`evidence/${doc.id}`)}>Evidence</button>
                    </>
                  )}
                  {!['uploaded', 'queued', 'processing', 'failed'].includes(doc.status) && (
                    <button type="button" className="text-sm text-sky-700 underline" onClick={() => navigate(`assistant/${doc.id}`)}>Assistant</button>
                  )}
                  {!ACTIVE.includes(doc.status) && (
                    <button type="button" className="text-sm text-slate-600 underline" onClick={() => reanalyze(doc.id)}>Analyse again</button>
                  )}
                </span>
              </div>
              {selected === doc.id && <Stages documentId={doc.id} onDone={refresh} />}
            </li>
          ))}
        </ul>
      </section>

      <HealthStatus health={health} error={healthError} loading={false} onRetry={checkHealth} />
    </div>
  )
}
