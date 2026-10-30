// Backend stores all timestamps as naive UTC (no tz suffix). Native
// `new Date(s)` interprets a naive ISO string as LOCAL TIME, which is
// 8h off for Taipei users. These helpers normalize the parse — assume
// UTC when no tz marker is present — so display falls back to the
// browser's locale (Asia/Taipei for the lab).

const _TZ_RE = /Z|[+-]\d{2}:?\d{2}$/

/** Parse a backend datetime to a JS Date, treating naive strings as UTC. */
export function parseUTC(ts) {
  if (ts == null || ts === '') return null
  if (ts instanceof Date) return ts
  if (typeof ts === 'number') return new Date(ts)
  const s = String(ts)
  return new Date(_TZ_RE.test(s) ? s : s + 'Z')
}

/** Localized date-time string (browser locale) for a backend timestamp. */
export function formatLocal(ts) {
  const d = parseUTC(ts)
  return d ? d.toLocaleString() : '—'
}

/** Short date — "May 6, 2026" — in the browser locale. */
export function formatLocalDate(ts) {
  const d = parseUTC(ts)
  return d
    ? d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    : '—'
}

/** Compact date+time like "2026-05-06 14:32:01" in the browser locale. */
export function formatLocalCompact(ts) {
  const d = parseUTC(ts)
  if (!d) return ''
  // Use sv-SE for an ISO-like format that's locale-aware in TZ but not separator.
  return d.toLocaleString('sv-SE').replace('T', ' ')
}

/** Convert a Date / backend timestamp to the value an
 *  <input type="datetime-local"> expects (`YYYY-MM-DDTHH:mm`, local time). */
export function toDatetimeLocalInput(ts) {
  const d = parseUTC(ts)
  if (!d) return ''
  const tzOff = d.getTimezoneOffset() * 60000
  return new Date(d.getTime() - tzOff).toISOString().slice(0, 16)
}
