import type { Story } from './types'
import { formatDate, plural, timeAgo, windowDays } from './format'
import { Icon } from './Icons'
import StoryCard from './StoryCard'
import SampleInvestigation from './SampleInvestigation'
import { useBriefing } from './useBriefing'
import SiteHeader from './SiteHeader'
import RankingPage from './RankingPage'
import CollectionActivity from './CollectionActivity'
import StoryFilters, { useStoryFilters } from './StoryFilters'

export default function App() {
  return window.location.pathname.replace(/\/$/, '') === '/ranking' ? <RankingPage /> : <Dashboard />
}

function Dashboard() {
  const state = useBriefing()
  const { data, mode, loading, refreshing, days } = state
  const briefing = data?.briefing
  const schedule = data?.status.schedule
  const automatic = mode === 'live' && Boolean(schedule?.enabled)
  const { filters, setFilters, clearFilters } = useStoryFilters()
  const filtered = filters.teams.length > 0 || filters.storyType !== 'all' || Boolean(filters.query.trim())
  const normalizeSearch = (text: string) => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
  const searchWords = normalizeSearch(filters.query).trim().split(/\s+/).filter(Boolean)
  const matchesFilters = (story: Story) => (!filters.teams.length || filters.teams.some(team => story.teams?.includes(team))) && (filters.storyType === 'all' || story.event === filters.storyType) && searchWords.every(word => normalizeSearch(`${story.title} ${story.summary?.text ?? ''}`).includes(word))
  const stories = briefing?.stories.filter(matchesFilters) ?? []
  const nextUpdateMinutes = schedule ? Math.max(0, Math.ceil((Date.parse(schedule.next_update_at) - state.now) / 60000)) : 0

  const candidates = briefing?.candidates.filter(story => !story.rank && matchesFilters(story)) ?? []
  const actualDays = briefing ? windowDays(briefing.window_start, briefing.as_of) : null
  const pendingWindow = actualDays !== null && actualDays !== days && !automatic
  const isStale = data?.status.stale || Boolean(!automatic && data?.status.last_successful_refresh && state.now - Date.parse(data.status.last_successful_refresh) > 6 * 3600000)
  const failedAttempt = data?.status.last_attempt?.status === 'failed' || data?.status.last_attempt?.status === 'interrupted'
  const publishers = new Set(briefing?.candidates.flatMap(story => story.publishers) ?? [])
  const weights = briefing?.settings ?? { coverage_weight: 0.5, momentum_weight: 0.3, freshness_weight: 0.2 }
  const refreshLabel = refreshing ? 'Refreshing…' : mode === 'sample' && !briefing ? 'Create sample briefing' : 'Refresh briefing'

  return <div id="top">
    <a className="skip-link" href="#briefing">Skip to briefing</a>
    <SiteHeader page="briefing" now={state.now} />

    <main className="page-shell">
      <section className="page-intro" aria-labelledby="page-title">
        <div><p className="eyebrow intro-kicker"><span className="small-rule" /> NBA NEWS / THE BRIEFING</p>
          <h1 id="page-title">The NBA briefing<span>.</span></h1>
          <p className="intro-copy">The most-covered stories across the sources we monitor.<br className="desktop-break" /> Distinct events, original links, and a clear look at the coverage.</p>
        </div>
        <div className="edition-mark"><span className="eyebrow">{mode === 'sample' ? 'TRY THE APP' : 'FOLLOW THE REPORTING'}</span><span className="edition-label">{mode === 'sample' ? 'Sample edition' : 'NBA / News'}</span><span>{automatic ? 'Updated daily at 6 AM Eastern.' : 'Updated when you refresh.'}</span></div>
      </section>

      <section className="toolbar" aria-label="Briefing controls">
        {automatic ? <div className="window-control"><span className="control-label">Coverage window</span><span>Past {actualDays ?? 7} days · Daily edition</span></div> : <div className="window-control"><span className="control-label">Coverage window</span><div className="segmented" aria-label="Coverage window">{[1, 3, 7].map(value => <button key={value} aria-pressed={days === value} disabled={refreshing || loading} onClick={() => state.setDays(value)}>{value} {value === 1 ? 'day' : 'days'}</button>)}</div></div>}
        <div className="toolbar-actions"><div className="mode-control" aria-label="Data mode"><button aria-pressed={mode === 'live'} disabled={refreshing} onClick={() => state.changeMode('live')}>News</button><button aria-pressed={mode === 'sample'} disabled={refreshing} onClick={() => state.changeMode('sample')}>Sample</button></div>
          {automatic ? <button className="refresh-button" disabled={loading} onClick={state.reload}><Icon name="refresh" />Reload briefing</button> : <button className="refresh-button" disabled={refreshing || loading || state.retrySeconds > 0} onClick={() => void state.refresh()}><Icon name="refresh" className={refreshing ? 'spinning' : ''} />{refreshLabel}</button>}
        </div>
      </section>

      <div className="status-line"><span><Icon name="clock" />{data?.status.last_successful_refresh ? <>Last refreshed <time dateTime={data.status.last_successful_refresh} title={formatDate(data.status.last_successful_refresh, true)}>{timeAgo(data.status.last_successful_refresh, state.now)}</time></> : 'No saved refresh yet'}</span>
        <span>{automatic && schedule ? `Next scheduled update in ${Math.floor(nextUpdateMinutes / 60)}h ${nextUpdateMinutes % 60}m · 6 AM Eastern` : state.retrySeconds > 0 ? `Refresh available in ${state.retrySeconds < 60 ? `${state.retrySeconds}s` : `${Math.ceil(state.retrySeconds / 60)} min`}` : refreshing ? 'Reading coverage and checking evidence…' : 'Manual refresh only'}</span>
      </div>

      {mode === 'sample' && <div className="notice sample-notice"><strong>Sample data</strong><span>These stories and publishers are fictional. No external services are used.</span></div>}
      {state.error && <div className="notice error-notice" role="alert"><div><strong>Something didn’t load.</strong><p>{state.error}</p></div><button className="text-button" disabled={loading || refreshing} onClick={state.reload}>Reload saved briefing</button></div>}
      {!state.error && failedAttempt && <div className="notice error-notice" role="alert"><strong>The last refresh did not finish.</strong><span>{briefing ? 'Showing the last saved briefing.' : 'No new briefing was saved.'}</span></div>}
      {isStale && <div className="notice"><strong>This briefing is getting old.</strong><span>{automatic ? 'The daily collection is overdue. Showing the last saved edition.' : 'It has been more than six hours since the last successful collection.'}</span></div>}
      {pendingWindow && <div className="notice"><strong>Refresh to load the past {days} {days === 1 ? 'day' : 'days'}.</strong><span>You’re still viewing the saved {actualDays}-day briefing.</span></div>}

      {briefing && <StoryFilters filters={filters} onChange={setFilters} onClear={clearFilters} />}

      <SampleInvestigation active={mode === 'sample'} />

      <div className="dashboard-layout">
        <section id="briefing" className="news-column" aria-label="NBA briefing" aria-busy={loading || refreshing}>
          <div className="section-heading"><div><p className="eyebrow">{mode === 'sample' ? 'FICTIONAL COVERAGE' : 'ACROSS THE LEAGUE'}</p><h2>The stories</h2></div><span className="story-count">{briefing ? `${stories.length} / 10` : 'Up to 10'}</span></div>
          {briefing && filtered && <p className="filter-results" role="status">Showing {stories.length} of {briefing.stories.length} ranked stories and {plural(candidates.length, 'unranked candidate')}. Rank numbers refer to the overall briefing.</p>}
          {loading && !briefing ? <div className="loading-state" role="status"><div className="loading-line" /><h3>Loading the saved briefing…</h3><p>Getting the stories and source details.</p></div>
            : !briefing ? <div className="empty-state"><span className="empty-number">00</span><h3>{state.error ? 'The briefing is unavailable.' : 'The first briefing starts here.'}</h3><p>{state.error ? 'Your saved news will appear when the API is available again.' : mode === 'sample' ? 'Create a sample briefing to explore the layout with fictional news.' : automatic ? 'News is collected daily at 6 AM Eastern while the server is running. You can also try the sample edition.' : 'Refresh to collect recent NBA coverage. You can also try the clearly labeled sample edition.'}</p>
                {!state.error && !automatic && <button className="secondary-button" disabled={refreshing || loading || state.retrySeconds > 0} onClick={() => void state.refresh()}>{mode === 'sample' ? 'Create sample briefing' : 'Collect the first briefing'}<Icon name="arrow" /></button>}
              </div>
              : <>
                {filtered && stories.length === 0 && candidates.length === 0 && <div className="empty-ranking"><p>No saved stories match these filters. Try another keyword, team, or story type.</p><button className="text-button" onClick={clearFilters}>Show all stories</button></div>}
                {briefing.experimental && <div className="coverage-note"><span className="tag">Provisional</span><p>{mode === 'sample' ? 'Fictional stories run through the same scoring and evidence checks.' : 'This collection is limited. Scores describe the reporting we have, and remain subject to review.'}</p></div>}
                {briefing.stories.length === 0 && <div className="empty-ranking"><span className="empty-ranking-icon">0</span><div><h3>Not enough independent coverage yet.</h3><p>{candidates.length ? `${plural(candidates.length, 'candidate')} below still ${candidates.length === 1 ? 'needs' : 'need'} more reporting before entering the ranking.` : 'No stories in this collection meet the evidence minimum.'} We show fewer stories when the evidence is limited.</p></div></div>}
                {stories.map(story => <StoryCard key={`${mode}-${briefing.briefing_id}-${story.id}`} story={story} briefing={briefing} mode={mode} />)}
                {candidates.length > 0 && <><div className="radar-heading"><p className="eyebrow">NOT RANKED YET</p><h2>On our radar</h2><p>Stories to follow, with provisional scores and less supporting coverage.</p></div>
                  {candidates.map(story => <StoryCard key={`${mode}-${briefing.briefing_id}-${story.id}`} story={story} briefing={briefing} mode={mode} />)}</>}
              </>}
        </section>

        <aside className="briefing-sidebar" aria-label="Briefing context">
          <section className="edition-panel"><div className="aside-heading"><h2>This edition</h2><span className={`source-dot ${mode === 'sample' ? 'sample-dot' : ''}`} aria-hidden="true" /></div>
            <dl><div><dt>Source</dt><dd>{mode === 'sample' ? 'Fictional sample' : briefing?.source ?? 'Monitored sources'}</dd></div>
              <div><dt>Available coverage</dt><dd>{briefing ? `${formatDate(briefing.window_start)} – ${formatDate(briefing.window_end)}` : 'Not collected yet'}</dd></div>
              <div><dt>Source delay</dt><dd>{briefing?.sources?.length ? 'Varies by source' : briefing?.warnings.some(note => note.includes('12 hours')) ? '12 hours' : briefing ? 'See coverage notes' : '12 hours on free access'}</dd></div>
              <div><dt>Publishers in view</dt><dd>{briefing ? publishers.size : '—'}</dd></div>
              <div><dt>Saved briefing</dt><dd>{briefing ? `#${String(briefing.briefing_id).padStart(3, '0')}` : 'Not available'}</dd></div>
            </dl>
            <p className="aside-footnote">Several publisher links can carry the same report. Likely copies count once.</p>
          </section>

          <section className="method-panel" id="method"><p className="eyebrow">THE METHOD</p><h2>How the score works.</h2><p>Each story gets a score from three simple measures.</p>
            {[['Coverage', weights.coverage_weight, 'How many independent publishers cover the event.'], ['Momentum', weights.momentum_weight, 'How quickly new reporting groups are joining the story.'], ['Freshness', weights.freshness_weight, 'The latest development backed by reviewed evidence.']].map(([label, weight, explanation]) => <div className="method-row" key={String(label)}><span className="method-weight">{Math.round(Number(weight) * 100)}<small>%</small></span><div><h3>{label}</h3><p>{explanation}</p></div></div>)}
            <a className="method-link" href={mode === 'sample' ? '/ranking?mode=sample' : '/ranking'}>Read the methodology<Icon name="arrow" /></a>
          </section>

          {briefing && <CollectionActivity briefing={briefing} />}
          {!!briefing?.sources?.length && <details className="sidebar-details"><summary>Collection sources<Icon name="chevron" /></summary><div className="details-body">
            <ul className="history-list">{briefing.sources.map(source => <li key={source.id}>
              <strong>{source.name}</strong><p>{source.status.replaceAll('_', ' ')} · {plural(source.article_count, 'article')}</p>
              {source.collected_at && <p>Last fetched {formatDate(source.collected_at, true)}</p>}
              {source.delay_hours ? <p>{source.delay_hours}-hour delay</p> : null}
              {(source.error || source.note) && <p>{source.error || source.note}</p>}
              {!!source.rejected_records && <p>{plural(source.rejected_records, 'item')} could not be used.</p>}
            </li>)}</ul>
          </div></details>}
          {briefing && <details className="sidebar-details"><summary>Coverage notes<Icon name="chevron" /></summary><div className="details-body"><ul>{briefing.warnings.map(note => <li key={note}>{note}</li>)}</ul><p>Source dates and claims have not been independently verified.</p></div></details>}
          <details className="sidebar-details"><summary>Recent briefings<Icon name="chevron" /></summary><div className="details-body">
            {state.historyError ? <p>Briefing history could not be loaded.</p> : state.history.length === 0 ? <p>No briefings saved in this mode yet.</p> : <ul className="history-list">{state.history.map(item => <li key={item.briefing_id}><span>#{String(item.briefing_id).padStart(3, '0')}<time dateTime={item.as_of}>{formatDate(item.as_of, true)}</time></span><small>{plural(item.story_count, 'ranked story')} · {plural(item.candidate_count, 'candidate')}</small></li>)}</ul>}
          </div></details>
        </aside>
      </div>
      <footer className="site-footer"><div><strong>COURT SIDE.</strong><p>The most-covered stories among our monitored sources.</p></div><a href="https://github.com/awsun124/Courtside-Agent" target="_blank" rel="noopener noreferrer">About the project<Icon name="external" /></a></footer>
    </main>
  </div>
}
