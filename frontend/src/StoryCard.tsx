import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { requestJson } from './api'
import { formatDate, plural, safeLink } from './format'
import { Icon } from './Icons'
import type { Briefing, DataMode, Story, StoryDetail } from './types'

const eventLabels: Record<string, string> = { game: 'Game report', injury: 'Injury update', trade: 'Trade news', contract: 'Roster move', league: 'League news', off_court: 'Off-court news', milestone: 'Player milestone' }
const activityLabels: Record<string, string> = {
  search_articles: 'Looked for related reporting', retrieve_material: 'Read a saved source excerpt',
  inspect_related_stories: 'Checked related story groups', compare_previous_briefings: 'Compared earlier briefings',
  finish: 'Checked summary references', rejected_action: 'An action could not be used',
}

function SourceLink({ url, children }: { url: string; children: ReactNode }) {
  const href = safeLink(url)
  return href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}<Icon name="external" /></a> : <span>{children}</span>
}

export default function StoryCard({ story, briefing, mode }: { story: Story; briefing: Briefing; mode: DataMode }) {
  const [detail, setDetail] = useState<StoryDetail | null>(null)
  const [sourceState, setSourceState] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  const reportDates = story.reporting_groups.map(group => group.first_published_at).sort((first, second) => Date.parse(first) - Date.parse(second))
  const reportedAt = reportDates.at(-1)
  const summary = story.summary
  const changed = story.what_changed?.status === 'compared' ? story.what_changed : null
  const newLinks = changed?.new_source_urls?.length ?? 0
  const removedLinks = changed?.removed_source_urls?.length ?? 0

  function sourceLabel(url: string) {
    const group = story.reporting_groups.find(group => group.evidence_urls.includes(url))
    if (group?.publishers.length === 1) return group.publishers[0]
    const href = safeLink(url)
    return href ? new URL(href).hostname : 'Source link'
  }

  async function loadSources() {
    if (sourceState === 'loading' || sourceState === 'ready') return
    const request = new AbortController()
    controller.current = request
    setSourceState('loading')
    try {
      const saved = await requestJson<StoryDetail>(`/api/stories/${encodeURIComponent(story.id)}?mode=${mode}&briefing_id=${briefing.briefing_id}`, { signal: request.signal })
      if (request.signal.aborted) return
      if (saved.data_mode !== mode || saved.briefing_id !== briefing.briefing_id) throw new Error('Wrong source snapshot')
      setDetail(saved)
      setSourceState('ready')
    } catch {
      if (!request.signal.aborted) setSourceState('error')
    }
  }

  const components = [
    { label: 'Coverage', ...story.breakdown.coverage, maximum: briefing.settings.coverage_weight * 100,
      explanation: `${plural(story.breakdown.coverage.independent_publishers, 'reporting group')} after likely copies are combined. The coverage target is ${story.breakdown.coverage.target}.` },
    { label: 'Momentum', ...story.breakdown.momentum, maximum: briefing.settings.momentum_weight * 100,
      explanation: `${plural(story.breakdown.momentum.recent_reports, 'new reporting group')} in the latest ${Math.round(story.breakdown.momentum.recent_hours)} hours, compared with ${story.breakdown.momentum.earlier_reports} in the earlier period.` },
    { label: 'Freshness', ...story.breakdown.freshness, maximum: briefing.settings.freshness_weight * 100,
      explanation: story.breakdown.freshness.development_at ? `Reviewed development: ${formatDate(story.breakdown.freshness.development_at, true)}.` : 'No reviewed development yet. A new copy of an old report does not earn freshness points.' },
  ]

  return <article className={`story-card ${story.rank === 1 ? 'lead-story' : ''}`}>
    <div className="story-number" aria-label={story.rank ? `Rank ${story.rank}` : 'Unranked candidate'}>
      {story.rank ? String(story.rank).padStart(2, '0') : <span className="unranked-mark">—</span>}
    </div>
    <div className="story-content">
      <div className="story-kicker"><span>{eventLabels[story.event] ?? 'NBA news'}</span>
        {story.has_rumor && <span className="tag rumor">Unconfirmed</span>}
        {!story.rank && <span className="candidate-label">Needs more coverage</span>}
      </div>
      <h3>{story.title}</h3>
      {summary ? <>
        <p className="source-caption">From the reporting</p>
        <p className="story-summary">{summary.text}</p>
        <div className="citation-links">{summary.citations.map(citation => <SourceLink key={citation.evidence_id} url={citation.url}>{citation.publisher}</SourceLink>)}</div>
      </> : <>
        <p className="missing-summary">{story.investigation?.status === 'source_restricted' ? 'Feed headline only. This story is excluded from generated summaries and investigation.' : 'No evidence check has been saved for this briefing yet. Original reporting is linked below.'}</p>
        <div className="citation-links">{story.evidence_urls.map(url => <SourceLink key={url} url={url}>{sourceLabel(url)}</SourceLink>)}</div>
      </>}
      <div className="story-meta">
        <span>{story.publishers.join(' · ')}</span>
        <span title={reportedAt}>{reportedAt ? `Reported ${formatDate(reportedAt, true)}` : 'Report time unavailable'}</span>
      </div>
      <div className="story-measures">
        <span>{plural(story.breakdown.coverage.independent_publishers, 'reporting group')}</span>
        <span>{plural(story.publishers.length, 'publisher')}</span>
        <span className="score-total">{story.score.toFixed(1)}<span> / 100</span></span>
      </div>

      {changed && <div className="changed-note"><span className="eyebrow">Since the previous briefing</span>
        <p>{newLinks || removedLinks ? `${plural(newLinks, 'new source link')}${removedLinks ? `, ${removedLinks} removed` : ''}.` : 'The source links are unchanged.'}
          {changed.score_change ? ` Score ${changed.score_change > 0 ? '+' : ''}${changed.score_change.toFixed(1)}.` : ''}
          {' '}A substantive update has not been established.</p>
      </div>}

      <div className="story-details">
        <details className="score-details">
          <summary>{story.rank ? 'Why this ranks' : 'Why this score'}<Icon name="chevron" /></summary>
          <div className="details-body">
            <p>{plural(story.breakdown.coverage.independent_publishers, 'estimated reporting group')} from {plural(story.evidence_urls.length, 'source link')} across {plural(story.publishers.length, 'publisher label')}.</p>
            {story.breakdown.coverage.independent_publishers < story.breakdown.coverage.target && <p className="detail-note">Limited monitored coverage: {story.breakdown.coverage.independent_publishers} of the {story.breakdown.coverage.target} reporting groups needed for full coverage points.</p>}
            {components.map(component => <div className="score-component" key={component.label}>
              <div className="score-label"><strong>{component.label}</strong><span>{component.points.toFixed(2)} / {component.maximum.toFixed(0)}</span></div>
              <div className="score-track" role="meter" aria-label={`${component.label} score`} aria-valuenow={component.points} aria-valuemin={0} aria-valuemax={component.maximum || 1}><span style={{ width: `${component.maximum > 0 ? Math.max(0, Math.min(100, component.score * 100)) : 0}%` }} /></div>
              <p>{component.explanation}</p>
            </div>)}
            {story.exclusion_reasons.length > 0 && <p className="detail-note">{story.exclusion_reasons.join('. ')}.</p>}
            <p className="detail-note">These scores describe coverage in this collection. They do not measure all NBA news.</p>
          </div>
        </details>

        <details onToggle={event => { if (event.currentTarget.open) void loadSources() }}>
          <summary>Sources <span className="detail-count">{story.evidence_urls.length}</span><Icon name="chevron" /></summary>
          <div className="details-body sources-list">
            {sourceState === 'loading' && <p role="status">Loading source details…</p>}
            {sourceState === 'error' && <div><p>Could not load the saved source details.</p><button className="text-button" onClick={() => void loadSources()}>Try source details again</button></div>}
            <div aria-label="Reporting groups">{story.reporting_groups.map((group, index) => <div className="source-entry" key={index}>
              <p><strong>Reporting group {index + 1}</strong> · {group.publishers.join(' · ')}</p>
              {group.evidence_urls.map(url => {
                const article = detail?.articles.find(article => article.url === url)
                return <div key={url}>
                  <SourceLink url={url}>{article?.title ?? sourceLabel(url)}</SourceLink>
                  {article && <>
                    <p>{article.publisher_name} · Published {formatDate(article.published_at, true)}</p>
                    {article.attribution_note && <p>{article.attribution_note}</p>}
                    <p className="collection-time">Collected {formatDate(article.collected_at, true)}</p>
                  </>}
                </div>
              })}
              {group.evidence_urls.length > 1 && <p className="detail-note">These links count together because they share a publisher or appear to carry the same report.</p>}
            </div>)}</div>
            <p className="detail-note">Some publishers may carry the same report. Their links stay available, but likely copies count once.</p>
            <p className="detail-note">Reporting groups are estimates. Original authorship and publisher ownership have not been verified.</p>
          </div>
        </details>

        <details>
          <summary>Evidence check<Icon name="chevron" /></summary>
          <div className="details-body">
            {story.investigation ? <>
              <p>{story.investigation.decision_summary}</p>
              <span className="review-status">{story.investigation.provider === 'rules' ? 'Rules-based source check' : 'Source investigation'} · {story.investigation.status.replaceAll('_', ' ')}</span>
              {story.investigation.activity.length > 0 && <ol className="activity-list">{story.investigation.activity.map((item, index) => <li key={index}>
                <span>{activityLabels[item.tool] ?? item.decision}</span>
                {typeof item.arguments?.query === 'string' && <small>Search: {item.arguments.query}</small>}
                {item.status === 'rejected' && <small>This action was not accepted.</small>}
              </li>)}</ol>}
              {story.investigation.uncertainty?.map(note => <p className="detail-note" key={note}>{note}</p>)}
            </> : <p>No investigation activity is saved for this briefing.</p>}
          </div>
        </details>
      </div>
    </div>
  </article>
}
