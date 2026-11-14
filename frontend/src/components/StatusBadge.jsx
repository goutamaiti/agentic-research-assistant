// A status is always a shape plus a word, never colour alone.
// [shape, label, tone]
const STATUS = {
  verified: ['check', 'Verified', 'good'],
  partially_supported: ['half', 'Partially supported', 'mid'],
  unsupported: ['cross', 'Unsupported', 'bad'],
  contradicted: ['warn', 'Contradicted', 'bad'],
  not_verifiable: ['dashed', 'Not verifiable', 'neutral'],
  pending: ['clock', 'Pending', 'neutral'],
  extracted: ['check', 'Extracted', 'good'],
  partially_extracted: ['half', 'Partially extracted', 'mid'],
  ambiguous: ['dashed', 'Ambiguous', 'mid'],
  not_found: ['dash', 'Not found in paper', 'neutral'],
  failed: ['cross', 'Could not be processed', 'bad'],
  completed: ['check', 'Completed', 'good'],
  partial: ['half', 'Partial', 'mid'],
  running: ['run', 'Running', 'info'],
  skipped: ['dash', 'Skipped', 'neutral'],
  interrupted: ['warn', 'Interrupted', 'mid'],
  indexed: ['check', 'Indexed', 'info'],
  partially_indexed: ['half', 'Partially indexed', 'mid'],
  analyzed: ['check', 'Analysed', 'good'],
  partially_analyzed: ['half', 'Partially analysed', 'mid'],
  uploaded: ['dot', 'Uploaded', 'neutral'],
  queued: ['clock', 'Queued', 'neutral'],
  processing: ['run', 'Processing', 'info'],
  ok: ['check', 'OK', 'good'],
  configured: ['dot', 'Configured, not contacted', 'info'],
  not_configured: ['warn', 'Not configured', 'mid'],
  error: ['cross', 'Error', 'bad'],
}

export function statusLabel(status) {
  return STATUS[status]?.[1] ?? status ?? 'Unknown'
}

export function statusTone(status) {
  return STATUS[status]?.[2] ?? 'neutral'
}

export function StatusGlyph({ status, size = 16 }) {
  const shape = STATUS[status]?.[0] ?? 'dot'
  const line = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round' }
  let body
  switch (shape) {
    case 'check':
      body = (
        <>
          <circle cx="8" cy="8" r="7" fill="currentColor" />
          <path d="M4.8 8.3l2.2 2.2 4.2-4.6" {...line} stroke="var(--glyph-ink)" />
        </>
      )
      break
    case 'half':
      body = (
        <>
          <circle cx="8" cy="8" r="6.2" {...line} />
          <path d="M8 1.8a6.2 6.2 0 0 0 0 12.4z" fill="currentColor" />
        </>
      )
      break
    case 'cross':
      body = (
        <>
          <circle cx="8" cy="8" r="6.2" {...line} />
          <path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8" {...line} />
        </>
      )
      break
    case 'warn':
      body = (
        <>
          <path d="M8 1.8L14.6 13.4H1.4z" {...line} />
          <path d="M8 6.2v3.3M8 11.4v.1" {...line} />
        </>
      )
      break
    case 'dashed':
      body = (
        <>
          <circle cx="8" cy="8" r="6.2" {...line} strokeDasharray="2.2 2.2" />
          <circle cx="8" cy="8" r="1" fill="currentColor" />
        </>
      )
      break
    case 'clock':
      body = (
        <>
          <circle cx="8" cy="8" r="6.2" {...line} />
          <path d="M8 4.6V8l2.3 1.5" {...line} />
        </>
      )
      break
    case 'run':
      body = <path d="M8 1.8a6.2 6.2 0 1 0 6.2 6.2" {...line} className="glyph-spin" />
      break
    case 'dash':
      body = (
        <>
          <circle cx="8" cy="8" r="6.2" {...line} />
          <path d="M5.2 8h5.6" {...line} />
        </>
      )
      break
    default:
      body = <circle cx="8" cy="8" r="2.6" fill="currentColor" />
  }
  return (
    <svg className="glyph" width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      {body}
    </svg>
  )
}

export default function StatusBadge({ status, label }) {
  return (
    <span className="status" data-tone={statusTone(status)}>
      <StatusGlyph status={status} />
      <span>{label ?? statusLabel(status)}</span>
    </span>
  )
}
