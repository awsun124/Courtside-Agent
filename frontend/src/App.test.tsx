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
  localStorage.clear()
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
    expect(screen.getByRole('link', { name: 'How we rank' }).getAttribute('href')).toBe('/ranking')
    expect(screen.getByRole('link', { name: 'Read the methodology' }).getAttribute('href')).toBe('/ranking')
  })

  it('shows related reading separately from scored sources', async () => {
    const latest = makeLatest()
    latest.briefing!.stories[0].related_reading = [{
      title: 'Analysis of the same matchup', url: 'https://context.example.com/analysis',
      publisher: 'Context Sports', published_at: '2026-11-08T10:00:00Z', reason: 'Context about the same matchup',
    }]
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    fireEvent.click(screen.getByText('Related reading'))
    expect(screen.getByRole('link', { name: 'Analysis of the same matchup' }).getAttribute('href')).toBe('https://context.example.com/analysis')
    expect(screen.getByText(/These links do not count toward the score/)).toBeTruthy()
    expect(fetchMock.mock.calls.some(([path]) => String(path).startsWith('/api/stories/'))).toBe(false)
  })

  it('filters saved stories by team and type without collecting news', async () => {
    const latest = makeLatest()
    latest.briefing!.stories[0].teams = ['boston celtics']
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    fireEvent.click(screen.getByText('Teams · All teams'))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Boston Celtics' }))
    expect(screen.getByRole('heading', { name: 'Saved NBA game report' })).toBeTruthy()
    await userEvent.selectOptions(screen.getByLabelText('Story type'), 'injury')
    expect(screen.queryByRole('heading', { name: 'Saved NBA game report' })).toBeNull()
    expect(screen.getByText(/No saved stories match/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getByRole('heading', { name: 'Saved NBA game report' })).toBeTruthy()
    expect(fetchMock.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
  })

  it('includes either selected team and keeps original ranks', async () => {
    const latest = makeLatest()
    const first = latest.briefing!.stories[0]
    first.teams = ['boston celtics']
    const second = { ...first, id: 'second', title: 'Saved Lakers report', rank: 4, teams: ['los angeles lakers'] }
    latest.briefing!.stories.push(second)
    latest.briefing!.candidates.push(second)
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: first.title })
    fireEvent.click(screen.getByText('Teams · All teams'))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Boston Celtics' }))
    expect(screen.queryByRole('heading', { name: second.title })).toBeNull()
    await userEvent.click(screen.getByRole('checkbox', { name: 'Los Angeles Lakers' }))
    expect(screen.getByRole('heading', { name: first.title })).toBeTruthy()
    expect(screen.getByRole('heading', { name: second.title })).toBeTruthy()
    expect(screen.getByLabelText('Rank 4').textContent).toBe('04')
    expect(screen.getByText(/Showing 2 of 2 ranked stories/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Remove Boston Celtics filter' }))
    expect(screen.queryByRole('heading', { name: first.title })).toBeNull()
    expect(fetchMock.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
  })

  it('restores filters after remounting even for teams with no saved coverage', async () => {
    serve()
    const view = render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    fireEvent.click(screen.getByText('Teams · All teams'))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Atlanta Hawks' }))
    await userEvent.selectOptions(screen.getByLabelText('Story type'), 'injury')
    view.unmount()
    render(<App />)
    await screen.findByText(/No saved stories match/)
    expect(screen.getByRole('button', { name: 'Remove Atlanta Hawks filter' })).toBeTruthy()
    expect((screen.getByLabelText('Story type') as HTMLSelectElement).value).toBe('injury')
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(JSON.parse(localStorage.getItem('courtside.story-filters')!)).toEqual({ teams: [], storyType: 'all', query: '' })
    expect(screen.getByRole('heading', { name: 'Saved NBA game report' })).toBeTruthy()
  })

  it('ignores damaged saved filters and works when browser storage is blocked', async () => {
    localStorage.setItem('courtside.story-filters', '{broken')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage blocked') })
    serve()
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.selectOptions(screen.getByLabelText('Story type'), 'injury')
    expect(screen.getByText(/No saved stories match/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getByRole('heading', { name: 'Saved NBA game report' })).toBeTruthy()
  })

  it('searches title and summary words together with existing filters locally', async () => {
    const latest = makeLatest()
    const story = latest.briefing!.stories[0]
    story.title = 'Curry returns for Warriors'
    story.teams = ['golden state warriors']
    story.summary!.text = 'A report about an ankle injury.'
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: story.title })
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search saved stories' }), '  CURRY   ankle ')
    expect(screen.getByRole('heading', { name: story.title })).toBeTruthy()
    expect(screen.getByLabelText('Rank 1').textContent).toBe('01')
    await userEvent.selectOptions(screen.getByLabelText('Story type'), 'injury')
    expect(screen.queryByRole('heading', { name: story.title })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Remove story type filter' }))
    expect(screen.getByRole('heading', { name: story.title })).toBeTruthy()
    await userEvent.clear(screen.getByRole('searchbox'))
    await userEvent.type(screen.getByRole('searchbox'), 'missingword')
    expect(screen.getByText(/No saved stories match/)).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(screen.getByRole('heading', { name: story.title })).toBeTruthy()
    expect(fetchMock.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
  })

  it('searches unranked titles without summaries and restores the search', async () => {
    const latest = makeLatest()
    const candidate = { ...latest.briefing!.stories[0], id: 'candidate', title: 'Dončić ankle update', rank: null, summary: null }
    latest.briefing!.candidates.push(candidate)
    serve(latest)
    const view = render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.type(screen.getByRole('searchbox'), 'doncic ankle')
    expect(screen.getByRole('heading', { name: candidate.title })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Saved NBA game report' })).toBeNull()
    view.unmount()
    render(<App />)
    await screen.findByRole('heading', { name: candidate.title })
    expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('doncic ankle')
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('')
  })

  it('shows team coverage and explains matches that are only unranked candidates', async () => {
    const latest = makeLatest()
    const candidate = { ...latest.briefing!.stories[0], id: 'warriors', title: 'Warriors game report', rank: null, teams: ['golden state warriors'] }
    latest.briefing!.candidates.push(candidate)
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    fireEvent.click(screen.getByText('Teams · All teams'))
    const warriors = screen.getByRole('checkbox', { name: 'Golden State Warriors' })
    expect(within(warriors.closest('label')!).getByText('1 saved')).toBeTruthy()
    const bulls = screen.getByRole('checkbox', { name: 'Chicago Bulls' })
    expect(within(bulls.closest('label')!).getByText('No saved stories')).toBeTruthy()
    await userEvent.click(warriors)
    expect(screen.getByRole('heading', { name: candidate.title })).toBeTruthy()
    expect(screen.getByText(/1 matching story below is unranked/)).toBeTruthy()
  })

  it('clears unread-only along with other filters', async () => {
    serve()
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByRole('button', { name: 'Mark as read' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Unread only' }))
    expect(screen.queryByRole('heading', { name: 'Saved NBA game report' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect((screen.getByRole('checkbox', { name: 'Unread only' }) as HTMLInputElement).checked).toBe(false)
    expect(screen.getByRole('heading', { name: 'Saved NBA game report' })).toBeTruthy()
  })

  it('finds roster moves by their category while retaining team filters', async () => {
    const latest = makeLatest()
    const story = latest.briefing!.stories[0]
    story.title = 'Lakers waive Lovering, sign Cooper'
    story.event = 'contract'
    story.teams = ['los angeles lakers']
    story.summary = null
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: story.title })
    await userEvent.type(screen.getByRole('searchbox'), 'roster moves')
    expect(screen.getByRole('heading', { name: story.title })).toBeTruthy()
    fireEvent.click(screen.getByText('Teams · All teams'))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Los Angeles Lakers' }))
    expect(screen.getByRole('heading', { name: story.title })).toBeTruthy()
    await userEvent.selectOptions(screen.getByLabelText('Story type'), 'injury')
    expect(screen.queryByRole('heading', { name: story.title })).toBeNull()
    expect(fetchMock.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
  })

  it('shows the daily schedule and reloads saved news without a collection request', async () => {
    const latest = makeLatest()
    latest.status.schedule = { enabled: true, timezone: 'America/New_York', hour: 6, next_update_at: new Date(now + 3600000).toISOString() }
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    expect(screen.getByText('Updated daily at 6 AM Eastern.')).toBeTruthy()
    expect(screen.getByText(/Next scheduled update in 1h 0m/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Refresh briefing' })).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Reload briefing' }))
    expect(fetchMock.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
  })

  it('hides game results and source text until explicitly revealed', async () => {
    const latest = makeLatest()
    latest.briefing!.stories[0].title = 'Celtics beat Lakers 120-100'
    latest.briefing!.stories[0].teams = ['boston celtics', 'los angeles lakers']
    serve(latest)
    const view = render(<App />)
    await screen.findByRole('heading', { name: 'Celtics beat Lakers 120-100' })
    await userEvent.click(screen.getByRole('checkbox', { name: 'Hide game spoilers' }))
    expect(screen.queryByText('Celtics beat Lakers 120-100')).toBeNull()
    expect(screen.queryByText(/A fictional NBA game ended/)).toBeNull()
    expect(screen.queryByText('Sources')).toBeNull()
    view.unmount()
    render(<App />)
    await screen.findByRole('heading', { name: /Result hidden/ })
    await userEvent.click(screen.getByRole('button', { name: 'Reveal this game' }))
    expect(screen.getByRole('heading', { name: 'Celtics beat Lakers 120-100' })).toBeTruthy()
    expect(screen.queryByText('Unread')).toBeNull()
    expect(fetchMock.mock.calls.every(([, options]) => options?.method !== 'POST')).toBe(true)
  })

  it('keeps bookmarks from older editions and removes them on request', async () => {
    serve()
    const view = render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByRole('button', { name: /^Bookmark$/ }))
    view.unmount()
    const next = makeLatest()
    next.briefing!.briefing_id = 4
    next.briefing!.stories = []
    next.briefing!.candidates = []
    serve(next)
    render(<App />)
    await screen.findByText('Not enough independent coverage yet.')
    await userEvent.click(screen.getByRole('button', { name: 'Show bookmarks' }))
    expect(screen.getByRole('heading', { name: 'Saved NBA game report' })).toBeTruthy()
    expect(JSON.parse(localStorage.getItem('courtside.reading')!).bookmarks[0].briefing.briefing_id).toBe(3)
    await userEvent.click(screen.getByRole('button', { name: 'Remove bookmark' }))
    expect(screen.getByText(/No bookmarks match/)).toBeTruthy()
  })

  it('remembers read stories without marking newly collected stories as read', async () => {
    serve()
    const view = render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByRole('button', { name: 'Mark as read' }))
    view.unmount()
    const next = makeLatest()
    const fresh = { ...next.briefing!.stories[0], id: 'new-story', title: 'New injury report', event: 'injury', rank: 2 }
    next.briefing!.stories.push(fresh)
    next.briefing!.candidates.push(fresh)
    serve(next)
    render(<App />)
    await screen.findByRole('heading', { name: fresh.title })
    await userEvent.click(screen.getByRole('checkbox', { name: 'Unread only' }))
    expect(screen.queryByRole('heading', { name: 'Saved NBA game report' })).toBeNull()
    expect(screen.getByRole('heading', { name: fresh.title })).toBeTruthy()
  })

  it('copies a link containing the exact edition and opens it despite saved filters', async () => {
    const copy = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText: copy } })
    serve()
    const view = render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    fireEvent.click(screen.getByRole('button', { name: 'Copy story link' }))
    await screen.findByText('Link copied')
    expect(copy.mock.calls[0][0]).toContain('story=story-one&briefing_id=3&mode=live')
    view.unmount()
    localStorage.setItem('courtside.story-filters', JSON.stringify({ teams: ['atlanta hawks'], storyType: 'injury', query: 'unrelated' }))
    window.history.replaceState(null, '', '/?story=story-one&briefing_id=3&mode=live')
    fetchMock.mockImplementation(async input => {
      if (String(input) === '/api/briefings/3?mode=live') return json(makeLatest().briefing)
      throw new Error('Unexpected request')
    })
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
  })

  it('offers a copyable link if the clipboard is unavailable', async () => {
    vi.stubGlobal('navigator', { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('Denied')) } })
    serve()
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    fireEvent.click(screen.getByRole('button', { name: 'Copy story link' }))
    await screen.findByText('Copy the link below')
    expect((screen.getByLabelText('Story link') as HTMLInputElement).value).toContain('briefing_id=3')
  })

  it('shows a missing shared edition honestly without loading different news', async () => {
    window.history.replaceState(null, '', '/?story=missing&briefing_id=999&mode=live')
    fetchMock.mockResolvedValue(json({ detail: 'Saved briefing not found' }, 404))
    render(<App />)
    await screen.findByRole('alert')
    expect(screen.getByText('Saved briefing not found')).toBeTruthy()
    expect(fetchMock.mock.calls).toHaveLength(1)
  })

  it('ignores the sample briefing URL and stays in live mode', async () => {
    const latest = makeLatest('sample')
    window.history.replaceState(null, '', '/?mode=sample')
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    expect(screen.queryByRole('button', { name: 'Sample' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Refresh briefing' })).toBeTruthy()
    expect(fetchMock.mock.calls.some(([path]) => String(path).includes('mode=sample'))).toBe(false)
  })

  it('does not silently switch to sample data when the API is down', async () => {
    fetchMock.mockRejectedValue(new Error('Offline'))
    render(<App />)
    await screen.findByRole('alert')
    expect(screen.queryByText('Sample data')).toBeNull()
    expect(screen.getByRole('button', { name: 'Refresh briefing' }).getAttribute('aria-pressed')).toBeNull()
    expect(screen.getByText('The briefing is unavailable.')).toBeTruthy()
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

  it('distinguishes reporting groups from publisher labels and source links', async () => {
    const latest = makeLatest()
    const story = latest.briefing!.stories[0]
    story.publishers.push('Third Sports')
    story.evidence_urls.push('https://third.example.com/copy')
    story.reporting_groups[0].publishers.push('Third Sports')
    story.reporting_groups[0].evidence_urls.push('https://third.example.com/copy')
    story.breakdown.coverage.raw_publisher_labels = 3
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    await userEvent.click(screen.getByText('Why this ranks'))
    expect(screen.getByText('2 estimated reporting groups from 3 source links across 3 publisher labels.')).toBeTruthy()
    expect(screen.getByText(/Limited monitored coverage: 2 of the 8/)).toBeTruthy()
    await userEvent.click(screen.getByText('Sources'))
    const groups = screen.getByLabelText('Reporting groups')
    expect(within(groups).getByText('Reporting group 1')).toBeTruthy()
    expect(within(groups).getByRole('link', { name: 'third.example.com' }).getAttribute('href')).toBe('https://third.example.com/copy')
    expect(within(groups).getByText(/These links count together/)).toBeTruthy()
    expect(within(groups).queryByText('Reporting group 3')).toBeNull()
  })

  it('shows dated injury reports without presenting an earlier absence as the latest status', async () => {
    const latest = makeLatest()
    const story = latest.briefing!.stories[0]
    story.event = 'injury'
    story.title = 'Marcus Reed cleared to play after ankle injury'
    story.injury_updates = [
      { title: 'Marcus Reed ruled out with ankle injury', availability: 'unavailable',
        published_at: '2026-11-08T10:00:00Z', publisher: 'First Sports', url: 'https://first.example.com/injury' },
      { title: story.title, availability: 'available',
        published_at: '2026-11-09T10:00:00Z', publisher: 'Second Sports', url: 'https://second.example.com/return' },
    ]
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: story.title })
    await userEvent.click(screen.getByText('Injury updates', { selector: 'summary' }))
    const updates = screen.getByText('Injury updates', { selector: 'summary' }).closest('details')!
    expect(within(updates).getByText('Reported unavailable')).toBeTruthy()
    expect(within(updates).getByText('Reported available')).toBeTruthy()
    expect(within(updates).getByRole('link', { name: story.title }).getAttribute('href')).toBe('https://second.example.com/return')
    expect(within(updates).getByText(/Availability inferred from saved headlines and excerpts/)).toBeTruthy()
  })

  it('attributes fallback links using their reporting groups instead of array positions', async () => {
    const latest = makeLatest()
    const story = latest.briefing!.stories[0]
    story.summary = null
    story.evidence_urls.reverse()
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    expect(screen.getAllByRole('link', { name: 'Sample newsroom alpha' }).every(link => link.getAttribute('href') === 'https://alpha.example.com/story')).toBe(true)
    expect(screen.getAllByRole('link', { name: 'Sample newsroom bravo' }).every(link => link.getAttribute('href') === 'https://bravo.example.com/story')).toBe(true)
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

  it('keeps the thirty minute cooldown after reloading saved status', async () => {
    const latest = makeLatest()
    latest.status.last_attempt = { id: 4, status: 'partial', requests_used: 5, started_at: new Date(now - 5 * 60000).toISOString(), completed_at: new Date(now - 4 * 60000).toISOString(), lease_until: new Date(now - 3 * 60000).toISOString(), error: null }
    serve(latest)
    render(<App />)
    await screen.findByRole('heading', { name: 'Saved NBA game report' })
    expect(screen.getByText('Refresh available in 25 min')).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Refresh briefing' }) as HTMLButtonElement).disabled).toBe(true)
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
    expect(screen.getByText('Headlines and source links only. A generated summary is unavailable for these sources.')).toBeTruthy()
    expect(screen.getAllByRole('link', { name: /Sample newsroom alpha/ }).length).toBeGreaterThan(0)
    expect(screen.queryByText('From the reporting')).toBeNull()
  })

})
