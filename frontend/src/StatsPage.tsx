import { useEffect, useState } from 'react'
import { requestJson } from './api'
import { formatDate, safeLink } from './format'
import SiteHeader from './SiteHeader'

interface PlayerStats { id: number; name: string; team: string; games: number; pts: number; reb: number; ast: number; stl: number; blk: number }
interface TeamStats { id: number; name: string; conference: string; wins: number; losses: number; win_percentage: number; points_per_game?: number | null; points_allowed?: number | null; point_difference?: number | null }
interface Snapshot<T> { rows: T[]; collected_at: string | null; source_url: string; source_name?: string; error: string | null; stale?: boolean }
interface Stats { season: string; source: string; checked_at: string | null; players: Snapshot<PlayerStats> | null; teams: Snapshot<TeamStats> | null }
const categories = [{ key: 'pts', label: 'Points' }, { key: 'reb', label: 'Rebounds' }, { key: 'ast', label: 'Assists' }, { key: 'stl', label: 'Steals' }, { key: 'blk', label: 'Blocks' }] as const

type Metric = typeof categories[number]['key']
function SourceNote({ source }: { source: { collected_at: string | null; source_url: string; source_name?: string; stale?: boolean } | null | undefined }) {
  return <p className="stats-source">{source?.collected_at ? `Collected ${formatDate(source.collected_at, true)}${source.stale ? ' · Stale data' : ''}` : 'No successful collection yet.'}{source && safeLink(source.source_url) && <> · <a href={safeLink(source.source_url)} target="_blank" rel="noopener noreferrer">{source.source_name ?? 'NBA'} source</a></>}</p>
}

function PlayerLeaders({ players, metric, label }: { players: PlayerStats[]; metric: Metric; label: string }) {
  const sorted = [...players].sort((first, second) => second[metric] - first[metric] || first.name.localeCompare(second.name))
  const rankOf = (player: PlayerStats) => sorted.findIndex(other => other[metric] === player[metric]) + 1
  return <section className="leaderboard-card" aria-labelledby={`leaders-${metric}`}>
    <div className="leaderboard-heading"><h3 id={`leaders-${metric}`}>{label}</h3><span>{metric.toUpperCase()} / game</span></div>
    <ol className="leaderboard-list">{sorted.slice(0, 5).map(player => <li key={player.id}><span className="leaderboard-rank">{rankOf(player)}</span><div><strong>{player.name}</strong><small>{player.team} · {player.games} games</small></div><span className="leaderboard-value">{player[metric].toFixed(1)}</span></li>)}</ol>
    {sorted.length > 5 && <details className="leaderboard-more"><summary>View all {label.toLowerCase()} leaders</summary><div className="stats-table-wrap"><table className="stats-table"><caption>All {sorted.length} matching players by {label.toLowerCase()} per game</caption><thead><tr><th scope="col">Rank</th><th scope="col">Player</th><th scope="col">Team</th><th scope="col">GP</th><th scope="col">{metric.toUpperCase()}</th></tr></thead><tbody>{sorted.map(player => <tr key={player.id}><td>{rankOf(player)}</td><th scope="row">{player.name}</th><td>{player.team}</td><td>{player.games}</td><td>{player[metric].toFixed(1)}</td></tr>)}</tbody></table></div></details>}
  </section>
}

export default function StatsPage() {
  const [data, setData] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [minimumGames, setMinimumGames] = useState(5)
  const [team, setTeam] = useState('all')
  const [reload, setReload] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void requestJson<Stats>('/api/stats', { signal: controller.signal }).then(saved => {
      if (!controller.signal.aborted) setData(saved)
    }).catch(error => { if (!controller.signal.aborted) setError(error.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [reload])
  const players = (data?.players?.rows ?? []).filter(player => player.games >= minimumGames && (team === 'all' || player.team === team))
  const teams = [...(data?.teams?.rows ?? [])].sort((first, second) => second.win_percentage - first.win_percentage || first.name.localeCompare(second.name))
  const playerTeams = [...new Set(data?.players?.rows.map(player => player.team) ?? [])].sort()
  return <>
    <SiteHeader page="stats" />
    <div className="stats-surface"><main className="page-shell stats-page">
      <section className="page-intro"><div><p className="eyebrow intro-kicker">NBA / THE NUMBERS</p><h1>League stats<span>.</span></h1><p className="intro-copy">The league at a glance. Five leaderboards, one view.</p></div><div className="edition-mark"><span className="eyebrow">REGULAR SEASON</span><span className="edition-label">{data?.season ?? 'NBA'}</span><span>Updated with the daily collection.</span></div></section>
      <div className="status-line"><span>Players: NBA.com · Teams: ESPN · Saved data</span><button className="text-button" disabled={loading} onClick={() => setReload(value => value + 1)}>Reload saved stats</button></div>
      {loading && !data && <p role="status">Loading saved statistics…</p>}
      {error && <p className="notice error-notice" role="alert">{error} {data ? 'Showing the previous snapshot.' : ''}</p>}
      {data && <>
        <section className="stats-section" aria-labelledby="players-title">
          <div className="section-heading"><div><p className="eyebrow">01 / INDIVIDUAL</p><h2 id="players-title">Player leaders</h2></div><span className="tag">Per game</span></div>
          <details className="stats-explore"><summary>Explore player filters</summary><div className="stats-controls"><label>Minimum games<select value={minimumGames} onChange={event => setMinimumGames(Number(event.target.value))}>{[1, 5, 10, 20].map(value => <option key={value} value={value}>{value} {value === 1 ? 'game' : 'games'}</option>)}</select></label><label>Team<select value={team} onChange={event => setTeam(event.target.value)}><option value="all">All teams</option>{playerTeams.map(team => <option key={team} value={team}>{team}</option>)}</select></label></div></details>
          <SourceNote source={data.players} />
          {data.players?.error && <p className="notice">{data.players.error}</p>}
          {data.players?.stale && <p className="notice">Player data is more than 26 hours old or has no collection timestamp.</p>}
          <div className="stats-basis"><span>{players.length} players in view · Minimum {minimumGames} games{team !== 'all' ? ` · ${team}` : ''}</span><details><summary>Data notes</summary><p>Leaders among the {data.players?.rows.length ?? 0} returned player rows. The minimum-games filter is our display rule, not the NBA’s official qualification criteria. Equal values share a rank.</p></details></div>
          {players.length ? <div className="leaderboard-grid">{categories.map(category => <PlayerLeaders key={category.key} players={players} metric={category.key} label={category.label} />)}</div> : <div className="empty-ranking"><p>{data.players?.rows.length ? 'No players match these filters. Try fewer minimum games or another team.' : 'No player data is available. No sample statistics have been substituted.'}</p></div>}

        </section>
        <section className="stats-section" aria-labelledby="teams-title"><div className="section-heading"><div><p className="eyebrow">02 / COLLECTIVE</p><h2 id="teams-title">Team records</h2></div></div><SourceNote source={data.teams} />
          {data.teams?.error && data.teams.rows.length > 0 && <p className="notice">{data.teams.error}</p>}
          {data.teams?.stale && data.teams.rows.length > 0 && <p className="notice">Team data is more than 26 hours old.</p>}
          {teams.length ? <><p className="stats-method">Ordered by winning percentage. Ties are alphabetical, not official playoff seeding.</p><div className="conference-grid">{['East', 'West'].map(conference => <section className="conference-card" key={conference} aria-label={`${conference}ern Conference`}><h3>{conference}ern Conference</h3><div className="stats-table-wrap"><table className="stats-table"><caption>{conference}ern Conference records</caption><thead><tr><th scope="col">Team</th><th scope="col">W</th><th scope="col">L</th><th scope="col">Win %</th><th scope="col" title="Points scored per game">PPG</th><th scope="col" title="Points allowed per game">Opp PPG</th><th scope="col" title="Points per game minus opponent points per game">Diff</th></tr></thead><tbody>{teams.filter(team => team.conference === conference).map(team => <tr key={team.id}><th scope="row">{team.name}</th><td>{team.wins}</td><td>{team.losses}</td><td>{(team.win_percentage * 100).toFixed(1)}%</td><td>{team.points_per_game?.toFixed(1) ?? '—'}</td><td>{team.points_allowed?.toFixed(1) ?? '—'}</td><td className={team.point_difference != null && team.point_difference > 0 ? 'positive-stat' : undefined}>{team.point_difference != null ? `${team.point_difference > 0 ? '+' : ''}${team.point_difference.toFixed(1)}` : '—'}</td></tr>)}</tbody></table></div></section>)}</div></> : <div className="empty-ranking"><p>Team records are unavailable from the statistics source. Player statistics remain available above.</p></div>}
        </section>
      </>}
      <footer className="site-footer"><p>Statistics are cached once per daily collection. Browsing and filtering do not call the source APIs.</p><a href="/">Back to the briefing</a></footer>
    </main></div>
  </>
}
