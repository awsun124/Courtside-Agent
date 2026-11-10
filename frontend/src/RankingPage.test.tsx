import { render, screen, within } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import App from './App'

it('opens a standalone ranking page without loading or refreshing news', () => {
  window.history.replaceState(null, '', '/ranking')
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  render(<App />)
  expect(screen.getByRole('heading', { level: 1, name: /How we rank/ })).toBeTruthy()
  const nav = within(screen.getByRole('navigation', { name: 'Main navigation' }))
  expect(nav.getByRole('link', { name: 'How we rank' }).getAttribute('aria-current')).toBe('page')
  expect(nav.getByRole('link', { name: 'NBA briefing' }).getAttribute('href')).toBe('/#briefing')
  expect(screen.getByRole('link', { name: 'Back to the NBA briefing' }).getAttribute('href')).toBe('/')
  expect(fetch).not.toHaveBeenCalled()
})

it('explains evidence requirements, scoring, sparse coverage, and source limits', () => {
  window.history.replaceState(null, '', '/ranking/')
  render(<App />)
  expect(screen.getByRole('heading', { name: 'Coverage' })).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Momentum' })).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Freshness' })).toBeTruthy()
  expect(screen.getByText(/at least two estimated independent reporting groups/)).toBeTruthy()
  expect(screen.getByText(/GNews free access excludes the latest 12 hours/)).toBeTruthy()
  expect(screen.getByText(/If both rates are zero, growth is zero/)).toBeTruthy()
  expect(screen.getByRole('cell', { name: '35 / 100' })).toBeTruthy()
  expect(screen.getByText(/These are the default settings/)).toBeTruthy()
})

it('preserves sample mode when navigating back to the briefing', () => {
  window.history.replaceState(null, '', '/ranking?mode=sample')
  render(<App />)
  expect(screen.getByRole('link', { name: 'Court Side home' }).getAttribute('href')).toBe('/?mode=sample')
  expect(screen.getByRole('link', { name: 'Back to the NBA briefing' }).getAttribute('href')).toBe('/?mode=sample')
})
