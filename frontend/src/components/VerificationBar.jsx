import { StatusGlyph, statusLabel } from './StatusBadge.jsx'
import { VERIFICATION_ORDER } from '../lib/paper.js'

// Proportion of claims per verification status. Segments differ by pattern as well as hue,
// and every count is also written out in the legend.
export default function VerificationBar({ counts, total }) {
  const present = VERIFICATION_ORDER.filter((s) => counts[s])
  return (
    <div className="vbar">
      <p className="vbar-headline">
        <strong>{counts.verified ?? 0} of {total}</strong> claims verified against the paper&rsquo;s text
      </p>
      <div className="vbar-track" role="img" aria-label={present.map((s) => `${counts[s]} ${statusLabel(s).toLowerCase()}`).join(', ')}>
        {present.map((status, index) => (
          <span
            key={status}
            className="vbar-seg"
            data-status={status}
            style={{ flexGrow: counts[status], '--i': index }}
          />
        ))}
      </div>
      <ul className="vbar-legend">
        {present.map((status) => (
          <li key={status} data-status={status}>
            <StatusGlyph status={status} size={14} />
            <span>{statusLabel(status)} {counts[status]}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
