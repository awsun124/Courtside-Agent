import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StatsPage from './StatsPage'

const source = { collected_at: '2026-11-11T12:00:00Z', source_url: 'https://stats.nba.com/stats/leagueleaders', error: null }
function snapshot() {
  return { season: '2026-27', source: 'NBA.com', checked_at: source.collected_at, teams: { ...source, rows: [], error: 'NBA source unavailable. No data collected.' }, players: { ...source, rows: [
    { id: 1, name: 'Test Scorer', team: 'BOS', games: 10, pts: 30, reb: 5, ast: 3, stl: 1, blk: 0.5 },
    { id: 2, name: 'Test Rebounder', team: 'LAL', games: 8, pts: 20, reb: 12, ast: 4, stl: 2, blk: 1 },
    { id: 3, name: 'One Game', team: 'BOS', games: 1, pts: 50, reb: 20, ast: 12, stl: 4, blk: 2 },
  ] } }
}
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(snapshot()), { status: 200 })))
})
describe('cached stats page', () => {
  it('shows all five leaderboards together and supports optional filters without new requests', async () => {
    render(<StatsPage />)
    const points = await screen.findByRole('region', { name: 'Points' })
    for (const name of ['Points', 'Rebounds', 'Assists', 'Steals', 'Blocks']) expect(screen.getByRole('region', { name })).toBeTruthy()
    expect(screen.queryByLabelText('Category')).toBeNull()
    expect(within(points).getAllByRole('listitem')[0].textContent).toContain('Test Scorer')
    const rebounds = screen.getByRole('region', { name: 'Rebounds' })
    expect(within(rebounds).getAllByRole('listitem')[0].textContent).toContain('Test Rebounder')
    expect(screen.queryByText('One Game')).toBeNull()
    fireEvent.click(screen.getByText('Explore player filters'))
    fireEvent.change(screen.getByLabelText('Team'), { target: { value: 'BOS' } })
    expect(screen.queryByText('Test Rebounder')).toBeNull()
    expect(screen.getByText(/Team records are unavailable/)).toBeTruthy()
    expect(vi.mocked(fetch).mock.calls).toHaveLength(1)
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/stats')
  })
  it('shows both conferences together when team data is available', async () => {
    const data = snapshot()
    const teams = [
      { id: 1, name: 'Test East', conference: 'East', wins: 8, losses: 2, win_percentage: .8, points_per_game: 115.2, points_allowed: 110.1, point_difference: 5.1 },
      { id: 2, name: 'Test West', conference: 'West', wins: 7, losses: 3, win_percentage: .7 },
    ]
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ...data, teams: { ...source, rows: teams } }), { status: 200 }))
    render(<StatsPage />)
    const east = await screen.findByRole('region', { name: 'Eastern Conference' })
    expect(within(east).getByText('Test East')).toBeTruthy()
    expect(within(east).getByText('115.2')).toBeTruthy()
    expect(within(east).getByText('+5.1')).toBeTruthy()
    expect(within(east).queryByText('Test West')).toBeNull()
    expect(within(screen.getByRole('region', { name: 'Western Conference' })).getByText('Test West')).toBeTruthy()
    expect(screen.queryByLabelText('Conference')).toBeNull()
  })
  it('handles failed API requests without inventing statistics', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('Offline'))
    render(<StatsPage />)
    await screen.findByRole('alert')
    expect(screen.queryByText('Test Scorer')).toBeNull()
  })
})
