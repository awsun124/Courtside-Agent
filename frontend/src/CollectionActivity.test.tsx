import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import CollectionActivity from './CollectionActivity'
import { makeLatest } from './test/fixtures'

it('shows the query, request count, and incremental coverage for an injury search', async () => {
  const briefing = makeLatest().briefing!
  briefing.collection_activity = [{ source_id: 'gnews', source_name: 'GNews', purpose: 'corroboration', topic: 'injury',
    query: 'marcus reed ankle injury', status: 'partial', requests: 1, returned_results: 7,
    added_articles: 5, publisher_labels: 4, added_publisher_labels: 2 }]
  render(<CollectionActivity briefing={briefing} />)
  await userEvent.click(screen.getByText('Collection activity'))
  expect(screen.getByText('GNews · Injury search')).toBeTruthy()
  expect(screen.getByText('marcus reed ankle injury')).toBeTruthy()
  expect(screen.getByText('7 results returned · 5 new article URLs added')).toBeTruthy()
  expect(screen.getByText('4 publisher labels in these results · 2 new to this collection')).toBeTruthy()
  expect(screen.getByText('Succeeded with partial coverage · 1 request')).toBeTruthy()
})

it('keeps a failed search distinct from a successful search returning zero results', async () => {
  const briefing = makeLatest().briefing!
  const counts = { requests: 1, returned_results: 0, added_articles: 0, publisher_labels: 0, added_publisher_labels: 0 }
  briefing.collection_activity = [
    { ...counts, source_id: 'gnews', source_name: 'GNews', purpose: 'discovery', query: 'NBA', status: 'ok' },
    { ...counts, source_id: 'gnews', source_name: 'GNews', purpose: 'corroboration', topic: 'game',
      query: 'lakers pistons', status: 'failed', note: 'Rate or quota limit reached. No retry was made.' },
  ]
  render(<CollectionActivity briefing={briefing} />)
  await userEvent.click(screen.getByText('Collection activity'))
  expect(screen.getByText('Succeeded · 1 request')).toBeTruthy()
  expect(screen.getByText('Failed · 1 request')).toBeTruthy()
  expect(screen.getByText(/Rate or quota limit reached/)).toBeTruthy()
})

it('explains skipped searches and does not invent details for older briefings', async () => {
  const briefing = makeLatest().briefing!
  const { rerender } = render(<CollectionActivity briefing={briefing} />)
  await userEvent.click(screen.getByText('Collection activity'))
  expect(screen.getByText(/No search activity was recorded/)).toBeTruthy()
  briefing.collection_activity = [{ source_id: 'gnews', source_name: 'GNews', purpose: 'corroboration', query: null,
    status: 'skipped', requests: 0, returned_results: 0, added_articles: 0, publisher_labels: 0, added_publisher_labels: 0,
    note: 'No eligible injury or game candidate was available.' }]
  rerender(<CollectionActivity briefing={briefing} />)
  expect(screen.getByText('Skipped · 0 requests')).toBeTruthy()
  expect(screen.getByText(/No eligible injury or game/)).toBeTruthy()
  expect(screen.queryByText(/0 results returned/)).toBeNull()
})

it('labels sample activity as making no external requests', async () => {
  render(<CollectionActivity briefing={makeLatest('sample').briefing!} />)
  await userEvent.click(screen.getByText('Collection activity'))
  expect(screen.getByText('Sample mode makes no external news requests.')).toBeTruthy()
  expect(within(screen.getByText('Collection activity').closest('details')!).queryByText(/Search:/)).toBeNull()
})
