import { useEffect, useState } from 'react'
import { api } from '../services/api.js'

function Citations({ citations }) {
  if (!citations?.length) return null
  return (
    <ul className="mt-2 space-y-1">
      {citations.map((c) => (
        <li key={c.passage_id + c.chunk_id}>
          <details className="text-xs text-slate-600">
            <summary className="cursor-pointer">
              Page {c.displayed_page_number ?? `PDF ${c.pdf_page_index}`} · {c.section_name ?? 'section unknown'}
            </summary>
            <p className="mt-1 border-l-4 border-slate-300 pl-3 text-slate-700">{c.text}</p>
          </details>
        </li>
      ))}
    </ul>
  )
}

export default function AssistantPage({ documentId }) {
  const [messages, setMessages] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .getHistory(documentId)
      .then((history) => {
        setMessages(history.messages)
        setConversationId(history.conversation_id)
      })
      .catch(setError)
  }, [documentId])

  const ask = async (event) => {
    event.preventDefault()
    const text = question.trim()
    if (!text) return
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

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold">Research assistant</h2>
        <p className="mt-1 text-sm text-slate-600">
          Answers use only this paper and cite the pages they come from.
        </p>
        <ul className="mt-4 space-y-3">
          {messages.map((m, index) => (
            <li key={index} className={`rounded-md p-3 text-sm ${m.role === 'user' ? 'bg-slate-100' : 'border border-slate-200'}`}>
              <p className="text-xs font-medium uppercase text-slate-500">{m.role === 'user' ? 'You' : 'Assistant'}</p>
              <p className="mt-1 whitespace-pre-wrap">{m.content}</p>
              {m.insufficient_evidence && (
                <p className="mt-1 text-xs font-medium text-amber-800">! Insufficient evidence in the paper</p>
              )}
              {m.general_explanation && (
                <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-900">
                  General explanation (not from the paper): {m.general_explanation}
                </p>
              )}
              <Citations citations={m.citations} />
            </li>
          ))}
        </ul>
        {error && <p role="alert" className="mt-3 text-sm text-red-700">{error.message}</p>}
        <form onSubmit={ask} className="mt-4 flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask about this paper…"
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button type="submit" disabled={busy} className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
            {busy ? 'Thinking…' : 'Ask'}
          </button>
        </form>
      </section>
    </div>
  )
}
