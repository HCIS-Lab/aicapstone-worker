// Display helpers shared by the views.

export const STATUS_BADGE = {
  UPLOADING: 'badge-queued',
  QUEUED: 'badge-queued',
  RUNNING: 'badge-running',
  FINISHED: 'badge-finished',
  FAILED: 'badge-failed',
}

/** Small status pill used in tables (same palette as the leaderboard). */
export function statusPillClass(status) {
  return ({
    FINISHED: 'bg-emerald-500/20 text-emerald-400',
    FAILED: 'bg-red-500/20 text-red-400',
    RUNNING: 'bg-blue-500/20 text-blue-300',
  })[status] || 'bg-brand-500/20 text-brand-400'
}

export function formatDuration(sec) {
  if (sec == null) return '—'
  if (sec >= 3600) {
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    return `${h}h ${m}m`
  }
  if (sec >= 60) {
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    return `${m}m ${s}s`
  }
  return `${Math.round(sec)}s`
}

export function formatRate(rate) {
  return rate == null ? '—' : `${(rate * 100).toFixed(1)}%`
}

export function formatBytes(n) {
  if (n == null) return '—'
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`
  return `${(n / 1024 ** 2).toFixed(1)} MB`
}

/** Live progress of a RUNNING run: episode X/N, or the current phase. */
export function runProgress(run) {
  if (!run || run.status !== 'RUNNING') return null
  const ep = run.episode || 0
  const et = run.episode_total || 0
  const pct = et > 0 ? Math.min(Math.max((ep / et) * 100, 3), 99) : 3
  const label = et > 0 ? `episode ${ep}/${et}` : (run.phase || 'starting…')
  return { pct, label }
}

/** Display name for a task id, e.g. cup_stacking → Cup Stacking. */
export function taskLabel(name) {
  if (!name) return 'N/A'
  return name.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
