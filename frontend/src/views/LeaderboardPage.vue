<template>
  <div class="max-w-[1600px] mx-auto px-6 py-12 relative min-h-screen pb-32">
    <!-- Header -->
    <div class="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
      <div>
        <h1 class="text-5xl font-black text-white mb-3 tracking-tight">Physical AI Course Project Evaluation Platform</h1>
        <p class="text-gray-400 text-lg">Real-Time Evaluation Leaderboard</p>
      </div>
    </div>

    <!-- Per-task leaderboards -->
    <div class="space-y-10">
      <div v-if="!loading && !boards.length" class="glass-card p-12 text-center text-gray-500 text-sm italic">
        No tasks yet. Your instructor has not set up the evaluation.
      </div>

      <div v-for="board in boards" :key="board.task">
        <div class="flex items-center justify-between mb-4 px-2">
          <h2 class="text-xl font-black text-white tracking-tight flex items-center gap-3">
            <span class="w-2 h-2 rounded-full bg-brand-500 shadow-sm shadow-brand-500/50"></span>
            {{ taskLabel(board.task) }}
            <span v-if="board.task === myTask" class="text-[9px] font-black px-2 py-0.5 rounded bg-brand-500/20 text-brand-300 uppercase tracking-widest">your task</span>
          </h2>
          <span class="text-[10px] font-black text-gray-500 uppercase tracking-widest">
            {{ board.rows.length }} Groups
          </span>
        </div>

        <div class="glass-card overflow-hidden">
          <div v-if="loading" class="flex flex-col items-center justify-center py-16">
            <div class="w-10 h-10 border-2 border-brand-500/20 border-t-brand-500 animate-spin rounded-full mb-4"></div>
            <p class="text-xs font-black text-gray-500 uppercase tracking-widest animate-pulse">Syncing...</p>
          </div>

          <table v-else class="w-full border-collapse">
            <thead>
              <tr class="bg-white/2 border-b border-white/5">
                <th class="px-5 py-4 text-left text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] w-16">#</th>
                <th class="px-5 py-4 text-left text-[10px] font-black text-gray-500 uppercase tracking-[0.2em]">Group</th>
                <th class="px-5 py-4 text-left text-[10px] font-black text-gray-500 uppercase tracking-[0.2em]">Status</th>
                <th class="px-5 py-4 text-right text-[10px] font-black text-gray-500 uppercase tracking-[0.2em]">Success Rate</th>
                <th class="px-5 py-4 text-right text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] w-28" title="Wallclock duration of the best run. Lower wins ties.">Time</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-white/[0.03]">
              <tr v-if="!board.rows.length">
                <td colspan="5" class="px-5 py-10 text-center text-xs text-gray-600 italic">No groups on this task yet.</td>
              </tr>
              <tr v-for="entry in board.rows" :key="entry.user"
                  class="group hover:bg-white/[0.02] transition-all duration-300"
                  :class="[entry.run_id ? 'cursor-pointer' : '', entry.mine ? 'bg-brand-500/[0.04]' : '']"
                  @click="entry.run_id && router.push(`/status/${entry.run_id}`)">
                <td class="px-5 py-5">
                  <span class="text-sm font-black font-mono"
                        :class="entry.success_rate == null ? 'text-gray-700'
                          : entry.rank === 1 ? 'text-amber-400' : entry.rank === 2 ? 'text-gray-300'
                          : entry.rank === 3 ? 'text-orange-400' : 'text-gray-600'">
                    {{ entry.rank }}
                  </span>
                </td>
                <td class="px-5 py-5 text-sm">
                  <span class="font-bold transition-colors"
                        :class="entry.mine ? 'text-brand-300' : 'text-white group-hover:text-brand-400'">{{ entry.user }}</span>
                  <span v-if="entry.mine" class="ml-2 text-[9px] font-black text-brand-400 uppercase tracking-widest">you</span>
                </td>
                <td class="px-5 py-5">
                  <template v-if="entry.active_status">
                    <span class="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-tighter text-brand-400">
                      <span class="relative flex h-1.5 w-1.5">
                        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75"></span>
                        <span class="relative inline-flex rounded-full h-1.5 w-1.5 bg-brand-500"></span>
                      </span>
                      {{ entry.active_status }}
                    </span>
                  </template>
                  <template v-else-if="entry.success_rate != null">
                    <span class="text-[10px] font-bold text-gray-600 uppercase">
                      <template v-if="entry.run_id">#{{ entry.run_id }} · </template>{{ formatRelative(entry.timestamp) }}
                    </span>
                  </template>
                  <template v-else-if="entry.submissions">
                    <span class="text-[10px] font-black uppercase tracking-tighter text-red-400/80">No finished run</span>
                  </template>
                  <template v-else>
                    <span class="text-[10px] font-bold text-gray-700 uppercase italic">No Submissions</span>
                  </template>
                </td>
                <td class="px-5 py-5 text-right">
                  <span class="text-lg font-black font-mono"
                        :class="entry.success_rate > 0 ? 'text-white' : 'text-gray-700'">
                    {{ ((entry.success_rate || 0) * 100).toFixed(1) }}%
                  </span>
                </td>
                <td class="px-5 py-5 text-right">
                  <span class="text-xs font-mono"
                        :class="entry.duration_sec ? 'text-gray-400' : 'text-gray-700'">
                    {{ entry.duration_sec ? formatDuration(entry.duration_sec) : '—' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Personal Submission History -->
    <div v-if="mySubmissions.length > 0" class="mt-16 mb-20">
      <div class="flex items-center justify-between mb-8 px-2">
        <div class="flex items-center gap-4">
          <div class="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-xl shadow-inner">📜</div>
          <div>
            <h2 class="text-3xl font-black text-white tracking-tight leading-none mb-1">Your Submissions</h2>
            <p class="text-gray-500 text-sm font-medium">All attempts for your group</p>
          </div>
        </div>
        <span class="text-[10px] font-black text-gray-400 uppercase tracking-widest bg-white/5 px-4 py-2 rounded-xl border border-white/5">
          Total: {{ mySubmissions.length }}
        </span>
      </div>

      <div class="glass-card overflow-hidden">
        <table class="w-full">
          <thead>
            <tr class="bg-white/2 border-b border-white/5">
              <th class="px-6 py-4 text-left text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] w-24">ID</th>
              <th class="px-6 py-4 text-left text-[10px] font-black text-gray-500 uppercase tracking-[0.2em]">Task</th>
              <th class="px-6 py-4 text-left text-[10px] font-black text-gray-500 uppercase tracking-[0.2em]">Submitted</th>
              <th class="px-6 py-4 text-left text-[10px] font-black text-gray-500 uppercase tracking-[0.2em]">Status</th>
              <th class="px-6 py-4 text-center text-[10px] font-black text-gray-500 uppercase tracking-[0.2em]">Success Rate</th>
              <th class="px-6 py-4 text-right text-[10px] font-black text-gray-500 uppercase tracking-[0.2em]">Detail</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/[0.03]">
            <tr v-for="sub in mySubmissions" :key="sub.id" class="group hover:bg-white/[0.02] transition-colors">
              <td class="px-6 py-4 font-mono text-xs text-gray-500">#{{ sub.id }}</td>
              <td class="px-6 py-4">
                <span class="px-2 py-0.5 rounded-md text-[10px] font-black uppercase tracking-tighter bg-brand-500/20 text-brand-400">
                  {{ taskLabel(sub.task_name) }}
                </span>
              </td>
              <td class="px-6 py-4 text-xs text-gray-400">{{ formatLocal(sub.created_at) }}</td>
              <td class="px-6 py-4">
                <div class="flex flex-col gap-1.5 max-w-[200px]">
                  <span :class="['text-[10px] font-black px-2 py-0.5 rounded-full uppercase tracking-tighter w-fit', statusPillClass(sub.status)]">
                    {{ sub.status }}<template v-if="sub.queue_position"> · #{{ sub.queue_position }}</template>
                  </span>
                  <div class="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                    <div v-if="runProgress(sub)"
                         class="h-full bg-brand-500 transition-all duration-1000"
                         :style="{ width: runProgress(sub).pct + '%' }"></div>
                    <div v-else :class="[
                      'h-full transition-all duration-1000',
                      sub.status === 'FINISHED' ? 'w-full bg-emerald-500' :
                      sub.status === 'FAILED' ? 'w-full bg-red-500' :
                      'w-1/3 bg-brand-500/50'
                    ]"></div>
                  </div>
                  <div v-if="runProgress(sub)" class="text-[9px] font-bold text-brand-300/80 font-mono tracking-tight">
                    {{ runProgress(sub).label }}
                  </div>
                </div>
              </td>
              <td class="px-6 py-4 text-center">
                <span v-if="sub.success_rate != null" class="text-xl font-black text-white font-mono tracking-tighter">
                  {{ (sub.success_rate * 100).toFixed(1) }}%
                </span>
                <span v-else class="text-xs font-black text-gray-700 italic">—</span>
              </td>
              <td class="px-6 py-4 text-right">
                <router-link :to="`/status/${sub.id}`"
                             class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white/5 border border-white/5 text-[10px] font-black text-gray-400 hover:text-white hover:bg-brand-500/20 hover:border-brand-500/30 transition-all uppercase tracking-widest">
                  View
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path d="M14 5l7 7m0 0l-7 7m7-7H3" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- About -->
    <section class="mt-16 glass-card p-10">
      <h2 class="text-2xl font-black text-white mb-5 tracking-tight">How evaluation works</h2>
      <div class="space-y-4 text-sm text-gray-400 leading-relaxed max-w-4xl">
        <p>
          Upload your trained LeRobot policy as a zip. It joins the queue and runs in NVIDIA Isaac Lab
          on this school's GPU, one submission at a time, in upload order.
        </p>
        <p>
          Each policy is evaluated over a fixed number of episodes set by your instructor; the score is
          the success rate over those episodes. The leaderboard shows each group's best finished run,
          with the shorter run winning ties.
        </p>
        <p v-if="quotaLimit">
          Each group can submit {{ quotaLimit }} time{{ quotaLimit === 1 ? '' : 's' }} in any 24 hours.
          Failed runs count toward the limit, so check your zip before uploading.
        </p>
      </div>
    </section>

    <!-- Submit FAB -->
    <button
      @click="openSubmit"
      class="fixed bottom-10 right-10 flex items-center gap-4 bg-brand-500 hover:bg-brand-600 text-white px-10 py-6 rounded-3xl shadow-2xl shadow-brand-500/40 transition-all duration-500 hover:scale-105 group z-40 border border-white/10 ring-4 ring-brand-500/20"
    >
      <div class="w-10 h-10 rounded-2xl bg-white/20 flex items-center justify-center group-hover:rotate-12 transition-transform shadow-inner">
        <svg class="w-6 h-6 fill-current" viewBox="0 0 24 24">
          <path d="M12 4v16m8-8H4" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
        </svg>
      </div>
      <div class="text-left leading-tight">
        <div class="text-xl font-black tracking-tight">Submit model</div>
        <div class="text-[10px] font-black uppercase tracking-widest text-white/70">For {{ myTask ? taskLabel(myTask) : 'any task' }}</div>
      </div>
    </button>

    <!-- Submit Slide-over -->
    <Transition name="slide">
      <div v-if="isSubmitOpen" class="fixed inset-0 z-50 overflow-hidden">
        <div class="absolute inset-0 bg-surface-950/80 backdrop-blur-sm" @click="closeSubmit"></div>
        <div class="absolute inset-y-0 right-0 max-w-xl w-full flex">
          <div class="h-full w-full glass-card !rounded-none border-y-0 border-r-0 flex flex-col shadow-2xl shadow-black/50 bg-surface-900/95">
            <div class="px-8 py-8 border-b border-white/5 flex items-center justify-between">
              <div>
                <h2 class="text-3xl font-black text-white tracking-tight">Submit Checkpoint</h2>
                <p class="text-gray-400 mt-1">Upload your model for {{ form.task ? taskLabel(form.task) : '…' }}</p>
              </div>
              <button @click="closeSubmit" class="p-3 rounded-xl hover:bg-white/5 text-gray-500 hover:text-white transition-all">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path d="M6 18L18 6M6 6l12 12" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>

            <div class="flex-1 overflow-y-auto px-8 py-8 space-y-6 no-scrollbar">
              <!-- Quota dots -->
              <div class="p-5 rounded-2xl bg-surface-900 border border-white/5 flex items-center justify-between">
                <div>
                  <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-3">Quota · last 24 h</div>
                  <div v-if="quotaLimit" class="flex gap-1.5 flex-wrap">
                    <div v-for="i in quotaLimit" :key="i"
                         class="w-2.5 h-2.5 rounded-full transition-all duration-500 shadow-sm"
                         :class="i <= quotaLeft
                           ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]'
                           : 'bg-white/5 border border-white/10'">
                    </div>
                  </div>
                  <div v-else class="text-xs font-bold text-emerald-400">Unlimited</div>
                </div>
                <div class="text-right">
                  <div class="text-2xl font-black text-white font-mono leading-none">
                    {{ quotaLimit ? quotaLeft : '∞' }}
                  </div>
                  <div class="text-[9px] font-black text-brand-400 uppercase tracking-tighter mt-1">Remaining</div>
                </div>
              </div>

              <!-- Task: fixed when assigned, else pick -->
              <div v-if="myTask" class="p-5 rounded-2xl bg-brand-500/10 border border-brand-500/20 text-brand-300">
                <div class="flex gap-3">
                  <svg class="w-6 h-6 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                  <div class="text-sm">
                    <p class="font-bold mb-1">Assigned Task</p>
                    <p class="opacity-80">You are evaluated on <b>{{ taskLabel(myTask) }}</b>. Submissions queue and run in order.</p>
                  </div>
                </div>
              </div>
              <div v-else class="space-y-3">
                <label class="block text-[10px] font-black text-gray-500 uppercase tracking-widest">Task</label>
                <div class="grid grid-cols-2 gap-3">
                  <button v-for="t in tasks" :key="t.name"
                          @click="form.task = t.name"
                          :class="[
                            'p-4 rounded-2xl border-2 text-left transition-all',
                            form.task === t.name
                              ? 'border-brand-500 bg-brand-500/10'
                              : 'border-white/10 hover:border-white/20 bg-white/[0.02]'
                          ]">
                    <div class="text-sm font-black text-white truncate">{{ taskLabel(t.name) }}</div>
                    <div v-if="t.description" class="text-[10px] text-gray-500 mt-1 truncate">{{ t.description }}</div>
                  </button>
                </div>
              </div>

              <!-- File Upload -->
              <div class="space-y-3">
                <label class="block text-[10px] font-black text-gray-500 uppercase tracking-widest">pretrained_model.zip</label>
                <div class="relative group cursor-pointer"
                     @dragover.prevent
                     @drop.prevent="handleFileDrop">
                  <input type="file" class="hidden" id="checkpoint-file"
                         accept=".zip,application/zip" @change="handleFileChange" />
                  <label for="checkpoint-file"
                         class="block p-10 rounded-3xl border-2 border-dashed border-white/10 hover:border-brand-500/50 hover:bg-white/[0.02] text-center transition-all duration-300"
                         :class="{ '!border-brand-500 !bg-brand-500/5': file && !zipError, '!border-red-500 !bg-red-500/5': zipError }">
                    <div v-if="!file" class="space-y-4">
                      <div class="w-16 h-16 mx-auto rounded-2xl bg-white/5 flex items-center justify-center text-gray-500 group-hover:text-brand-400 transition-colors">
                        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                      </div>
                      <div>
                        <span class="text-white font-bold block">Click to upload or drag &amp; drop a .zip</span>
                        <span class="text-gray-500 text-sm mt-1 block">Maximum file size: 6GB</span>
                      </div>
                    </div>
                    <div v-else class="flex items-center justify-center gap-4">
                      <div class="w-12 h-12 rounded-xl flex items-center justify-center"
                           :class="zipError ? 'bg-red-500/20 text-red-400' : 'bg-emerald-500/20 text-emerald-400'">
                        <svg v-if="!zipError" class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M5 13l4 4L19 7" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                        <svg v-else class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M6 18L18 6M6 6l12 12" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                      </div>
                      <div class="text-left">
                        <div class="text-white font-bold">{{ file.name }}</div>
                        <div class="text-gray-500 text-sm italic">{{ formatBytes(file.size) }}</div>
                        <div v-if="zipChecking" class="text-gray-400 text-xs font-bold mt-1">Checking…</div>
                        <div v-else-if="zipError" class="text-red-400 text-xs font-bold mt-1">{{ zipError }}</div>
                        <div v-else-if="zipChecked" class="text-emerald-400 text-xs font-bold mt-1">
                          Required files present<span v-if="zipWarning" class="text-amber-400 font-normal"> · {{ zipWarning }}</span>
                        </div>
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              <!-- Required files -->
              <div class="p-5 rounded-3xl bg-surface-900 border border-white/5">
                <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-3">Expected files</div>
                <ul class="space-y-1.5 text-xs font-mono text-gray-400">
                  <li v-for="f in REQUIRED_ZIP_FILES" :key="f" class="flex items-center gap-2">
                    <span class="text-brand-500">▸</span>{{ f }}<span class="text-[9px] text-red-400/80 font-sans font-black uppercase">required</span>
                  </li>
                  <li v-for="f in USUAL_ZIP_FILES" :key="f" class="flex items-center gap-2">
                    <span class="text-brand-500">▸</span>{{ f }}
                  </li>
                </ul>
              </div>

              <div v-if="submitError" class="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-sm">{{ submitError }}</div>
            </div>

            <div class="p-8 border-t border-white/5 bg-white/[0.02]">
              <button @click="handleSubmit"
                      :disabled="!canSubmit"
                      class="w-full btn-primary py-5 text-lg flex items-center justify-center gap-3 disabled:opacity-50">
                <div v-if="isSubmitting" class="w-5 h-5 border-2 border-white/20 border-t-white animate-spin rounded-full"></div>
                <span v-if="isSubmitting && uploadProgress < 100">Uploading {{ uploadProgress }}%</span>
                <span v-else-if="isSubmitting">Checking zip...</span>
                <span v-else-if="quotaLimit && quotaLeft === 0">Quota used, try again later</span>
                <span v-else>Confirm submission</span>
              </button>
              <p class="text-center text-xs text-gray-500 mt-4">By submitting, you agree to the course code of conduct.</p>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import JSZip from 'jszip'
import { getLeaderboard, listRuns, listTasks, createRun, errorText } from '../api'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'
import { parseUTC, formatLocal } from '../utils/datetime'
import { statusPillClass, formatDuration, formatBytes, runProgress, taskLabel } from '../utils/format'

const REQUIRED_ZIP_FILES = ['config.json', 'model.safetensors']
const USUAL_ZIP_FILES = ['train_config.json', 'policy_preprocessor.json', 'policy_postprocessor.json']
const MAX_ZIP_BYTES = 6 * 1024 * 1024 * 1024

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()
const route = useRoute()

const boards = ref([])
const loading = ref(true)
const mySubmissions = ref([])
const tasks = ref([])

const myTask = computed(() => auth.me?.assigned_task || null)
const quotaLimit = computed(() => auth.stats?.daily_quota || 0)
const quotaLeft = computed(() => auth.stats?.remaining ?? quotaLimit.value)

const isSubmitOpen = ref(false)
const isSubmitting = ref(false)
const uploadProgress = ref(0)
const submitError = ref('')
const file = ref(null)
const zipError = ref('')
const zipWarning = ref('')
const zipChecked = ref(false)
const zipChecking = ref(false)
const form = reactive({ task: '' })

const canSubmit = computed(() =>
  !!file.value && !!form.task && !zipError.value && !zipChecking.value && !isSubmitting.value
  && !(quotaLimit.value && quotaLeft.value === 0))

let pollTimer = null

function formatRelative(ts) {
  const d = parseUTC(ts)
  if (!d) return ''
  const mins = Math.floor((Date.now() - d.getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

async function fetchBoards() {
  try {
    boards.value = (await getLeaderboard()).data
  } catch (err) {
    console.error('Leaderboard fetch error:', err)
  } finally {
    loading.value = false
  }
}

async function fetchMine() {
  try {
    mySubmissions.value = (await listRuns()).data.runs
  } catch (err) {
    console.error('Submissions fetch error:', err)
  }
  auth.refreshStats()
}

async function fetchTasks() {
  try {
    tasks.value = (await listTasks()).data
  } catch { /* the slide-over shows no choices */ }
}

function openSubmit() {
  submitError.value = ''
  form.task = myTask.value || form.task || tasks.value[0]?.name || ''
  isSubmitOpen.value = true
}

function closeSubmit() {
  if (isSubmitting.value) return
  isSubmitOpen.value = false
  if (route.query.submit) router.replace({ query: {} })
}

function handleFileChange(e) {
  setFile(e.target.files[0])
  e.target.value = ''
}

function handleFileDrop(e) {
  setFile(e.dataTransfer.files[0])
}

function setFile(f) {
  file.value = f || null
  submitError.value = ''
  validateZip(file.value)
}

async function validateZip(f) {
  zipError.value = ''
  zipWarning.value = ''
  zipChecked.value = false
  if (!f) return
  if (f.size > MAX_ZIP_BYTES) {
    zipError.value = `File exceeds 6GB (${formatBytes(f.size)})`
    return
  }
  if (!/\.zip$/i.test(f.name)) {
    zipError.value = 'File must be a .zip archive'
    return
  }
  zipChecking.value = true
  try {
    const zip = await JSZip.loadAsync(f)
    const names = new Set(Object.keys(zip.files).map(p => p.split('/').pop()))
    const missing = REQUIRED_ZIP_FILES.filter(n => !names.has(n))
    if (missing.length) {
      zipError.value = `Missing: ${missing.join(', ')}`
      return
    }
    const absent = USUAL_ZIP_FILES.filter(n => !names.has(n))
    if (absent.length) zipWarning.value = `no ${absent.join(', ')}`
    zipChecked.value = true
  } catch {
    // JSZip can't open some very large zips in the browser; the worker
    // checks the zip again after the upload, so let it through.
    zipWarning.value = 'could not inspect in the browser; checked after upload'
    zipChecked.value = true
  } finally {
    zipChecking.value = false
  }
}

async function handleSubmit() {
  if (!canSubmit.value) return
  isSubmitting.value = true
  uploadProgress.value = 0
  submitError.value = ''
  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('task_name', form.task)
  try {
    const { data } = await createRun(fd, (p) => { uploadProgress.value = p })
    ui.toast(`Submission #${data.id} queued`)
    file.value = null
    zipChecked.value = false
    zipWarning.value = ''
    isSubmitting.value = false
    closeSubmit()
    router.push(`/status/${data.id}`)
  } catch (err) {
    submitError.value = errorText(err, 'Submission failed')
    fetchMine()
  } finally {
    isSubmitting.value = false
  }
}

onMounted(async () => {
  fetchBoards()
  fetchMine()
  await fetchTasks()
  pollTimer = setInterval(() => {
    fetchBoards()
    fetchMine()
  }, 5000)
  if (route.query.submit) openSubmit()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>
