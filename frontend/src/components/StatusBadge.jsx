// Statuses are always shown as text plus a symbol, never by colour alone (spec §12.4).
const STYLES = {
  verified: ['✓', 'Verified', 'bg-emerald-50 text-emerald-800 ring-emerald-600/30'],
  partially_supported: ['◐', 'Partially supported', 'bg-amber-50 text-amber-900 ring-amber-600/30'],
  unsupported: ['✕', 'Unsupported', 'bg-red-50 text-red-800 ring-red-600/30'],
  contradicted: ['⚠', 'Contradicted', 'bg-red-100 text-red-900 ring-red-700/40'],
  not_verifiable: ['?', 'Not verifiable', 'bg-slate-100 text-slate-700 ring-slate-500/30'],
  pending: ['…', 'Pending', 'bg-slate-50 text-slate-600 ring-slate-400/30'],
  extracted: ['✓', 'Extracted', 'bg-emerald-50 text-emerald-800 ring-emerald-600/30'],
  partially_extracted: ['◐', 'Partially extracted', 'bg-amber-50 text-amber-900 ring-amber-600/30'],
  ambiguous: ['?', 'Ambiguous', 'bg-amber-50 text-amber-900 ring-amber-600/30'],
  not_found: ['–', 'Not found in paper', 'bg-slate-100 text-slate-600 ring-slate-400/30'],
  failed: ['✕', 'Could not be processed', 'bg-red-50 text-red-800 ring-red-600/30'],
  completed: ['✓', 'Completed', 'bg-emerald-50 text-emerald-800 ring-emerald-600/30'],
  partial: ['◐', 'Partial', 'bg-amber-50 text-amber-900 ring-amber-600/30'],
  running: ['⟳', 'Running', 'bg-sky-50 text-sky-800 ring-sky-600/30'],
  skipped: ['–', 'Skipped', 'bg-slate-100 text-slate-600 ring-slate-400/30'],
  interrupted: ['!', 'Interrupted', 'bg-amber-50 text-amber-900 ring-amber-600/30'],
  indexed: ['✓', 'Indexed', 'bg-sky-50 text-sky-800 ring-sky-600/30'],
  partially_indexed: ['◐', 'Partially indexed', 'bg-amber-50 text-amber-900 ring-amber-600/30'],
  analyzed: ['✓', 'Analysed', 'bg-emerald-50 text-emerald-800 ring-emerald-600/30'],
  partially_analyzed: ['◐', 'Partially analysed', 'bg-amber-50 text-amber-900 ring-amber-600/30'],
  uploaded: ['•', 'Uploaded', 'bg-slate-50 text-slate-700 ring-slate-400/30'],
  queued: ['…', 'Queued', 'bg-slate-50 text-slate-700 ring-slate-400/30'],
  processing: ['⟳', 'Processing', 'bg-sky-50 text-sky-800 ring-sky-600/30'],
}

export default function StatusBadge({ status }) {
  const [symbol, label, className] = STYLES[status] ?? ['•', status ?? 'unknown', STYLES.pending[2]]
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${className}`}
    >
      <span aria-hidden="true">{symbol}</span>
      {label}
    </span>
  )
}
