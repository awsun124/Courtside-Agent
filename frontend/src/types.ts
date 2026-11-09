export type DataMode = 'live' | 'sample'

export interface Citation {
  evidence_id: string
  publisher: string
  url: string
  quote: string
  published_at: string
}

export interface Summary {
  kind: 'source_excerpts'
  text: string
  citations: Citation[]
  note: string
}

export interface Investigation {
  provider?: string
  status: string
  decision_summary: string
  activity: { step?: number; tool: string; status: string; decision: string; arguments?: Record<string, unknown> }[]
  uncertainty?: string[]
  corroboration?: { retrieved_reporting_groups: number; status: string }
}

export interface Story {
  id: string
  title: string
  event: string
  rank: number | null
  score: number
  eligible: boolean
  exclusion_reasons: string[]
  publishers: string[]
  evidence_urls: string[]
  reporting_groups: { first_published_at: string; publishers: string[]; evidence_urls: string[] }[]
  has_rumor: boolean
  needs_review: boolean
  summary?: Summary | null
  investigation?: Investigation
  what_changed?: {
    status: string
    previous_briefing_id?: number
    new_source_urls?: string[]
    removed_source_urls?: string[]
    score_change?: number
    note: string
    meaningful_update: string
  } | null
  breakdown: {
    coverage: { score: number; points: number; independent_publishers: number; raw_publisher_labels: number; target: number }
    momentum: { score: number; points: number; status: string; recent_reports: number; earlier_reports: number; recent_hours: number; earlier_hours: number }
    freshness: { score: number; points: number; status: string; development_at: string | null; age_hours: number | null; evidence_urls: string[] }
  }
}

export interface CollectionSource {
  id: string
  name: string
  kind: string
  status: string
  article_count: number
  collected_at: string | null
  delay_hours?: number
  note?: string
  error?: string
  rejected_records?: number
}

export interface Briefing {
  briefing_id: number
  title: string
  data_mode: DataMode
  source: string
  as_of: string
  window_start: string
  window_end: string
  experimental: boolean
  warnings: string[]
  sources?: CollectionSource[]
  source_errors?: string[]
  settings: { coverage_weight: number; momentum_weight: number; freshness_weight: number; minimum_publishers: number }
  stories: Story[]
  candidates: Story[]
  investigation?: { provider?: string; status: string; llm_calls: number; steps_used?: number }
}

export interface RefreshAttempt {
  id: number
  status: string
  started_at: string
  completed_at: string | null
  lease_until: string
  requests_used: number
  error: string | null
}

export interface LatestResponse {
  briefing: Briefing | null
  status: {
    state: 'empty' | 'ready' | 'stale'
    data_mode: DataMode
    stale: boolean
    last_successful_refresh: string | null
    last_attempt: RefreshAttempt | null
    empty_reason: string | null
  }
}

export interface HistoryItem {
  briefing_id: number
  as_of: string
  experimental: boolean
  story_count: number
  candidate_count: number
}

export interface HistoryResponse {
  data_mode: DataMode
  briefings: HistoryItem[]
}

export interface SourceArticle {
  title: string
  url: string
  publisher_name: string
  published_at: string
  collected_at: string
  description?: string | null
  content_excerpt?: string | null
  attribution_note?: string
}

export interface StoryDetail {
  story: Story
  articles: SourceArticle[]
  briefing_id: number
  data_mode: DataMode
  experimental: boolean
}
