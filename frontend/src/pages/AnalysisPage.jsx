import { useEffect, useMemo, useRef, useState } from 'react'
import ClaimEntry from '../components/ClaimEntry.jsx'
import ErrorNotice from '../components/ErrorNotice.jsx'
import StatusBadge, { StatusGlyph, statusLabel } from '../components/StatusBadge.jsx'
import VerificationBar from '../components/VerificationBar.jsx'
import { SECTIONS, claimsFor, summarise, weakestStatus } from '../lib/paper.js'
import { api } from '../services/api.js'

// Re-exported so existing imports keep working.
export { ORIGIN, SECTIONS, pageLabel } from '../lib/paper.js'

function MetaRow({ label, field }) {
  const value = Array.isArray(field.value) ? field.value.join(', ') : field.value
  if (value === null || value === undefined || value === '') {
    return (
      <>
        <dt>{label}</dt>
        <dd className="muted">Not found in the paper</dd>
      </>
    )
  }
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  )
}

function Contents({ items, active, onPick }) {
  return (
    <ol className="toc-list">
      {items.map(({ name, title, weakest }) => (
        <li key={name}>
          <button type="button" onClick={() => onPick(name)} aria-current={active === name ? 'true' : undefined}>
            <span>{title}</span>
            {weakest ? (
              <span className="toc-mark" data-status={weakest}>
                <StatusGlyph status={weakest} size={14} />
                <span className="sr-only">Weakest claim: {statusLabel(weakest)}</span>
              </span>
            ) : (
              <span className="toc-mark" data-status="none">
                <StatusGlyph status="not_found" size={14} />
                <span className="sr-only">No claims</span>
              </span>
            )}
          </button>
        </li>
      ))}
    </ol>
  )
}

export default function AnalysisPage({ documentId }) {
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState(null)
  const [report, setReport] = useState(null)
  const [downloading, setDownloading] = useState(null)
  const [active, setActive] = useState(null)
  const sectionRefs = useRef({})

  useEffect(() => {
    api.getAnalysis(documentId).then(setAnalysis).catch(setError)
  }, [documentId])

  const download = async (format) => {
    setDownloading(format)
    try {
      const created = await api.createReport(documentId, format)
      setReport(created)
      window.open(created.download_url, '_blank', 'noopener')
    } catch (err) {
      setError(err)
    } finally {
      setDownloading(null)
    }
  }

  const result = analysis?.result
  const model = useMemo(() => {
    if (!result) return null
    const evidence = Object.fromEntries(result.evidence_registry.map((e) => [e.evidence_id, e]))
    const sections = SECTIONS.map(([title, part, name]) => {
      const claims = claimsFor(result, part, name)
      return { title, part, name, claims, category: result[part][name], weakest: weakestStatus(claims) }
    })
    return { evidence, sections, counts: summarise(result.claims) }
  }, [result])

  useEffect(() => {
    if (!model || typeof IntersectionObserver === 'undefined') return undefined
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActive(visible[0].target.dataset.section)
      },
      { rootMargin: '-10% 0px -75% 0px' },
    )
    Object.values(sectionRefs.current).forEach((el) => el && observer.observe(el))
    return () => observer.disconnect()
  }, [model])

  const jump = (name) => {
    const el = sectionRefs.current[name]
    if (!el) return
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    setActive(name)
  }

  if (error && !analysis) return <ErrorNotice error={error} title="The analysis could not be loaded" />
  if (!analysis) return <p className="muted" role="status">Loading analysis</p>

  const md = result.paper_metadata
  const toc = model.sections.map(({ name, title, weakest }) => ({ name, title, weakest }))

  return (
    <div className="analysis">
      <aside className="toc" aria-label="Sections">
        <p className="toc-heading">Sections</p>
        <Contents items={toc} active={active} onPick={jump} />
      </aside>

      <div className="analysis-body">
        <header className="paper-head">
          <h2 className="paper-title">{md.title.value ?? 'Untitled paper'}</h2>
          <dl className="meta">
            <MetaRow label="Authors" field={md.authors} />
            <MetaRow label="Year" field={md.publication_year} />
            <MetaRow label="Venue" field={md.journal_or_conference} />
            <MetaRow label="DOI" field={md.doi} />
            <MetaRow label="Keywords" field={md.keywords} />
          </dl>
          <div className="actions">
            <button type="button" className="button primary" onClick={() => download('pdf')} disabled={downloading !== null}>
              {downloading === 'pdf' ? 'Preparing PDF' : 'Download PDF report'}
            </button>
            <button type="button" className="button" onClick={() => download('json')} disabled={downloading !== null}>
              {downloading === 'json' ? 'Preparing JSON' : 'Download JSON report'}
            </button>
          </div>
          {report && <p className="muted small" role="status">Report {report.report_id} is ready. It opened in a new tab.</p>}
          {error && <ErrorNotice error={error} title="The report could not be created" />}
        </header>

        <VerificationBar counts={model.counts} total={result.claims.length} />
        <p className="caveat">
          Statuses are checked automatically against the paper&rsquo;s text and can be wrong. Open a quote to check it yourself.
        </p>

        <details className="toc-mobile">
          <summary>Jump to a section</summary>
          <Contents items={toc} active={active} onPick={(n) => { jump(n) }} />
        </details>

        {model.sections.map(({ title, name, claims, category }) => (
          <section
            key={name}
            className="section"
            data-section={name}
            ref={(el) => { sectionRefs.current[name] = el }}
            aria-labelledby={`h-${name}`}
          >
            <div className="section-head">
              <h3 id={`h-${name}`}>{title}</h3>
              {(category.task_status === 'failed' || category.status !== 'extracted') && (
                <StatusBadge status={category.task_status === 'failed' ? 'failed' : category.status} />
              )}
            </div>
            {category.note && <p className="muted small">{category.note}</p>}
            {name === 'abstract' && category.original_abstract?.value && (
              <p className="abstract">{category.original_abstract.value}</p>
            )}
            {claims.length > 0 ? (
              <ul className="entries">
                {claims.map((claim) => (
                  <ClaimEntry
                    key={claim.claim_id}
                    claim={claim}
                    evidence={claim.evidence_ids.map((id) => model.evidence[id]).filter(Boolean)}
                    layout="stack"
                  />
                ))}
              </ul>
            ) : (
              <p className="muted">No claims were extracted for this section.</p>
            )}
          </section>
        ))}

        <p className="provenance">
          Extracted with {result.processing_metadata.model_id}. {result.claims.length} claims, each tied to a quote where one could be found.
        </p>
      </div>
    </div>
  )
}
