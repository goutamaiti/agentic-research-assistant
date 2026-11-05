// Thin client for the FastAPI backend. All requests go to same-origin /api paths
// (proxied by Vite in development), so no backend URL or credential lives in the bundle.

export class ApiError extends Error {
  constructor(message, { status = null, code = 'network_error' } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export async function request(path, { fetchImpl = fetch, ...init } = {}) {
  let response
  try {
    response = await fetchImpl(`/api${path}`, {
      headers: { Accept: 'application/json' },
      ...init,
    })
  } catch {
    throw new ApiError('Cannot reach the backend. Is the API server running?')
  }

  let body = null
  try {
    body = await response.json()
  } catch {
    // Non-JSON body (e.g. proxy error page); handled below.
  }

  if (!response.ok) {
    const message = body?.error?.message ?? `Request failed with status ${response.status}`
    throw new ApiError(message, {
      status: response.status,
      code: body?.error?.code ?? `http_${response.status}`,
    })
  }
  if (body === null) {
    throw new ApiError('The backend returned an unreadable response.', {
      status: response.status,
      code: 'invalid_response',
    })
  }
  return body
}

export function getHealth(options) {
  return request('/health', options)
}

const postJson = (path, data) =>
  request(path, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(data ?? {}),
  })

export const api = {
  listDocuments: () => request('/documents'),
  getDocument: (id) => request(`/documents/${id}`),
  uploadDocument: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/documents/upload', { method: 'POST', body: form })
  },
  analyze: (id) => postJson(`/documents/${id}/analyze`),
  getStatus: (id) => request(`/documents/${id}/status`),
  getAnalysis: (id) => request(`/documents/${id}/analysis`),
  getEvidence: (id) => request(`/documents/${id}/evidence`),
  ask: (id, question, conversationId) =>
    postJson(`/documents/${id}/chat`, { question, conversation_id: conversationId ?? null }),
  getHistory: (id) => request(`/documents/${id}/chat/history`),
  createReport: (id, format) => postJson(`/documents/${id}/report`, { format }),
}
