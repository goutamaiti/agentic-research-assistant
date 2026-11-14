import { pageText } from '../lib/paper.js'

const MATCH_NOTE = {
  normalized: 'Matched after ignoring spacing and punctuation differences',
  pdf_metadata: 'From the PDF file’s embedded metadata, not printed on a page',
}

// A white "page" holding the paper's own words, with the printed page folio.
export default function Sheet({ text, evidence, section, folio, note }) {
  const located = evidence ? evidence.pdf_page_index !== null && evidence.pdf_page_index !== undefined : true
  const folioText = folio ?? (evidence ? pageText(evidence) : null)
  const sectionName = section ?? evidence?.section_name
  const matchNote = note ?? (evidence ? MATCH_NOTE[evidence.quote_match] : null)
  return (
    <figure className="sheet" data-located={located ? 'yes' : 'no'}>
      {folioText && <span className="folio">{folioText}</span>}
      <blockquote>
        <span className="quote">{text}</span>
      </blockquote>
      <figcaption>
        {!located && <span>Quote not found in the paper, so it has no page.</span>}
        {located && sectionName && <span>{sectionName}</span>}
        {matchNote && <span>{matchNote}</span>}
      </figcaption>
    </figure>
  )
}
