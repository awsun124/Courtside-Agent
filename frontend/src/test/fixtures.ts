import type { DataMode, LatestResponse, Story } from '../types'

export const now = Date.parse('2026-11-09T12:00:00Z')

export function makeStory(mode: DataMode = 'live'): Story {
  return {
    id: 'story-one', title: mode === 'sample' ? 'Sample: Lakers win a fictional game' : 'Saved NBA game report',
    event: 'game', rank: 1, score: 32.5, eligible: true, exclusion_reasons: [],
    publishers: ['Sample newsroom alpha', 'Sample newsroom bravo'],
    evidence_urls: ['https://alpha.example.com/story', 'https://bravo.example.com/story'],
    reporting_groups: [
      { first_published_at: '2026-11-08T10:00:00Z', publishers: ['Sample newsroom alpha'], evidence_urls: ['https://alpha.example.com/story'] },
      { first_published_at: '2026-11-08T12:00:00Z', publishers: ['Sample newsroom bravo'], evidence_urls: ['https://bravo.example.com/story'] },
    ],
    has_rumor: false, needs_review: true,
    summary: { kind: 'source_excerpts', text: 'Sample newsroom alpha reports: A fictional NBA game ended 110-100.', note: 'Attributed API excerpt',
      citations: [{ evidence_id: 'article-one', publisher: 'Sample newsroom alpha', url: 'https://alpha.example.com/story', quote: 'A fictional NBA game ended 110-100.', published_at: '2026-11-08T10:00:00Z' }] },
    investigation: { provider: 'rules', status: 'complete', decision_summary: 'Read two saved excerpts. Scores unchanged.',
      activity: [{ step: 1, tool: 'search_articles', status: 'ok', decision: 'Inspected saved metadata', arguments: { query: 'NBA game' } },
        { step: 2, tool: 'retrieve_material', status: 'ok', decision: 'Retrieved saved excerpt' }],
      uncertainty: ['Only saved API excerpts were inspected. Full articles were not retrieved.'] },
    what_changed: { status: 'compared', previous_briefing_id: 1, new_source_urls: ['https://bravo.example.com/story'], removed_source_urls: [], score_change: 5,
      note: 'New links do not prove a substantive development', meaningful_update: 'not established' },
    breakdown: {
      coverage: { score: .25, points: 12.5, independent_publishers: 2, raw_publisher_labels: 2, target: 8 },
      momentum: { score: 2 / 3, points: 20, status: 'reduced because coverage is sparse', recent_reports: 2, earlier_reports: 0, recent_hours: 24, earlier_hours: 36 },
      freshness: { score: 0, points: 0, status: 'no reviewed development', development_at: null, age_hours: null, evidence_urls: [] },
    },
  }
}

export function makeLatest(mode: DataMode = 'live'): LatestResponse {
  const story = makeStory(mode)
  return {
    briefing: {
      briefing_id: 3, data_mode: mode, source: mode === 'sample' ? 'Sample' : 'GNews',
      title: mode === 'sample' ? 'Sample briefing (fictional data)' : 'Most-covered stories among our monitored sources',
      as_of: '2026-11-09T12:00:00Z', window_start: '2026-11-06T12:00:00Z', window_end: '2026-11-09T00:00:00Z',
      experimental: true, warnings: ['The article collection is incomplete.', 'The source excludes the latest 12 hours.'],
      settings: { coverage_weight: .5, momentum_weight: .3, freshness_weight: .2, minimum_publishers: 2 },
      stories: [story], candidates: [story], investigation: { provider: 'rules', status: 'complete', llm_calls: 0 },
    },
    status: { state: 'ready', data_mode: mode, stale: false, last_successful_refresh: '2026-11-09T12:00:00Z', last_attempt: null, empty_reason: null },
  }
}
