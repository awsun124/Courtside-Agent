export class ApiError extends Error {
  constructor(message: string, public status = 0, public retryAfter = 0) {
    super(message)
  }
}

function apiUrl(path: string) {
  const base = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '')
  if (!base) return path
  let url: URL
  try { url = new URL(base) } catch { throw new ApiError('The API address is configured incorrectly.') }
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname)))) {
    throw new ApiError('The API address must be an HTTPS origin without credentials or a path.')
  }
  return `${url.origin}${path}`
}

export async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const cancel = () => controller.abort()
  options.signal?.addEventListener('abort', cancel, { once: true })
  if (options.signal?.aborted) controller.abort()
  const timer = window.setTimeout(cancel, options.method === 'POST' ? 135000 : 15000)
  try {
    const response = await fetch(apiUrl(path), { ...options, signal: controller.signal })
    const body = await response.json().catch(() => null)
    if (!response.ok) {
      const message = typeof body?.detail === 'string' ? body.detail : 'Could not reach Court Side. Check that the API is running.'
      const retryAfter = Number(response.headers.get('Retry-After'))
      throw new ApiError(message, response.status, Number.isFinite(retryAfter) ? retryAfter : 0)
    }
    if (!body) throw new ApiError('The API returned an unreadable response.')
    return body as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (controller.signal.aborted) throw new ApiError('The request took too long. Your saved briefing is still available.')
    throw new ApiError('Could not reach Court Side. Check the API connection and try again.')
  } finally {
    window.clearTimeout(timer)
    options.signal?.removeEventListener('abort', cancel)
  }
}
