<template>
  <div class="max-w-5xl mx-auto px-6 py-16">
    <div class="mb-10">
      <router-link to="/runs" class="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-300 transition-colors mb-4">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        Back to Runs
      </router-link>
      <h1 class="text-3xl font-bold text-white mb-2">Run #{{ id }}</h1>
      <p class="text-gray-400">{{ run ? (run.label || run.zip_name || '—') : '...' }} · {{ taskLabel(run?.task_name) }}</p>
    </div>

    <div v-if="loading && !run" class="glass-card p-16 text-center">
      <div class="w-12 h-12 mx-auto rounded-full border-2 border-brand-500 border-t-transparent animate-spin mb-4"></div>
      <p class="text-gray-400">Loading run...</p>
    </div>

    <div v-else-if="error" class="glass-card p-10 text-center">
      <div class="w-16 h-16 mx-auto rounded-2xl bg-red-500/20 flex items-center justify-center mb-4 text-2xl">!</div>
      <h3 class="text-lg font-semibold text-white mb-2">Error</h3>
      <p class="text-gray-400 text-sm">{{ error }}</p>
    </div>

    <template v-else-if="run">
      <!-- Header card -->
      <div class="glass-card p-8 mb-8">
        <div class="flex items-center gap-3 mb-5 flex-wrap">
          <span class="px-3 py-1 rounded-md text-[11px] font-black uppercase tracking-widest bg-brand-500/20 text-brand-400">
            {{ run.task_name }}<template v-if="run.episode_total || run.settings"> · {{ run.episode_total || run.settings.eval_rounds }} episodes</template>
          </span>
          <span :class="['badge', STATUS_BADGE[run.status] || 'badge-queued']">{{ run.status }}</span>
        </div>

        <!-- Live evaluation progress (episode Y/M) -->
        <div v-if="progress" class="mb-6">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[10px] font-black text-brand-400 uppercase tracking-widest flex items-center gap-2">
              <span class="relative flex h-1.5 w-1.5">
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75"></span>
                <span class="relative inline-flex rounded-full h-1.5 w-1.5 bg-brand-500"></span>
              </span>
              Evaluating
            </span>
            <span class="text-xs font-mono font-bold text-brand-300">{{ progress.label }}</span>
          </div>
          <div class="h-2.5 w-full bg-white/5 rounded-full overflow-hidden">
            <div class="h-full bg-gradient-to-r from-brand-500 to-brand-400 transition-all duration-700"
                 :style="{ width: progress.pct + '%' }"></div>
          </div>
          <div class="text-right text-[10px] font-mono text-gray-500 mt-1">{{ Math.round(progress.pct) }}%</div>
        </div>

        <div class="flex items-baseline gap-3 mb-4">
          <span class="text-5xl font-black text-white font-mono tracking-tighter">{{ formatRate(run.success_rate) }}</span>
          <span class="text-sm font-bold text-gray-500">success rate</span>
        </div>
        <div class="h-2 w-full bg-white/5 rounded-full overflow-hidden mb-6">
          <div class="h-full transition-all duration-1000 bg-gradient-to-r from-emerald-500 to-emerald-400"
               :style="{ width: ((run.success_rate || 0) * 100) + '%' }"></div>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Submitted</div>
            <div class="text-white font-bold">{{ formatLocal(run.created_at) }}</div>
          </div>
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Duration</div>
            <div class="text-white font-bold font-mono">{{ formatDuration(run.duration_sec) }}</div>
          </div>
          <div v-if="run.status === 'QUEUED' && run.queue_position">
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Queue</div>
            <div class="text-brand-400 font-bold font-mono">#{{ run.queue_position }}</div>
          </div>
          <div v-else>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Finished</div>
            <div class="text-white font-bold">{{ formatLocal(run.finished_at) }}</div>
          </div>
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Checkpoint</div>
            <div class="text-white font-bold truncate" :title="run.zip_name">{{ formatBytes(run.zip_size) }}</div>
          </div>
        </div>
      </div>

      <!-- Aggregate results -->
      <div v-if="summary" class="glass-card p-6 mb-8">
        <div class="mb-6">
          <h3 class="text-lg font-bold text-white">Evaluation Summary</h3>
          <p class="text-xs text-gray-500 mt-1">Successful / failed episodes, from the success rate over {{ summary.total }} episodes</p>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
          <div class="space-y-3">
            <div class="p-5 rounded-2xl bg-white/5 border border-white/5">
              <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Total Episodes</div>
              <div class="text-4xl text-white font-mono font-black">{{ summary.total }}</div>
            </div>
            <div class="p-5 rounded-2xl bg-emerald-500/10 border border-emerald-500/20">
              <div class="text-[10px] font-black text-emerald-400 uppercase tracking-widest mb-1">✓ Success</div>
              <div class="flex items-baseline gap-3">
                <span class="text-4xl text-emerald-400 font-mono font-black">{{ summary.ok }}</span>
                <span class="text-sm text-emerald-300/80 font-mono">{{ ((summary.ok / summary.total) * 100).toFixed(1) }}%</span>
              </div>
            </div>
            <div class="p-5 rounded-2xl bg-red-500/10 border border-red-500/20">
              <div class="text-[10px] font-black text-red-400 uppercase tracking-widest mb-1">✕ Failed</div>
              <div class="flex items-baseline gap-3">
                <span class="text-4xl text-red-400 font-mono font-black">{{ summary.fail }}</span>
                <span class="text-sm text-red-300/80 font-mono">{{ ((summary.fail / summary.total) * 100).toFixed(1) }}%</span>
              </div>
            </div>
          </div>
          <div class="aspect-square max-w-md mx-auto w-full">
            <Pie :data="pieData" :options="pieOptions" />
          </div>
        </div>
      </div>

      <!-- Replay -->
      <div v-if="run.has_video && run.status !== 'RUNNING'" class="glass-card p-6 mb-8">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-sm font-black text-white uppercase tracking-widest flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-purple-500"></span> Eval Replay
          </h3>
          <a :href="videoUrl" :download="`run_${run.id}_eval.mp4`"
             class="text-[10px] font-black text-brand-400 uppercase tracking-widest hover:text-brand-300">Download</a>
        </div>
        <video :src="videoUrl" controls class="w-full rounded-xl border border-white/5 bg-black max-h-[70vh]">
          Your browser does not support HTML5 video.
        </video>
      </div>

      <!-- Error message -->
      <div v-if="run.error_message" class="glass-card p-6 border-red-500/20 mb-8">
        <h3 class="text-sm font-bold text-red-400 uppercase tracking-wider mb-3">Evaluation Failed</h3>
        <p class="text-sm text-gray-300 font-mono whitespace-pre-wrap break-all">{{ run.error_message }}</p>
        <p class="text-[11px] text-gray-600 mt-3 italic">The full output is in the log below.</p>
      </div>

      <!-- Detected policy + effective settings -->
      <div v-if="run.policy_type || run.settings" class="glass-card p-6 mb-8">
        <h3 class="text-sm font-black text-white uppercase tracking-widest mb-4 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-brand-500"></span> Policy &amp; Settings
        </h3>
        <div v-if="run.policy_type" class="flex items-center gap-3 mb-5">
          <span class="text-[10px] font-black text-gray-500 uppercase tracking-widest">policy_type</span>
          <span class="px-3 py-1 rounded-md bg-brand-500/20 text-brand-400 text-xs font-black uppercase tracking-widest font-mono">
            {{ run.policy_type }}
          </span>
        </div>
        <div v-if="run.settings" class="grid grid-cols-2 md:grid-cols-3 gap-3">
          <div v-for="(v, k) in run.settings" :key="k" class="rounded-xl border border-white/10 bg-surface-900 px-4 py-3">
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1 flex items-center gap-2">
              {{ k }}
              <span v-if="k in (run.overrides || {})" class="text-[9px] text-amber-400">run override</span>
            </div>
            <div class="text-white font-mono text-sm">{{ formatSetting(k, v) }}</div>
          </div>
        </div>
      </div>

      <!-- Log -->
      <div class="glass-card overflow-hidden mb-8">
        <div class="p-4 border-b border-white/5 flex flex-wrap gap-3 justify-between items-center">
          <div class="flex items-center gap-3">
            <div class="flex gap-1.5">
              <span class="w-2.5 h-2.5 bg-red-500 rounded-full"></span>
              <span class="w-2.5 h-2.5 bg-amber-500 rounded-full"></span>
              <span class="w-2.5 h-2.5 bg-emerald-500 rounded-full"></span>
            </div>
            <span class="ml-2 text-xs font-mono font-black tracking-widest uppercase"
                  :class="run.status === 'RUNNING' ? 'text-emerald-400' : 'text-gray-400'">
              {{ run.status === 'RUNNING' ? 'live' : 'log' }} · run #{{ run.id }}
            </span>
          </div>
          <div class="flex flex-wrap gap-2 items-center">
            <input v-model="logSearch" placeholder="search…"
                   class="px-3 py-1.5 rounded-lg bg-surface-900 border border-white/10 text-xs text-white w-40 focus:border-brand-500 outline-none" />
            <span v-if="logSearch" class="text-[10px] text-gray-500">{{ logMatchCount }} matches</span>
            <button @click="copyLog" class="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-[10px] font-black text-gray-300 uppercase tracking-widest hover:text-white">
              {{ copiedHint || 'Copy' }}
            </button>
            <button @click="downloadLog" class="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-[10px] font-black text-gray-300 uppercase tracking-widest hover:text-white">
              Download
            </button>
            <button @click="logWrap = !logWrap" class="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-[10px] font-black text-gray-300 uppercase tracking-widest hover:text-white">
              {{ logWrap ? 'Unwrap' : 'Wrap' }}
            </button>
          </div>
        </div>
        <div ref="logBody" @scroll="onLogScroll"
             class="p-5 h-[28rem] overflow-auto bg-surface-950 font-mono text-xs leading-relaxed"
             :class="logWrap ? 'whitespace-pre-wrap break-all' : 'whitespace-pre'">
          <div v-for="(line, idx) in logLines" :key="idx" :class="severityClass(line)">
            <span class="text-gray-700 select-none mr-3">{{ String(idx + 1).padStart(4, ' ') }}</span><mark
              v-if="logSearch && line.toLowerCase().includes(logSearch.toLowerCase())"
              class="bg-amber-500/30 text-inherit">{{ line }}</mark><template v-else>{{ line }}</template>
          </div>
          <div v-if="!logLines.length" class="text-gray-600 italic">
            {{ ['QUEUED', 'UPLOADING'].includes(run.status) ? 'Waiting for the GPU…' : 'No log output.' }}
          </div>
          <div v-if="run.status === 'RUNNING'" class="h-3 w-2 bg-emerald-500 animate-pulse inline-block align-middle ml-1"></div>
        </div>
        <div class="p-3 border-t border-white/5 flex justify-between items-center text-[10px] font-mono text-gray-500">
          <span>{{ logLines.length }} lines<template v-if="logLines.length >= LOG_TAIL"> (last {{ LOG_TAIL }})</template></span>
          <span v-if="run.status === 'RUNNING'" class="text-emerald-400">refreshing every 3s</span>
        </div>
      </div>

      <div class="flex gap-4 mt-8 flex-wrap">
        <router-link to="/runs" class="btn-secondary">Back to Runs</router-link>
        <button v-if="['QUEUED', 'RUNNING'].includes(run.status)" @click="doCancel" class="btn-secondary !text-amber-300">Cancel run</button>
        <button v-if="['FINISHED', 'FAILED'].includes(run.status) && run.has_zip" @click="doRerun" class="btn-secondary">Re-run</button>
        <button v-if="!['RUNNING', 'UPLOADING'].includes(run.status)" @click="doDelete" class="btn-secondary !text-red-400">Delete</button>
        <router-link to="/runs?submit=1" class="btn-primary ml-auto">New Evaluation</router-link>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Pie } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import {
  getRun, getRunLog, rerunRun, cancelRun, deleteRun, runVideoUrl, errorText,
} from '../api'
import { useUiStore } from '../stores/ui'
import { formatLocal } from '../utils/datetime'
import {
  STATUS_BADGE, formatDuration, formatRate, formatBytes, runProgress, taskLabel,
} from '../utils/format'

ChartJS.register(ArcElement, Tooltip, Legend)

const LOG_TAIL = 2000

const props = defineProps({ id: [String, Number] })
const ui = useUiStore()
const router = useRouter()

const run = ref(null)
const loading = ref(true)
const error = ref('')

const logText = ref('')
const logBody = ref(null)
const logWrap = ref(true)
const logSearch = ref('')
const copiedHint = ref('')
let followLog = true
let pollTimer = null

const progress = computed(() => runProgress(run.value))
const videoUrl = computed(() => run.value ? runVideoUrl(run.value.id, run.value.finished_at) : '')

// Per-episode results aren't stored; the split follows from rate × the
// episode count the rollout reported (falling back to the configured one).
const summary = computed(() => {
  const r = run.value
  const total = r?.episode_total || r?.settings?.eval_rounds
  if (!r || r.status !== 'FINISHED' || r.success_rate == null || !total) return null
  const ok = Math.round(r.success_rate * total)
  return { total, ok, fail: total - ok }
})

const pieData = computed(() => ({
  labels: ['Success', 'Failed'],
  datasets: [{
    data: [summary.value?.ok || 0, summary.value?.fail || 0],
    backgroundColor: ['rgba(16, 185, 129, 0.85)', 'rgba(239, 68, 68, 0.85)'],
    borderColor: ['rgba(16, 185, 129, 1)', 'rgba(239, 68, 68, 1)'],
    borderWidth: 2,
    hoverOffset: 8,
  }],
}))

const pieOptions = {
  responsive: true,
  maintainAspectRatio: true,
  plugins: {
    legend: {
      position: 'bottom',
      labels: { color: '#cbd5e1', font: { weight: 700 }, padding: 14 },
    },
    tooltip: {
      callbacks: {
        label: (ctx) => {
          const total = ctx.dataset.data.reduce((a, b) => a + b, 0)
          const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : '0.0'
          return `${ctx.label}: ${ctx.parsed} (${pct}%)`
        },
      },
    },
  },
}

const logLines = computed(() => (logText.value ? logText.value.split('\n') : []))
const logMatchCount = computed(() => {
  const q = logSearch.value.toLowerCase()
  return q ? logLines.value.filter(l => l.toLowerCase().includes(q)).length : 0
})

function severityClass(line) {
  if (/traceback|error|exception|failed|fatal/i.test(line)) return 'text-red-400'
  if (/warn/i.test(line)) return 'text-amber-300'
  if (/^\[(worker|rollout)\]|episode \d+/i.test(line)) return 'text-sky-300'
  return 'text-gray-300'
}

function formatSetting(key, v) {
  if (v === null || v === undefined || v === '') return 'auto'
  if (typeof v === 'boolean') return v ? 'on' : 'off'
  if (key === 'timeout_sec') return v === 0 ? 'unlimited' : formatDuration(v)
  if (key === 'episode_length_s') return `${v}s`
  return String(v)
}

// ── Data ─────────────────────────────────────────────────────────────
async function fetchRun() {
  try {
    run.value = (await getRun(props.id)).data
    error.value = ''
  } catch (err) {
    error.value = err.response?.status === 404 ? 'This run does not exist (it may have been deleted).' : errorText(err)
    run.value = null
  } finally {
    loading.value = false
  }
}

async function fetchLog() {
  try {
    logText.value = (await getRunLog(props.id, LOG_TAIL)).data || ''
  } catch { return }
  if (followLog) {
    await nextTick()
    if (logBody.value) logBody.value.scrollTop = logBody.value.scrollHeight
  }
}

function onLogScroll() {
  const el = logBody.value
  followLog = el.scrollTop + el.clientHeight >= el.scrollHeight - 20
}

async function tick() {
  const wasActive = ['QUEUED', 'RUNNING', 'UPLOADING'].includes(run.value?.status)
  await fetchRun()
  // Keep pulling the log while active, plus once more as it finishes.
  if (wasActive || run.value?.status === 'RUNNING') fetchLog()
}

// ── Log tools ────────────────────────────────────────────────────────
async function copyLog() {
  try {
    await navigator.clipboard.writeText(logText.value)
    copiedHint.value = 'Copied'
  } catch {
    copiedHint.value = 'Copy failed'
  }
  setTimeout(() => { copiedHint.value = '' }, 1500)
}

function downloadLog() {
  const blob = new Blob([logText.value], { type: 'text/plain' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `run_${props.id}.log`
  a.click()
  URL.revokeObjectURL(a.href)
}

// ── Actions ──────────────────────────────────────────────────────────
async function doCancel() {
  const ok = await ui.confirm({
    title: `Cancel run #${props.id}?`,
    message: 'The run is stopped and marked FAILED (cancelled). The zip is kept, so it can be re-run.',
    danger: true,
    acceptLabel: 'Cancel run',
  })
  if (!ok) return
  try {
    await cancelRun(props.id)
    ui.toast(`Run #${props.id} cancelled`)
  } catch (err) {
    ui.toast(errorText(err), 'error')
  }
  tick()
}

async function doRerun() {
  try {
    await rerunRun(props.id)
    ui.toast(`Run #${props.id} queued again with the current settings`)
    logText.value = ''
    followLog = true
  } catch (err) {
    ui.toast(errorText(err), 'error')
  }
  fetchRun()
}

async function doDelete() {
  const ok = await ui.confirm({
    title: `Delete run #${props.id}?`,
    message: 'This permanently removes from this worker:',
    bullets: ['the uploaded policy zip', 'the run log', 'the recorded video', 'the result row'],
    danger: true,
    acceptLabel: 'Delete',
  })
  if (!ok) return
  try {
    await deleteRun(props.id)
    ui.toast(`Run #${props.id} deleted`)
    router.push('/runs')
  } catch (err) {
    ui.toast(errorText(err), 'error')
  }
}

async function load() {
  loading.value = true
  logText.value = ''
  followLog = true
  await fetchRun()
  fetchLog()
}

watch(() => props.id, load)

onMounted(() => {
  load()
  pollTimer = setInterval(tick, 3000)
})

onUnmounted(() => {
  clearInterval(pollTimer)
})
</script>
