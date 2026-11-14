import { useEffect, useMemo, useState } from 'react'
import ClaimEntry from '../components/ClaimEntry.jsx'
import ErrorNotice from '../components/ErrorNotice.jsx'
import { StatusGlyph, statusLabel } from '../components/StatusBadge.jsx'
import { VERIFICATION_ORDER } from '../lib/paper.js'
import { api } from '../services/api.js'

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

  if (error) return <ErrorNotice error={error} title="The evidence could not be loaded" />
  if (!data) return <p className="muted" role="status">Loading evidence</p>

  const count = (name) => (name === 'all' ? data.claims.length : data.verification_summary[name] ?? 0)
  const filters = ['all', ...VERIFICATION_ORDER.filter((s) => count(s) > 0)]

  return (
    <div className="evidence">
      <header className="evidence-head">
        <h2>Evidence for every claim</h2>
        <p>
          <strong>{count('verified')} of {data.claims.length}</strong> claims are verified against quotes from the paper.
          Checks are automatic and can be wrong, so read the quote beside each claim.
        </p>
      </header>

      <div className="filters" role="group" aria-label="Filter claims by verification status">
        {filters.map((name) => (
          <button key={name} type="button" onClick={() => setFilter(name)} aria-pressed={filter === name} data-status={name}>
            {name !== 'all' && <StatusGlyph status={name} size={14} />}
            <span>{name === 'all' ? 'All claims' : statusLabel(name)}</span>
            <span className="filter-count">{count(name)}</span>
          </button>
        ))}
      </div>

      {claims.length === 0 ? (
        <p className="muted">No claims have this status. Choose another filter.</p>
      ) : (
        <ul className="entries split" aria-live="polite">
          {claims.map((claim) => (
            <ClaimEntry
              key={claim.claim_id}
              claim={claim}
              evidence={claim.evidence}
              layout="split"
              showExplanation
              showMeta
            />
          ))}
        </ul>
      )}
    </div>
  )
}
