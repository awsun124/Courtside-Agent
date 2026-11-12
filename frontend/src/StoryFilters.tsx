import { useEffect, useRef, useState } from 'react'

const storageKey = 'courtside.story-filters'
const teamNames = ['Atlanta Hawks', 'Boston Celtics', 'Brooklyn Nets', 'Charlotte Hornets', 'Chicago Bulls', 'Cleveland Cavaliers', 'Dallas Mavericks', 'Denver Nuggets', 'Detroit Pistons', 'Golden State Warriors', 'Houston Rockets', 'Indiana Pacers', 'Los Angeles Clippers', 'Los Angeles Lakers', 'Memphis Grizzlies', 'Miami Heat', 'Milwaukee Bucks', 'Minnesota Timberwolves', 'New Orleans Pelicans', 'New York Knicks', 'Oklahoma City Thunder', 'Orlando Magic', 'Philadelphia 76ers', 'Phoenix Suns', 'Portland Trail Blazers', 'Sacramento Kings', 'San Antonio Spurs', 'Toronto Raptors', 'Utah Jazz', 'Washington Wizards']
const storyTypes = [['game', 'Game reports'], ['injury', 'Injury updates'], ['trade', 'Trade news'], ['contract', 'Roster moves'], ['league', 'League news'], ['off_court', 'Off-court news'], ['milestone', 'Player milestones']]
interface Filters { teams: string[]; storyType: string; query: string }

function savedFilters(): Filters {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null')
    return {
      teams: Array.isArray(saved?.teams) ? [...new Set<string>(saved.teams.filter((team: unknown) => typeof team === 'string' && teamNames.some(name => name.toLowerCase() === team)))] : [],
      query: typeof saved?.query === 'string' ? saved.query.slice(0, 200) : '',
      storyType: storyTypes.some(([value]) => value === saved?.storyType) ? saved.storyType : 'all',
    }
  } catch { return { teams: [], storyType: 'all', query: '' } }
}

export function useStoryFilters() {
  const [filters, setFilters] = useState<Filters>(savedFilters)
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(filters)) } catch { /* Filtering still works when browser storage is unavailable. */ }
  }, [filters])
  return { filters, setFilters, clearFilters: () => setFilters({ teams: [], storyType: 'all', query: '' }) }
}

export default function StoryFilters({ filters, onChange, onClear, teamCounts = {}, typeCounts = {}, readingFiltered = false }: { filters: Filters; onChange: (filters: Filters) => void; onClear: () => void; teamCounts?: Record<string, number>; typeCounts?: Record<string, number>; readingFiltered?: boolean }) {
  const teamPicker = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    function closeOutside(event: PointerEvent) {
      if (event.target instanceof Node && !teamPicker.current?.contains(event.target) && teamPicker.current) teamPicker.current.open = false
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape' && teamPicker.current?.open) {
        teamPicker.current.open = false
        teamPicker.current.querySelector('summary')?.focus()
      }
    }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [])
  const active = readingFiltered || filters.teams.length > 0 || filters.storyType !== 'all' || Boolean(filters.query.trim())
  function toggleTeam(team: string) {
    onChange({ ...filters, teams: filters.teams.includes(team) ? filters.teams.filter(value => value !== team) : [...filters.teams, team] })
  }
  return <section className="story-filters" aria-label="Filter saved stories">
    <div className="filter-controls">
      <label className="search-filter">Search saved stories<input type="search" value={filters.query} maxLength={200} placeholder="Player, injury, or keyword" onChange={event => onChange({ ...filters, query: event.target.value })} aria-describedby="search-scope" /></label>
      <details className="team-picker" ref={teamPicker}>
        <summary>Teams · {filters.teams.length ? `${filters.teams.length} selected` : 'All teams'}</summary>
        <fieldset><legend>Choose teams</legend><p>Counts show saved stories, including unranked candidates. Teams with no saved coverage will have no matches.</p>
          <div className="team-options">{teamNames.map(name => <label key={name}><input type="checkbox" aria-label={name} checked={filters.teams.includes(name.toLowerCase())} onChange={() => toggleTeam(name.toLowerCase())} /><span>{name}<small className="team-coverage">{teamCounts[name.toLowerCase()] ? `${teamCounts[name.toLowerCase()]} saved` : 'No saved stories'}</small></span></label>)}</div>
        </fieldset>
      </details>
      <label className="type-filter">Story type<select value={filters.storyType} onChange={event => onChange({ ...filters, storyType: event.target.value })}><option value="all">All story types</option>{storyTypes.map(([value, label]) => <option key={value} value={value}>{label} ({typeCounts[value] ?? 0})</option>)}</select></label>
      {active && <button className="text-button" onClick={onClear}>Clear filters</button>}
    </div>
    {active && <div className="active-filters" aria-label="Active filters">{teamNames.filter(name => filters.teams.includes(name.toLowerCase())).map(name => <button key={name} aria-label={`Remove ${name} filter`} onClick={() => toggleTeam(name.toLowerCase())}>{name}<span aria-hidden="true"> ×</span></button>)}
      {filters.query.trim() && <button aria-label="Clear search" onClick={() => onChange({ ...filters, query: '' })}>Search: {filters.query.trim()}<span aria-hidden="true"> ×</span></button>}
      {filters.storyType !== 'all' && <button aria-label="Remove story type filter" onClick={() => onChange({ ...filters, storyType: 'all' })}>{storyTypes.find(([value]) => value === filters.storyType)?.[1]}<span aria-hidden="true"> ×</span></button>}
    </div>}
    <p id="search-scope">Search matches any entered word in titles, available summaries, team names, or story types. Filters are remembered in this browser. They use saved stories and keep overall ranks and scores.</p>
  </section>
}
