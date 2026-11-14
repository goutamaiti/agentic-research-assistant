import { useId, useState } from 'react'
import { ORIGIN, pageLabel } from '../lib/paper.js'
import Sheet from './Sheet.jsx'
import StatusBadge from './StatusBadge.jsx'

// One claim, joined by a thread to the quotes that support it.
// layout "split": claim left, quotes right, always shown (Evidence page).
// layout "stack": quotes revealed on request (Analysis page).
export default function ClaimEntry({ claim, evidence, layout = 'stack', showExplanation = false, showMeta = false }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const located = evidence.some((e) => e.pdf_page_index !== null && e.pdf_page_index !== undefined)
  const shown = layout === 'split' || open
  const quoteCount = evidence.length

  return (
    <li className="entry" data-layout={layout} data-status={claim.verification_status} data-open={shown ? 'yes' : 'no'}>
      <div className="entry-claim">
        <p className="claim-text">{claim.claim_text}</p>
        <p className="claim-meta">
          <StatusBadge status={claim.verification_status} />
          <span>{ORIGIN[claim.origin] ?? claim.origin}</span>
          {showMeta && <span className="claim-id">{claim.claim_id}</span>}
        </p>
        {showExplanation && claim.verification_explanation && (
          <p className="claim-why">{claim.verification_explanation}</p>
        )}
        {layout === 'stack' && quoteCount > 0 && (
          <button
            type="button"
            className="link-button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? 'Hide quote' : located ? `Show quote, ${pageLabel(evidence)}` : 'Show quote (no page found)'}
          </button>
        )}
        {quoteCount === 0 && <p className="claim-why">No quote is attached to this claim.</p>}
      </div>
      {quoteCount > 0 && (
        <div className="entry-quotes" id={panelId}>
          <div className="entry-quotes-inner">
            {evidence.map((e) => (
              <Sheet key={e.evidence_id} text={e.source_text} evidence={e} />
            ))}
          </div>
        </div>
      )}
    </li>
  )
}
