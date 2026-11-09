export function formatDate(value: string | null | undefined, withTime = false) {
  if (!value || Number.isNaN(Date.parse(value))) return 'Not available'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short', day: 'numeric', ...(withTime ? { hour: 'numeric', minute: '2-digit' } as const : {}),
  }).format(new Date(value))
}

export function timeAgo(value: string | null | undefined, now = Date.now()) {
  if (!value || Number.isNaN(Date.parse(value))) return 'Not refreshed yet'
  const minutes = Math.max(0, Math.floor((now - Date.parse(value)) / 60000))
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes} min ago`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
  return formatDate(value, true)
}

export function windowDays(start: string, asOf: string) {
  return Math.max(1, Math.min(7, Math.round((Date.parse(asOf) - Date.parse(start)) / 86400000)))
}

export function safeLink(value: string) {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined
  } catch {
    return undefined
  }
}

export function plural(count: number, word: string) {
  return `${count} ${word}${count === 1 ? '' : 's'}`
}
