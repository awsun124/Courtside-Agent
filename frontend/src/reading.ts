import { useEffect, useState } from 'react'
import type { Briefing, DataMode, Story } from './types'

export interface SavedStory { story: Story; briefing: Briefing; mode: DataMode }
interface Reading { hideSpoilers: boolean; read: string[]; bookmarks: SavedStory[] }
export const storyKey = (story: Story, mode: DataMode) => `${mode}:${story.id}`

function loadReading(): Reading {
  try {
    const saved = JSON.parse(localStorage.getItem('courtside.reading') ?? 'null')
    return {
      hideSpoilers: saved?.hideSpoilers === true,
      read: Array.isArray(saved?.read) ? saved.read.filter((key: unknown) => typeof key === 'string').slice(-2000) : [],
      bookmarks: Array.isArray(saved?.bookmarks) ? saved.bookmarks.filter((entry: SavedStory) => entry && ['live', 'sample'].includes(entry.mode) && typeof entry.story?.id === 'string' && typeof entry.story?.title === 'string' && Array.isArray(entry.story?.reporting_groups) && entry.story?.breakdown?.coverage && entry.briefing?.settings && Number.isInteger(entry.briefing?.briefing_id)).slice(-50) : [],
    }
  } catch { return { hideSpoilers: false, read: [], bookmarks: [] } }
}

export function useReading() {
  const [reading, setReading] = useState(loadReading)
  const [storageError, setStorageError] = useState(false)
  useEffect(() => {
    try { localStorage.setItem('courtside.reading', JSON.stringify(reading)); setStorageError(false) }
    catch { setStorageError(true) }
  }, [reading])
  function markRead(story: Story, mode: DataMode) {
    const key = storyKey(story, mode)
    setReading(previous => ({ ...previous, read: [...new Set([...previous.read, key])].slice(-2000) }))
  }
  function bookmark(story: Story, briefing: Briefing, mode: DataMode) {
    const key = storyKey(story, mode)
    setReading(previous => ({ ...previous, bookmarks: previous.bookmarks.some(entry => storyKey(entry.story, entry.mode) === key)
      ? previous.bookmarks.filter(entry => storyKey(entry.story, entry.mode) !== key)
      : [...previous.bookmarks, { story, mode, briefing: { ...briefing, stories: [], candidates: [] } }].slice(-50) }))
  }
  return { reading, storageError, markRead, bookmark,
    setSpoilers: (hideSpoilers: boolean) => setReading(previous => ({ ...previous, hideSpoilers })) }
}
export type ReadingActions = ReturnType<typeof useReading>

export function sharedStoryUrl(story: Story, briefing: Briefing, mode: DataMode) {
  const url = new URL('/', window.location.origin)
  url.searchParams.set('story', story.id)
  url.searchParams.set('briefing_id', String(briefing.briefing_id))
  url.searchParams.set('mode', mode)
  return url.href
}
