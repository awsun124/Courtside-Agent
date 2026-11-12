import { afterEach, describe, expect, it, vi } from 'vitest'
import { requestJson } from './api'

afterEach(() => vi.unstubAllEnvs())
describe('deployment API routing', () => {
  it('uses the configured backend origin for API requests', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://backend.example.com/')
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })))
    vi.stubGlobal('fetch', fetchMock)
    expect(await requestJson('/api/stats')).toEqual({ ok: true })
    expect(fetchMock.mock.calls[0][0]).toBe('https://backend.example.com/api/stats')
  })
  it('rejects insecure remote addresses and credentials before making requests', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    for (const base of ['http://remote.example.com', 'https://secret@example.com', 'https://example.com/path', 'https://example.com?key=private']) {
      vi.stubEnv('VITE_API_BASE_URL', base)
      await expect(requestJson('/api/stats')).rejects.toThrow('API address')
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
