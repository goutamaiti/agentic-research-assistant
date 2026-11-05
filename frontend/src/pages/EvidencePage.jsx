import { useEffect, useMemo, useState } from 'react'
import StatusBadge from '../components/StatusBadge.jsx'
import { api } from '../services/api.js'
import { ORIGIN, pageLabel } from './AnalysisPage.jsx'

const FILTERS = ['all', 'verified', 'partially_supported', 'unsupported', 'contradicted', 'not_verifiable', 'pending']

export default function EvidencePage({ documentId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    api.getEvidence(documentId).then(setData).catch(setError)
  }, [documentId])

  const claims = useMemo(
    () => (data ? data.claims.filter((c) => filter === 'all' || c.verification_status === filter) : []),
    [data, filter],
  )

  if (error) return <p className="text-sm text-red-700">{error.message}</p>
  if (!data) return <p className="text-sm text-slate-500">Loading evidence…</p>

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">Evidence verification</h2>
        <p className="mt-1 text-sm text-slate-600">
          Each claim is checked against the quoted passages from the paper. Verification is
          automatic and can be wrong.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {FILTERS.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setFilter(name)}
              aria-pressed={filter === name}
              className={`rounded-md border px-2 py-1 text-xs ${filter === name ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-300'}`}
            >
              {name.replace('_', ' ')} ({name === 'all' ? data.claims.length : data.verification_summary[name] ?? 0})
            </button>
          ))}
        </div>
      </section>

      {claims.map((claim) => (
        <article key={claim.claim_id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="text-sm font-medium">{claim.claim_text}</p>
            <StatusBadge status={claim.verification_status} />
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {claim.claim_id} · {claim.category.replace('_', ' ')} · {ORIGIN[claim.origin]} · {pageLabel(claim.evidence)}
          </p>
          {claim.verification_explanation && (
            <p className="mt-2 text-sm text-slate-700">{claim.verification_explanation}</p>
          )}
          {claim.evidence.map((e) => (
            <blockquote key={e.evidence_id} className="mt-2 border-l-4 border-slate-300 pl-3 text-sm text-slate-700">
              “{e.source_text}”
              <footer className="text-xs text-slate-500">
                {e.pdf_page_index === null
                  ? 'Quote not found in the paper'
                  : `Page ${e.displayed_page_number ?? `PDF ${e.pdf_page_index}`} · ${e.section_name ?? 'section unknown'}`}
              </footer>
            </blockquote>
          ))}
        </article>
      ))}
    </div>
  )
}
