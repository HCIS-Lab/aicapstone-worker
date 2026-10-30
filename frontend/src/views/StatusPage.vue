<template>
  <div class="max-w-5xl mx-auto px-6 py-16">
    <div class="mb-10">
      <router-link to="/leaderboard" class="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-300 transition-colors mb-4">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        Back to Leaderboard
      </router-link>
      <h1 class="text-3xl font-bold text-white mb-2">Submission #{{ id }}</h1>
      <p class="text-gray-400">{{ sub?.owner || '...' }} · {{ taskLabel(sub?.task_name) }}</p>
    </div>

    <div v-if="loading && !sub" class="glass-card p-16 text-center">
      <div class="w-12 h-12 mx-auto rounded-full border-2 border-brand-500 border-t-transparent animate-spin mb-4"></div>
      <p class="text-gray-400">Loading submission...</p>
    </div>

    <div v-else-if="error" class="glass-card p-10 text-center">
      <div class="w-16 h-16 mx-auto rounded-2xl bg-red-500/20 flex items-center justify-center mb-4 text-2xl">!</div>
      <h3 class="text-lg font-semibold text-white mb-2">Error</h3>
      <p class="text-gray-400 text-sm">{{ error }}</p>
    </div>

    <template v-else-if="sub">
      <!-- Header card -->
      <div class="glass-card p-8 mb-8">
        <div class="flex items-center gap-3 mb-5 flex-wrap">
          <span class="px-3 py-1 rounded-md text-[11px] font-black uppercase tracking-widest bg-brand-500/20 text-brand-400">
            {{ taskLabel(sub.task_name) }}<template v-if="sub.episode_total"> · {{ sub.episode_total }} episodes</template>
          </span>
          <span :class="['badge', STATUS_BADGE[sub.status] || 'badge-queued']">{{ sub.status }}</span>
        </div>

        <!-- Live evaluation progress -->
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
          <span class="text-5xl font-black text-white font-mono tracking-tighter">{{ formatRate(sub.success_rate) }}</span>
          <span class="text-sm font-bold text-gray-500">success rate</span>
        </div>
        <div class="h-2 w-full bg-white/5 rounded-full overflow-hidden mb-6">
          <div class="h-full transition-all duration-1000 bg-gradient-to-r from-emerald-500 to-emerald-400"
               :style="{ width: ((sub.success_rate || 0) * 100) + '%' }"></div>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Submitted</div>
            <div class="text-white font-bold">{{ formatLocal(sub.created_at) }}</div>
          </div>
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Duration</div>
            <div class="text-white font-bold font-mono">{{ formatDuration(sub.duration_sec) }}</div>
          </div>
          <div v-if="sub.status === 'QUEUED' && sub.queue_position">
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Queue</div>
            <div class="text-brand-400 font-bold font-mono">#{{ sub.queue_position }}</div>
          </div>
          <div v-else>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Finished</div>
            <div class="text-white font-bold">{{ formatLocal(sub.finished_at) }}</div>
          </div>
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Checkpoint</div>
            <div class="text-white font-bold truncate" :title="sub.zip_name">{{ formatBytes(sub.zip_size) }}</div>
          </div>
        </div>
      </div>

      <!-- Aggregate results -->
      <div v-if="summary" class="glass-card p-6 mb-8">
        <div class="mb-6">
          <h3 class="text-lg font-bold text-white">Evaluation Summary</h3>
          <p class="text-xs text-gray-500 mt-1">Successful / failed episodes over {{ summary.total }} episodes</p>
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

      <!-- Detected policy -->
      <div v-if="sub.policy_type" class="glass-card p-6 mb-8">
        <h3 class="text-sm font-black text-white uppercase tracking-widest mb-4 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-brand-500"></span> Detected Policy
        </h3>
        <div class="flex items-center gap-3">
          <span class="text-[10px] font-black text-gray-500 uppercase tracking-widest">policy_type</span>
          <span class="px-3 py-1 rounded-md bg-brand-500/20 text-brand-400 text-xs font-black uppercase tracking-widest font-mono">
            {{ sub.policy_type }}
          </span>
        </div>
      </div>

      <!-- Error message (user-facing summary only) -->
      <div v-if="sub.error_message" class="glass-card p-6 border-red-500/20 mb-8">
        <h3 class="text-sm font-bold text-red-400 uppercase tracking-wider mb-3">Evaluation Failed</h3>
        <p class="text-sm text-gray-300">{{ sub.error_message }}</p>
        <p class="text-[11px] text-gray-600 mt-3 italic">Need more detail? Ask an admin to share the full log.</p>
      </div>

      <div class="flex gap-4 mt-8">
        <router-link to="/leaderboard" class="btn-secondary">Back to Leaderboard</router-link>
        <router-link to="/leaderboard?submit=1" class="btn-primary">New Submission</router-link>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Pie } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import { getRun, errorText } from '../api'
import { formatLocal } from '../utils/datetime'
import {
  STATUS_BADGE, formatDuration, formatRate, formatBytes, runProgress, taskLabel,
} from '../utils/format'

ChartJS.register(ArcElement, Tooltip, Legend)

const props = defineProps({ id: [String, Number] })

const sub = ref(null)
const loading = ref(true)
const error = ref('')
let pollTimer = null

const progress = computed(() => runProgress(sub.value))

// Per-episode results aren't stored; the split follows from rate × the
// episode count the rollout reported.
const summary = computed(() => {
  const s = sub.value
  const total = s?.episode_total
  if (!s || s.status !== 'FINISHED' || s.success_rate == null || !total) return null
  const ok = Math.round(s.success_rate * total)
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

async function fetchStatus() {
  try {
    sub.value = (await getRun(props.id)).data
    error.value = ''
    if (['FINISHED', 'FAILED'].includes(sub.value.status)) clearInterval(pollTimer)
  } catch (err) {
    error.value = err.response?.status === 404
      ? 'This submission does not exist or is not yours.'
      : errorText(err, 'Failed to fetch status')
    clearInterval(pollTimer)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchStatus()
  pollTimer = setInterval(fetchStatus, 3000)
})

onUnmounted(() => {
  clearInterval(pollTimer)
})
</script>
