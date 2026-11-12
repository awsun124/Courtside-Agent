import type { Story } from './types'

const storyLabels: Record<string, string> = {
  game: 'game report', injury: 'injury update', trade: 'trade news', contract: 'roster move signing waiver',
  league: 'league news', off_court: 'off court news', milestone: 'player milestone',
}

function searchWords(text: string) {
  return (text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [])
    .map(word => word.length > 4 && word.endsWith('ies') ? `${word.slice(0, -3)}y` : word.length > 3 && word.endsWith('s') && !word.endsWith('ss') && word !== 'news' ? word.slice(0, -1) : word)
}

export function matchesSearch(story: Story, query: string) {
  const queryWords = searchWords(query)
  if (!queryWords.length) return true
  const words = searchWords([story.title, story.summary?.text ?? '', ...(story.teams ?? []), storyLabels[story.event] ?? story.event].join(' '))
  return queryWords.some(queryWord => words.some(word => word.includes(queryWord)))
}
