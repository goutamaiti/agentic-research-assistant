import { describe, expect, it } from 'vitest'
import { ApiError, getHealth } from './api.js'

const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
})

describe('getHealth', () => {
  it('requests the same-origin /api/health path and returns the body', async () => {
    const calls = []
    const fetchImpl = async (url, init) => {
      calls.push({ url, init })
      return jsonResponse(200, { status: 'ok' })
    }
    await expect(getHealth({ fetchImpl })).resolves.toEqual({ status: 'ok' })
    expect(calls[0].url).toBe('/api/health')
  })

  it('surfaces structured backend errors', async () => {
    const fetchImpl = async () =>
      jsonResponse(500, { error: { code: 'internal_error', message: 'boom' } })
    await expect(getHealth({ fetchImpl })).rejects.toMatchObject({
      name: 'ApiError',
      status: 500,
      code: 'internal_error',
      message: 'boom',
    })
  })

  it('reports an unreachable backend clearly', async () => {
    const fetchImpl = async () => {
      throw new TypeError('Failed to fetch')
    }
    const error = await getHealth({ fetchImpl }).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe('network_error')
  })

  it('rejects non-JSON responses', async () => {
    const fetchImpl = async () => ({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError('Unexpected token <')
      },
    })
    await expect(getHealth({ fetchImpl })).rejects.toMatchObject({ code: 'invalid_response' })
  })
})

describe('access password', () => {
  it('sends no password header unless one was entered', async () => {
    const calls = []
    const fetchImpl = async (url, init) => {
      calls.push(init)
      return jsonResponse(200, { status: 'ok' })
    }
    await getHealth({ fetchImpl })
    expect(calls[0].headers['X-Access-Password']).toBeUndefined()
    expect(calls[0].headers.Accept).toBe('application/json')
  })
})
