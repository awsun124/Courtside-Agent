import { useEffect, useState } from 'react'
import { requestJson } from './api'
import { formatDate } from './format'
import { useReading } from './reading'
import SiteHeader from './SiteHeader'
import StoryCard from './StoryCard'
import type { Briefing, DataMode } from './types'

export default function SharedStory() {
  const [briefing, setBriefing] = useState<Briefing | null>(null)
  const [error, setError] = useState('')
  const reader = useReading()
  const params = new URLSearchParams(window.location.search)
  const mode: DataMode = params.get('mode') === 'sample' ? 'sample' : 'live'
  const storyId = params.get('story') ?? ''
  const briefingId = params.get('briefing_id') ?? ''
  useEffect(() => {
    const controller = new AbortController()
    if (!/^[1-9]\d*$/.test(briefingId) || !storyId || storyId.length > 200) {
      setError('This story link is invalid.')
      return
    }
    void requestJson<Briefing>(`/api/briefings/${briefingId}?mode=${mode}`, { signal: controller.signal }).then(saved => {
      if (controller.signal.aborted) return
      if (saved.data_mode !== mode || saved.briefing_id !== Number(briefingId) || !saved.candidates.some(story => story.id === storyId)) throw new Error('This story is unavailable in the saved briefing.')
      setBriefing(saved)
    }).catch(error => { if (!controller.signal.aborted) setError(error.message) })
    return () => controller.abort()
  }, [mode, storyId, briefingId])
  const story = briefing?.candidates.find(story => story.id === storyId)
  return <>
    <SiteHeader page="briefing" now={Date.now()} />
    <main className="page-shell shared-story">
      <a href={mode === 'sample' ? '/?mode=sample' : '/'}>Back to the latest briefing</a>
      <h1>Saved story</h1>
      {mode === 'sample' && <p className="notice">Sample data. This story is fictional.</p>}
      <label className="reading-toggle"><input type="checkbox" checked={reader.reading.hideSpoilers} onChange={event => reader.setSpoilers(event.target.checked)} />Hide game spoilers</label>
      {reader.storageError && <p role="status">Browser storage is unavailable. Reading choices will last only for this visit.</p>}
      {error ? <p role="alert">{error}</p> : story && briefing ? <>
        <p>Saved edition · {formatDate(briefing.as_of, true)}. Rank and score reflect that edition.</p>
        <StoryCard story={story} briefing={briefing} mode={mode} reader={reader} />
      </> : <p role="status">Loading saved story…</p>}
    </main>
  </>
}
