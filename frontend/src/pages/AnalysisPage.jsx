import { useEffect, useState } from 'react'
import StatusBadge from '../components/StatusBadge.jsx'
import { api } from '../services/api.js'

export const SECTIONS = [
  ['Abstract', 'research_analysis', 'abstract'],
  ['Research problem', 'research_analysis', 'research_problem'],
  ['Objectives', 'research_analysis', 'objectives'],
  ['Motivation', 'research_analysis', 'motivation'],
  ['Background', 'research_analysis', 'background'],
  ['Methodology', 'research_analysis', 'methodology'],
  ['Algorithms and models', 'technical_analysis', 'algorithms_and_models'],
  ['Dataset and experiments', 'technical_analysis', 'dataset_and_experiments'],
  ['Results', 'research_analysis', 'results'],
  ['Limitations', 'research_analysis', 'limitations'],
  ['Future scope', 'research_analysis', 'future_scope'],
  ['Research contributions', 'technical_analysis', 'research_contributions'],
  ['Methodology breakdown', 'technical_analysis', 'methodology_breakdown'],
  ['Technical terminology', 'technical_analysis', 'technical_terminology'],
]

export const ORIGIN = {
  directly_extracted: 'From the paper',
  author_claimed: 'Author claim',
  system_inferred: 'System inference',
  system_explanation: 'System explanation',
}

export function pageLabel(evidence) {
  const located = evidence.filter((e) => e.pdf_page_index !== null)
  if (located.length === 0) return 'no located source'
  return [...new Set(located.map((e) => `p. ${e.displayed_page_number ?? `PDF ${e.pdf_page_index}`}`))].join(', ')
}

function MetadataRow({ label, field }) {
  const value = Array.isArray(field.value) ? field.value.join(', ') : field.value
  return (
    <div className="flex flex-wrap gap-2 py-1 text-sm">
      <dt className="w-40 shrink-0 text-slate-500">{label}</dt>
      <dd className="flex-1">{value ?? <span className="italic text-slate-500">not found in the paper</span>}</dd>
    </div>
  )
}

export default function AnalysisPage({ documentId }) {
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)

  useEffect(() => {
    api.getAnalysis(documentId).then(setAnalysis).catch(setError)
  }, [documentId])

  const download = async (format) => {
    try {
      const created = await api.createReport(documentId, format)
      setReport(created)
      window.open(created.download_url, '_blank', 'noopener')
    } catch (err) {
      setError(err)
    }
  }

  if (error) return <p className="text-sm text-red-700">{error.message}</p>
  if (!analysis) return <p className="text-sm text-slate-500">Loading analysis…</p>
  const result = analysis.result
  const evidence = Object.fromEntries(result.evidence_registry.map((e) => [e.evidence_id, e]))
  const md = result.paper_metadata

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 className="text-lg font-semibold">{md.title.value ?? 'Untitled paper'}</h2>
          <div className="flex gap-2">
            <button type="button" onClick={() => download('pdf')} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">Download PDF report</button>
            <button type="button" onClick={() => download('json')} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">Download JSON</button>
          </div>
        </div>
        {report && <p className="mt-1 text-xs text-slate-500">Report {report.report_id} generated.</p>}
        <dl className="mt-3">
          <MetadataRow label="Authors" field={md.authors} />
          <MetadataRow label="Year" field={md.publication_year} />
          <MetadataRow label="Venue" field={md.journal_or_conference} />
          <MetadataRow label="DOI" field={md.doi} />
          <MetadataRow label="Keywords" field={md.keywords} />
        </dl>
        <p className="mt-3 text-xs text-slate-500">
          Model {result.processing_metadata.model_id} · {result.claims.length} claims · statuses are
          checked automatically against the paper's text and can be wrong.
        </p>
      </section>

      {SECTIONS.map(([title, part, name]) => {
        const category = result[part][name]
        const prefix = `${part}.${name}`
        const claims = result.claims.filter((c) => c.field_path === prefix || c.field_path.startsWith(`${prefix}.`))
        return (
          <section key={name} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold">{title}</h3>
              <StatusBadge status={category.task_status === 'failed' ? 'failed' : category.status} />
            </div>
            {category.note && <p className="mt-1 text-xs text-slate-500">{category.note}</p>}
            {name === 'abstract' && category.original_abstract?.value && (
              <p className="mt-2 text-sm text-slate-700">{category.original_abstract.value}</p>
            )}
            <ul className="mt-3 space-y-2">
              {claims.map((claim) => (
                <li key={claim.claim_id} className="rounded-md bg-slate-50 p-3 text-sm">
                  <p>{claim.claim_text}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                    <span className="font-medium">{ORIGIN[claim.origin]}</span>
                    <StatusBadge status={claim.verification_status} />
                    <span>{pageLabel(claim.evidence_ids.map((id) => evidence[id]).filter(Boolean))}</span>
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
