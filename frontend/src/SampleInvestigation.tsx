import { useState } from 'react'
import { ApiError, requestJson } from './api'
import { formatDate } from './format'
import type { SampleInvestigationResult } from './types'

export default function SampleInvestigation({ active }: { active: boolean }) {
  const [result, setResult] = useState<SampleInvestigationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryUntil, setRetryUntil] = useState(0)
  const [now, setNow] = useState(Date.now())

  async function investigate() {
    if (loading || retryUntil > Date.now()) return
    setLoading(true)
    setError(null)
    try {
      const next = await requestJson<SampleInvestigationResult>('/api/sample/investigate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
      })
      if (next.data_mode !== 'sample') throw new ApiError('The API returned an unexpected data mode.')
      setResult(next)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The sample investigation could not finish.')
      if (reason instanceof ApiError && reason.retryAfter > 0) {
        const until = Date.now() + reason.retryAfter * 1000
        setRetryUntil(until)
        setNow(Date.now())
        window.setTimeout(() => setNow(Date.now()), reason.retryAfter * 1000)
      }
    } finally {
      setLoading(false)
    }
  }

  if (!active) return null
  const wait = Math.max(0, Math.ceil((retryUntil - now) / 1000))
  const story = result?.target
  const investigation = story?.investigation
  const summary = story?.summary

  return <section className="sample-agent-panel" aria-labelledby="sample-agent-title">
    <div className="sample-agent-copy"><p className="eyebrow">OPTIONAL AI DEMO</p><h2 id="sample-agent-title">Let the investigator check a story.</h2>
      <p>Uses fictional injury reports and a separate trade rumor. The score stays rules-based. Up to five model requests.</p>
      <button className="secondary-button" onClick={() => void investigate()} disabled={loading || wait > 0}>
        {loading ? 'Investigating…' : wait ? `Try again in ${wait}s` : result ? 'Run it again' : 'Run sample investigation'}
      </button>
      {error && <p className="sample-agent-error" role="alert">{error}</p>}
    </div>
    {story && <div className="sample-agent-result" aria-live="polite">
      <div className="sample-agent-result-heading"><span className="tag">Fictional story</span><span>{result.model} · {result.passed ? 'checks passed' : 'incomplete'}</span></div>
      <h3>{story.title}</h3>
      {summary ? <><p className="story-summary">{summary.text}</p><ul className="sample-agent-citations">{summary.citations.map(citation => <li key={citation.evidence_id}><a href={citation.url} target="_blank" rel="noopener noreferrer">{citation.publisher}: “{citation.quote}”</a><time dateTime={citation.published_at}>{formatDate(citation.published_at, true)}</time></li>)}</ul></> : <p className="missing-summary">The investigator did not find enough supported evidence for a summary.</p>}
      <details className="sample-agent-activity"><summary>Investigation activity <span>{investigation?.activity.length ?? 0} steps</span></summary>
        <ol className="activity-list">{investigation?.activity.map((step, index) => <li key={`${step.step}-${step.tool}-${index}`}>{step.tool.replaceAll('_', ' ')}<small>{step.decision}</small></li>)}</ol>
        {investigation?.uncertainty?.map(note => <p className="detail-note" key={note}>{note}</p>)}
      </details>
      <p className="sample-agent-note">{result.note}</p>
    </div>}
  </section>
}
