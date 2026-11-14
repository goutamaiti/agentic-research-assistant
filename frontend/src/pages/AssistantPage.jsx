import { useEffect, useRef, useState } from 'react'
import ErrorNotice from '../components/ErrorNotice.jsx'
import Sheet from '../components/Sheet.jsx'
import { StatusGlyph } from '../components/StatusBadge.jsx'
import { api } from '../services/api.js'

const SUGGESTIONS = [
  'What problem does this paper address?',
  'Which datasets were used?',
  'What limitations do the authors acknowledge?',
]

function citationFolio(c) {
  return c.displayed_page_number ? `p. ${c.displayed_page_number}` : `PDF page ${c.pdf_page_index + 1}`
}

function Citation({ citation }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="cite" data-open={open ? 'yes' : 'no'}>
      <button type="button" className="cite-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="cite-folio">{citationFolio(citation)}</span>
        <span>{citation.section_name ?? 'Section unknown'}</span>
        <span className="sr-only">{open ? 'Hide passage' : 'Show passage'}</span>
      </button>
      <div className="cite-panel">
        <div className="entry-quotes-inner">
          <Sheet text={citation.text} folio={citationFolio(citation)} section={citation.section_name} />
        </div>
      </div>
    </li>
  )
}

function Message({ message }) {
  if (message.role === 'user') {
    return (
      <li className="msg user">
        <p className="msg-who">You asked</p>
        <p className="msg-text">{message.content}</p>
      </li>
    )
  }
  return (
    <li className="msg assistant">
      <p className="msg-who">Answer</p>
      {message.insufficient_evidence && (
        <p className="notice" data-tone="mid">
          <StatusGlyph status="dashed" />
          <span><strong>Not enough evidence in the paper.</strong> The paper does not say enough to answer this reliably.</span>
        </p>
      )}
      <p className="msg-text">{message.content}</p>
      {message.citations?.length > 0 && (
        <ul className="cites" aria-label="Citations">
          {message.citations.map((c) => (
            <Citation key={`${c.passage_id}-${c.chunk_id}`} citation={c} />
          ))}
        </ul>
      )}
      {message.general_explanation && (
        <aside className="general">
          <p className="general-label">General background, not from the paper</p>
          <p>{message.general_explanation}</p>
        </aside>
      )}
    </li>
  )
}

export default function AssistantPage({ documentId }) {
  const [messages, setMessages] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(null)
  const endRef = useRef(null)

  useEffect(() => {
    api
      .getHistory(documentId)
      .then((history) => {
        setMessages(history.messages)
        setConversationId(history.conversation_id)
      })
      .catch(setError)
      .finally(() => setLoaded(true))
  }, [documentId])

  useEffect(() => {
    if (messages.length > 0 || busy) endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages, busy])

  const send = async (raw) => {
    const text = raw.trim()
    if (!text || busy) return
    setBusy(true)
    setError(null)
    setMessages((current) => [...current, { role: 'user', content: text, citations: [] }])
    setQuestion('')
    try {
      const reply = await api.ask(documentId, text, conversationId)
      setConversationId(reply.conversation_id)
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: reply.answer,
          citations: reply.citations,
          insufficient_evidence: reply.insufficient_evidence,
          general_explanation: reply.general_explanation,
        },
      ])
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const submit = (event) => {
    event.preventDefault()
    send(question)
  }

  const onKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      send(question)
    }
  }

  return (
    <div className="assistant">
      <header className="assistant-head">
        <h2>Ask this paper</h2>
        <p className="muted">Answers use only the paper and cite the pages they come from. If the paper does not say, the assistant says so.</p>
      </header>

      {loaded && messages.length === 0 && !error && (
        <div className="suggestions">
          <p>Start with a question:</p>
          <ul>
            {SUGGESTIONS.map((s) => (
              <li key={s}>
                <button type="button" className="chip" onClick={() => send(s)} disabled={busy}>{s}</button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ol className="transcript">
        {messages.map((m, index) => (
          <Message key={index} message={m} />
        ))}
        {busy && (
          <li className="msg assistant" role="status">
            <p className="msg-who">Answer</p>
            <p className="msg-text muted">Reading the paper</p>
          </li>
        )}
      </ol>
      <div ref={endRef} />

      {error && <ErrorNotice error={error} title="The question could not be answered" hint="Your question was not saved. Check your connection and ask again." />}

      <form onSubmit={submit} className="composer">
        <label htmlFor="question" className="sr-only">Your question about this paper</label>
        <textarea
          id="question"
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask a question about this paper"
        />
        <button type="submit" className="button primary" disabled={busy || !question.trim()}>
          {busy ? 'Answering' : 'Ask question'}
        </button>
      </form>
    </div>
  )
}
