import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { makeLatest, now } from './test/fixtures'
import type { LatestResponse } from './types'

const fetchMock = vi.fn<typeof fetch>()

function json(value: unknown, status = 200, headers?: HeadersInit) {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json', ...headers } })
}

function serve(latest = makeLatest()) {
  fetchMock.mockImplementation(async input => {
    const path = String(input)
    const mode = path.includes('mode=sample') ? 'sample' : 'live'
    if (path.includes('/latest')) return json(mode === latest.status.data_mode ? latest : makeLatest(mode))
    if (path.includes('/api/briefings?')) return json({ data_mode: mode, briefings: [] })
    if (path.startsWith('/api/stories/')) return json({ data_mode: latest.status.data_mode, briefing_id: 3, story: latest.briefing!.stories[0], articles: [{
      title: 'Original fictional report', url: 'https://alpha.example.com/story', publisher_name: 'Sample newsroom alpha',
      published_at: '2026-11-08T10:00:00Z', collected_at: '2026-11-09T12:00:00Z',
    }] })
    throw new Error('Unexpected request')
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  vi.spyOn(Date, 'now').mockReturnValue(now)
})

describe('Court Side dashboard', () => {
  it('loads saved news without automatically refreshing a source', async () => {
    serve()
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    expect(screen.getByText('12 hours')).toBeTruthy()
    expect(screen.getByText('Provisional')).toBeTruthy()
    expect(fetchMock.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
    expect(screen.getByLabelText('Rank 1').textContent).toBe('01')
  })

  it('does not silently switch to sample data when the API is down', async () => {
    fetchMock.mockRejectedValue(new Error('Offline'))
    render(<App />)
    await screen.findByRole('alert')
    expect(screen.queryByText('Sample data')).toBeNull()
    expect(screen.getByRole('button', { name: 'News' }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText('The briefing is unavailable.')).toBeTruthy()
  })

  it('labels explicitly selected sample data and keeps requests in that mode', async () => {
    serve()
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByRole('button', { name: 'Sample' }))
    await screen.findByRole('heading', { name: 'Sample: Lakers win a fictional game' })
    expect(screen.getByText('Sample data')).toBeTruthy()
    expect(screen.getByText(/These stories and publishers are fictional/)).toBeTruthy()
    expect(window.location.search).toBe('?mode=sample')
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('mode=sample'))).toBe(true)
  })

  it('runs the sample investigation only after its separate button is clicked', async () => {
    serve()
    const defaults = fetchMock.getMockImplementation()!
    const target = makeLatest('sample').briefing!.stories[0]
    target.title = 'Sample: Lakers give Marcus Reed ankle injury update'
    fetchMock.mockImplementation((input, options) => {
      if (String(input) === '/api/sample/investigate') return Promise.resolve(json({
        data_mode: 'sample', model: 'qwen-test', passed: true, checks: { scores_unchanged: true },
        optional_checks: {}, note: 'Fictional evidence only.', target,
      }))
      return defaults(input, options)
    })
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    expect(screen.queryByRole('button', { name: 'Run sample investigation' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Sample' }))
    await screen.findByRole('heading', { name: 'Sample: Lakers win a fictional game' })
    expect(fetchMock.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
    await userEvent.click(screen.getByRole('button', { name: 'Run sample investigation' }))
    await screen.findByRole('heading', { name: 'Sample: Lakers give Marcus Reed ankle injury update' })
    expect(screen.getByText(/qwen-test · checks passed/)).toBeTruthy()
    expect(screen.getByText(/Fictional evidence only/)).toBeTruthy()
    const aiCalls = fetchMock.mock.calls.filter(([path]) => String(path) === '/api/sample/investigate')
    expect(aiCalls).toHaveLength(1)
    expect(JSON.parse(String(aiCalls[0][1]?.body))).toEqual({})
  })

  it('shows candidates without inventing a rank when evidence is limited', async () => {
    const latest = makeLatest()
    latest.briefing!.stories = []
    const candidate = latest.briefing!.candidates[0]
    candidate.rank = null
    candidate.eligible = false
    candidate.exclusion_reasons = ['Needs 2 independent publisher groups, found 1']
    serve(latest)
    render(<App />)
    await screen.findByText('Not enough independent coverage yet.')
    expect(screen.getByRole('heading', { name: 'On our radar' })).toBeTruthy()
    expect(screen.getByLabelText('Unranked candidate')).toBeTruthy()
    expect(screen.queryByLabelText('Rank 1')).toBeNull()
    expect(screen.getByText('0 / 10')).toBeTruthy()
  })

  it('shows the actual score breakdown and source investigation activity', async () => {
    serve()
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByText('Why this ranks'))
    expect(screen.getByText('12.50 / 50')).toBeTruthy()
    expect(screen.getByText('20.00 / 30')).toBeTruthy()
    expect(screen.getByText(/No reviewed development yet/)).toBeTruthy()
    await userEvent.click(screen.getByText('Evidence check'))
    expect(screen.getByText('Looked for related reporting')).toBeTruthy()
    expect(screen.getByText('Rules-based source check · complete')).toBeTruthy()
    expect(screen.getByText(/A substantive update has not been established/)).toBeTruthy()
  })

  it('retrieves source details for the exact briefing only when expanded', async () => {
    serve()
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('/api/stories/'))).toBe(false)
    const sourceDetails = screen.getByText('Sources').closest('details')!
    await userEvent.click(within(sourceDetails).getByText('Sources'))
    await screen.findByText('Original fictional report')
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('briefing_id=3'))).toBe(true)
    expect(screen.getByText(/Collected Nov 9/)).toBeTruthy()
  })

  it('keeps the old briefing after a failed manual refresh', async () => {
    serve()
    const reads = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((input, options) => options?.method === 'POST' ? Promise.resolve(json({ detail: 'The news source failed.' }, 502)) : reads(input, options))
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByRole('button', { name: 'Refresh briefing' }))
    await screen.findByText('The news source failed.')
    expect(screen.getByRole('heading', { name: 'Saved NBA game report' })).toBeTruthy()
    expect(screen.queryByText('Sample data')).toBeNull()
  })

  it('does not pretend a selected date window has already been collected', async () => {
    const latest = makeLatest()
    serve(latest)
    const reads = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((input, options) => {
      if (options?.method !== 'POST') return reads(input, options)
      const updated = makeLatest()
      updated.briefing!.window_start = '2026-11-02T12:00:00Z'
      return Promise.resolve(json(updated))
    })
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByRole('button', { name: '7 days' }))
    expect(screen.getByText(/still viewing the saved 3-day briefing/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Refresh briefing' }))
    await waitFor(() => expect(screen.queryByText(/still viewing the saved 3-day briefing/)).toBeNull())
    const post = fetchMock.mock.calls.find(([, options]) => options?.method === 'POST')!
    expect(JSON.parse(String(post[1]!.body))).toEqual({ mode: 'live', days: 7, max_requests: 3 })
  })

  it('honors refresh cooldowns returned by the server', async () => {
    serve()
    const reads = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((input, options) => options?.method === 'POST' ? Promise.resolve(json({ detail: 'Please wait.' }, 429, { 'Retry-After': '60' })) : reads(input, options))
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByRole('button', { name: 'Refresh briefing' }))
    await screen.findByText('Please wait.')
    await waitFor(() => expect((screen.getByRole('button', { name: 'Refresh briefing' }) as HTMLButtonElement).disabled).toBe(true))
    expect(screen.getByText('Refresh available in 1 min')).toBeTruthy()
  })

  it('shows stale data and a failed previous source attempt honestly', async () => {
    const latest = makeLatest()
    latest.status.stale = true
    latest.status.last_attempt = { id: 4, status: 'failed', requests_used: 1, started_at: '2026-11-09T10:00:00Z', completed_at: '2026-11-09T10:01:00Z', lease_until: '2026-11-09T10:02:00Z', error: 'Source unavailable' }
    serve(latest)
    render(<App />)
    await screen.findByText('This briefing is getting old.')
    expect(screen.getByText('The last refresh did not finish.')).toBeTruthy()
    expect(screen.getByText('Showing the last saved briefing.')).toBeTruthy()
  })

  it('discards a slow response from the previously selected mode', async () => {
    let resolveLive!: (response: Response) => void
    const delayed = new Promise<Response>(resolve => { resolveLive = resolve })
    serve()
    const defaults = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((input, options) => String(input).includes('/latest?mode=live') ? delayed : defaults(input, options))
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: 'Sample' }))
    await screen.findByRole('heading', { name: 'Sample: Lakers win a fictional game' })
    resolveLive(json(makeLatest('live')))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Saved NBA game report' })).toBeNull())
    expect(screen.getByText('Sample data')).toBeTruthy()
  })

  it('renders external article text as text and blocks unsafe source links', async () => {
    const latest = makeLatest()
    const title = '<img src=x onerror=alert(1)> NBA report'
    latest.briefing!.stories[0].title = title
    latest.briefing!.stories[0].summary!.citations[0].url = 'javascript:alert(1)'
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: title })
    expect(document.querySelector('img')).toBeNull()
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull()
  })

  it('keeps a history error separate from the working briefing', async () => {
    serve()
    const defaults = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((input, options) => String(input).includes('/api/briefings?') ? Promise.reject(new Error('History offline')) : defaults(input, options))
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByText('Recent briefings'))
    expect(screen.getByText('Briefing history could not be loaded.')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('offers an explicit first refresh for an empty database', async () => {
    const empty: LatestResponse = { briefing: null, status: { state: 'empty', data_mode: 'live', stale: false, last_attempt: null, last_successful_refresh: null, empty_reason: 'no_saved_briefing' } }
    serve(empty)
    render(<App />)
    await screen.findByText('The first briefing starts here.')
    expect(screen.getByRole('button', { name: 'Collect the first briefing' })).toBeTruthy()
    expect(fetchMock.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
  })

  it('shows loading while a refresh is pending and prevents another click', async () => {
    let finish!: (response: Response) => void
    serve()
    const defaults = fetchMock.getMockImplementation()!
    fetchMock.mockImplementation((input, options) => options?.method === 'POST' ? new Promise<Response>(resolve => { finish = resolve }) : defaults(input, options))
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByRole('button', { name: 'Refresh briefing' }))
    expect((screen.getByRole('button', { name: 'Refreshing…' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Refreshing…' }))
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST').length).toBe(1)
    finish(json(makeLatest()))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Refreshing…' })).toBeNull())
  })
  it('shows individual source failures without hiding the saved news', async () => {
    const latest = makeLatest()
    latest.briefing!.sources = [
      { id: 'gnews', name: 'GNews', kind: 'api', status: 'failed', article_count: 0, collected_at: null, error: 'GNews unavailable' },
      { id: 'yahoo-nba', name: 'Yahoo Sports', kind: 'rss', status: 'ok', article_count: 12, collected_at: '2026-11-09T12:00:00Z', note: 'Recent feed snapshot only.' },
    ]
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByText('Collection sources'))
    expect(screen.getByText('GNews unavailable')).toBeTruthy()
    expect(screen.getByText('ok · 12 articles')).toBeTruthy()
    expect(screen.getByText('Recent feed snapshot only.')).toBeTruthy()
    expect(screen.getByText('Varies by source')).toBeTruthy()
  })

  it('labels feed-only headlines and keeps attribution links visible', async () => {
    const latest = makeLatest()
    const story = latest.briefing!.stories[0]
    story.summary = null
    story.investigation = { status: 'source_restricted', activity: [], decision_summary: 'Source processing is restricted.' }
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    expect(screen.getByText('Feed headline only. This story is excluded from generated summaries and investigation.')).toBeTruthy()
    expect(screen.getAllByRole('link', { name: /Sample newsroom alpha/ }).length).toBeGreaterThan(0)
    expect(screen.queryByText('From the reporting')).toBeNull()
  })

})
