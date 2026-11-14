// Shared knowledge about the shape of an analysis result.

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

// Most worrying first; used to summarise a section by its weakest claim.
export const SEVERITY = ['contradicted', 'unsupported', 'partially_supported', 'pending', 'not_verifiable', 'verified']

export const VERIFICATION_ORDER = ['verified', 'partially_supported', 'not_verifiable', 'pending', 'unsupported', 'contradicted']

export function pageText(evidence) {
  if (evidence.pdf_page_index === null || evidence.pdf_page_index === undefined) return null
  return evidence.displayed_page_number
    ? `p. ${evidence.displayed_page_number}`
    : `PDF page ${evidence.pdf_page_index + 1}`
}

export function pageLabel(evidence) {
  const pages = [...new Set(evidence.map(pageText).filter(Boolean))]
  return pages.length === 0 ? 'no located source' : pages.join(', ')
}

export function claimsFor(result, part, name) {
  const prefix = `${part}.${name}`
  return result.claims.filter((c) => c.field_path === prefix || c.field_path.startsWith(`${prefix}.`))
}

export function weakestStatus(claims) {
  if (claims.length === 0) return null
  return SEVERITY.find((status) => claims.some((c) => c.verification_status === status)) ?? 'pending'
}

export function summarise(claims) {
  const counts = {}
  for (const c of claims) counts[c.verification_status] = (counts[c.verification_status] ?? 0) + 1
  return counts
}
