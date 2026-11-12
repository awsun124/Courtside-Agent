import { describe, expect, it } from 'vitest'
import { matchesSearch } from './search'
import { makeStory } from './test/fixtures'

describe('saved story search', () => {
  it('matches any word instead of requiring every word', () => {
    const story = { ...makeStory(), title: 'Curry returns', summary: null }
    expect(matchesSearch(story, 'ankle Curry')).toBe(true)
    expect(matchesSearch(story, 'unrelated')).toBe(false)
  })
  it('searches category labels and plural variants without a summary', () => {
    const story = { ...makeStory(), event: 'contract', title: 'Lakers sign Cooper', summary: null }
    expect(matchesSearch(story, 'roster moves')).toBe(true)
    expect(matchesSearch(story, 'move')).toBe(true)
    expect(matchesSearch(story, 'injuries')).toBe(false)
    expect(matchesSearch({ ...story, event: 'injury' }, 'injuries')).toBe(true)
  })
  it('includes team names and ignores accents, punctuation, and case', () => {
    const story = { ...makeStory(), title: 'Dončić returns', teams: ['los angeles lakers'] }
    expect(matchesSearch(story, 'DONCIC!')).toBe(true)
    expect(matchesSearch(story, 'Los Angeles')).toBe(true)
    expect(matchesSearch(story, '   ')).toBe(true)
  })
})
