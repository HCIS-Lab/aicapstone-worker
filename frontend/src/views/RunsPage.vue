<template>
  <div class="max-w-[1600px] mx-auto px-6 py-12 relative min-h-screen pb-32">
    <!-- Header -->
    <div class="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
      <div>
        <h1 class="text-5xl font-black text-white mb-3 tracking-tight">Evaluation Runs</h1>
        <p class="text-gray-400 text-lg">Upload policy checkpoints, follow the queue and replay results</p>
      </div>
      <div class="flex items-center gap-4">
        <button @click="fetchRuns()" :disabled="loading"
                class="px-5 py-3 rounded-2xl bg-white/5 border border-white/10 text-xs font-black text-gray-300 hover:text-white hover:bg-white/10 uppercase tracking-widest transition-all">
          <span v-if="loading">Refreshing...</span>
          <span v-else>Refresh</span>
        </button>
      </div>
    </div>

    <!-- Stat cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      <div class="glass-card p-6">
        <p class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2">Total Runs</p>
        <h2 class="text-3xl font-black text-white font-mono">{{ runs.length }}</h2>
      </div>
      <div class="glass-card p-6">
        <p class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2">On GPU</p>
        <h2 class="text-3xl font-black font-mono" :class="current ? 'text-brand-300' : 'text-gray-600'">
          {{ current ? '#' + current : 'idle' }}
        </h2>
      </div>
      <div class="glass-card p-6">
        <p class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2">Queued</p>
        <h2 class="text-3xl font-black text-white font-mono">{{ queuedCount }}</h2>
      </div>
      <div class="glass-card p-6">
        <p class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2">Failure Rate</p>
        <h2 class="text-3xl font-black font-mono" :class="failureRate > 30 ? 'text-red-400' : 'text-white'">
          {{ finishedOrFailed ? failureRate + '%' : '—' }}
        </h2>
      </div>
    </div>

    <!-- Runs table -->
    <div class="glass-card p-6">
      <div class="flex items-center justify-between mb-4 gap-4 flex-wrap">
        <div>
          <h3 class="text-sm font-black text-white uppercase tracking-widest flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-brand-500"></span> Runs
          </h3>
          <p class="text-xs text-gray-500 mt-1">
            Runs execute one at a time on this worker's GPU, in upload order. Policy zips are kept,
            so any finished or failed run can be re-run with the current settings.
          </p>
        </div>
        <button @click="openSubmit" class="btn-primary text-xs py-2.5 px-5">+ New evaluation</button>
      </div>

      <div class="flex items-center gap-2 mb-4 flex-wrap">
        <button v-for="s in STATUS_FILTERS" :key="s.value"
                @click="statusFilter = s.value"
                :class="[
                  'px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all',
                  statusFilter === s.value
                    ? 'bg-brand-500 text-white'
                    : 'bg-white/5 border border-white/10 text-gray-400 hover:text-white'
                ]">
          {{ s.label }}
        </button>
        <select v-model="taskFilter"
                class="px-3 py-2 rounded-xl bg-surface-900 border border-white/10 text-xs text-white focus:border-brand-500 outline-none">
          <option value="">All tasks</option>
          <option v-for="t in taskNames" :key="t" :value="t">{{ t }}</option>
        </select>
        <input v-model="search" placeholder="Search label / zip / id / policy"
               class="px-3 py-2 rounded-xl bg-surface-900 border border-white/10 text-xs text-white focus:border-brand-500 outline-none flex-1 min-w-[180px]" />
        <span class="text-[10px] text-gray-500 ml-auto">
          {{ filteredRuns.length }} / {{ runs.length }} shown
        </span>
      </div>

      <div class="overflow-x-auto rounded-xl border border-white/5">
        <table class="w-full text-sm">
          <thead class="bg-white/2">
            <tr>
              <th class="px-4 py-3 text-left text-[10px] font-black text-gray-500 uppercase tracking-widest">ID</th>
              <th class="px-4 py-3 text-left text-[10px] font-black text-gray-500 uppercase tracking-widest">Checkpoint</th>
              <th class="px-4 py-3 text-left text-[10px] font-black text-gray-500 uppercase tracking-widest">Task</th>
              <th class="px-4 py-3 text-left text-[10px] font-black text-gray-500 uppercase tracking-widest">Policy</th>
              <th class="px-4 py-3 text-left text-[10px] font-black text-gray-500 uppercase tracking-widest">Status</th>
              <th class="px-4 py-3 text-center text-[10px] font-black text-gray-500 uppercase tracking-widest">Success Rate</th>
              <th class="px-4 py-3 text-center text-[10px] font-black text-gray-500 uppercase tracking-widest">Duration</th>
              <th class="px-4 py-3 text-left text-[10px] font-black text-gray-500 uppercase tracking-widest">Submitted</th>
              <th class="px-4 py-3 text-right text-[10px] font-black text-gray-500 uppercase tracking-widest">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/[0.03]">
            <tr v-for="run in filteredRuns" :key="run.id" class="hover:bg-white/[0.02]">
              <td class="px-4 py-3 font-mono text-xs text-gray-500">#{{ run.id }}</td>
              <td class="px-4 py-3">
                <div class="text-white font-bold truncate max-w-[260px]" :title="run.label || run.zip_name">
                  {{ run.label || run.zip_name || '—' }}
                </div>
                <div v-if="run.label && run.zip_name" class="text-[10px] text-gray-600 font-mono truncate max-w-[260px]">
                  {{ run.zip_name }}
                </div>
              </td>
              <td class="px-4 py-3 text-gray-400 text-xs">
                {{ run.task_name }}
                <div v-if="run.settings" class="text-[10px] text-gray-600 font-mono">
                  {{ run.settings.eval_rounds }} eps × {{ run.settings.episode_length_s }}s
                </div>
              </td>
              <td class="px-4 py-3 text-xs font-mono text-gray-300">{{ run.policy_type || '—' }}</td>
              <td class="px-4 py-3">
                <div class="flex flex-col gap-1.5 max-w-[200px]">
                  <span :class="['text-[10px] font-black px-2 py-0.5 rounded-full uppercase tracking-tighter w-fit', statusPillClass(run.status)]"
                        :title="run.error_message || ''">
                    {{ run.status }}
                    <template v-if="run.status === 'QUEUED' && run.queue_position"> · #{{ run.queue_position }}</template>
                  </span>
                  <div class="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                    <div v-if="runProgress(run)"
                         class="h-full bg-brand-500 transition-all duration-1000"
                         :style="{ width: runProgress(run).pct + '%' }"></div>
                    <div v-else :class="[
                      'h-full transition-all duration-1000',
                      run.status === 'FINISHED' ? 'w-full bg-emerald-500' :
                      run.status === 'FAILED' ? 'w-full bg-red-500' :
                      'w-1/3 bg-brand-500/50'
                    ]"></div>
                  </div>
                  <div v-if="runProgress(run)" class="text-[9px] font-bold text-brand-300/80 font-mono tracking-tight">
                    {{ runProgress(run).label }}
                  </div>
                  <div v-else-if="run.status === 'FAILED' && run.error_message"
                       class="text-[9px] text-red-400/80 truncate" :title="run.error_message">
                    {{ run.error_message }}
                  </div>
                </div>
              </td>
              <td class="px-4 py-3 text-center">
                <span v-if="run.success_rate != null" class="text-xl font-black text-white font-mono tracking-tighter">
                  {{ formatRate(run.success_rate) }}
                </span>
                <span v-else class="text-xs font-black text-gray-700 italic">—</span>
              </td>
              <td class="px-4 py-3 text-center font-mono text-xs text-gray-400">{{ formatDuration(run.duration_sec) }}</td>
              <td class="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">{{ formatLocalCompact(run.created_at) }}</td>
              <td class="px-4 py-3 text-right">
                <div class="flex gap-2 justify-end items-center">
                  <router-link :to="`/runs/${run.id}`"
                               class="px-3 py-1 rounded-md bg-white/5 border border-white/10 text-gray-300 text-[10px] font-black uppercase hover:text-white hover:bg-brand-500/20 hover:border-brand-500/30">
                    View
                  </router-link>
                  <button v-if="run.has_video && run.status !== 'RUNNING'" @click="openReplay(run)"
                          class="px-3 py-1 rounded-md bg-purple-500/10 border border-purple-500/20 text-purple-300 text-[10px] font-black uppercase hover:bg-purple-500/20">
                    Replay
                  </button>
                  <button v-if="['QUEUED', 'RUNNING'].includes(run.status)" @click="doCancel(run)"
                          class="px-3 py-1 rounded-md bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[10px] font-black uppercase hover:bg-amber-500/20">
                    Cancel
                  </button>
                  <button v-if="['FINISHED', 'FAILED'].includes(run.status) && run.has_zip" @click="doRerun(run)"
                          class="px-3 py-1 rounded-md bg-brand-500/20 border border-brand-500/30 text-brand-400 text-[10px] font-black uppercase hover:bg-brand-500/30">
                    Re-run
                  </button>
                  <button v-if="!['RUNNING', 'UPLOADING'].includes(run.status)" @click="doDelete(run)"
                          class="px-3 py-1 rounded-md bg-red-500/10 border border-red-500/20 text-red-400 text-[10px] font-black uppercase hover:bg-red-500/20">
                    Delete
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!filteredRuns.length">
              <td colspan="9" class="px-4 py-12 text-center text-gray-600 italic text-sm">
                {{ runs.length ? 'No runs match the current filters.' : 'No runs yet — click "New evaluation" to upload a checkpoint.' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

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
        <div class="text-xl font-black tracking-tight">Evaluate model</div>
        <div class="text-[10px] font-black uppercase tracking-widest text-white/70">{{ tasks.length }} tasks available</div>
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
                <p class="text-gray-400 mt-1">Queue a policy for evaluation on this worker</p>
              </div>
              <button @click="closeSubmit" class="p-3 rounded-xl hover:bg-white/5 text-gray-500 hover:text-white transition-all">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path d="M6 18L18 6M6 6l12 12" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
            </div>

            <div class="flex-1 overflow-y-auto px-8 py-8 space-y-6 no-scrollbar">
              <!-- Task selector -->
              <div class="space-y-3">
                <label class="block text-[10px] font-black text-gray-500 uppercase tracking-widest">Task</label>
                <div v-if="!tasks.length" class="p-5 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-sm">
                  No tasks defined. <router-link to="/tasks" class="underline">Add one</router-link> first.
                </div>
                <div class="grid grid-cols-2 gap-3">
                  <button v-for="t in tasks" :key="t.name"
                          @click="form.task = t.name"
                          :class="[
                            'p-4 rounded-2xl border-2 text-left transition-all',
                            form.task === t.name
                              ? 'border-brand-500 bg-brand-500/10'
                              : 'border-white/10 hover:border-white/20 bg-white/[0.02]'
                          ]">
                    <div class="flex items-center justify-between gap-2 mb-2">
                      <span class="text-sm font-black text-white truncate">{{ taskLabel(t.name) }}</span>
                      <span :class="[
                        'text-[9px] font-black px-2 py-0.5 rounded uppercase shrink-0',
                        t.kind === 'builtin' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-brand-500/20 text-brand-400'
                      ]">
                        {{ t.kind === 'builtin' ? 'built-in' : 'config' }}
                      </span>
                    </div>
                    <div class="text-[10px] text-gray-500 font-mono">
                      {{ effective(t).eval_rounds }} eps × {{ effective(t).episode_length_s }}s
                    </div>
                  </button>
                </div>
              </div>

              <!-- Overrides -->
              <div class="p-5 rounded-2xl bg-surface-900 border border-white/5 space-y-4">
                <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest">This run only (optional)</div>
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Episodes</label>
                    <input v-model="form.eval_rounds" type="number" min="1" step="1"
                           :placeholder="selectedTask ? String(effective(selectedTask).eval_rounds) : ''"
                           class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-brand-500 outline-none" />
                  </div>
                  <div>
                    <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Episode length (s)</label>
                    <input v-model="form.episode_length_s" type="number" min="1" step="any"
                           :placeholder="selectedTask ? String(effective(selectedTask).episode_length_s) : ''"
                           class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-brand-500 outline-none" />
                  </div>
                </div>
                <div>
                  <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Label</label>
                  <input v-model="form.label" type="text" maxlength="120" placeholder="e.g. Group 3 · act · step 40k"
                         class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:border-brand-500 outline-none" />
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
                         class="block p-10 rounded-3xl border-2 border-dashed border-white/10 hover:border-brand-500/50 hover:bg-white/[0.02] text-center transition-all duration-300 cursor-pointer"
                         :class="{ '!border-brand-500 !bg-brand-500/5': file && !zipError, '!border-red-500 !bg-red-500/5': zipError }">
                    <div v-if="!file" class="space-y-4">
                      <div class="w-16 h-16 mx-auto rounded-2xl bg-white/5 flex items-center justify-center text-gray-500 group-hover:text-brand-400 transition-colors">
                        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                      </div>
                      <div>
                        <span class="text-white font-bold block">Click to upload or drag &amp; drop a .zip</span>
                        <span class="text-gray-500 text-sm mt-1 block">Maximum file size: 6GB · LeRobot checkpoint</span>
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
                      <div class="text-left min-w-0">
                        <div class="text-white font-bold truncate">{{ file.name }}</div>
                        <div class="text-gray-500 text-sm italic">{{ formatBytes(file.size) }}</div>
                        <div v-if="zipError" class="text-red-400 text-xs font-bold mt-1">{{ zipError }}</div>
                        <div v-else-if="zipChecking" class="text-gray-400 text-xs font-bold mt-1">Checking zip…</div>
                        <div v-else-if="zipChecked" class="text-emerald-400 text-xs font-bold mt-1">
                          Required files present<span v-if="zipWarning" class="text-amber-300 font-normal"> · {{ zipWarning }}</span>
                        </div>
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              <!-- Required files -->
              <div class="p-5 rounded-3xl bg-surface-900 border border-white/5">
                <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-3">Checkpoint files</div>
                <ul class="space-y-1.5 text-xs font-mono text-gray-400">
                  <li v-for="f in REQUIRED_ZIP_FILES" :key="f" class="flex items-center gap-2">
                    <span class="text-brand-500">▸</span>{{ f }}
                    <span class="text-[9px] text-brand-400 font-sans font-black uppercase tracking-widest">required</span>
                  </li>
                  <li v-for="f in USUAL_ZIP_FILES" :key="f" class="flex items-center gap-2">
                    <span class="text-gray-600">▸</span>{{ f }}
                  </li>
                </ul>
                <p class="text-[10px] text-gray-600 mt-3">At the top level or inside one folder (e.g. pretrained_model/). The policy type is read from config.json.</p>
              </div>

              <div v-if="submitError" class="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-sm">
                {{ submitError }}
              </div>
            </div>

            <div class="p-8 border-t border-white/5 bg-white/[0.02]">
              <button @click="handleSubmit"
                      :disabled="!canSubmit"
                      class="w-full btn-primary py-5 text-lg flex items-center justify-center gap-3 disabled:opacity-50">
                <div v-if="isSubmitting" class="w-5 h-5 border-2 border-white/20 border-t-white animate-spin rounded-full"></div>
                <span v-if="isSubmitting && uploadProgress < 100">Uploading {{ uploadProgress }}%</span>
                <span v-else-if="isSubmitting">Checking checkpoint...</span>
                <span v-else>Queue evaluation{{ form.task ? ' · ' + taskLabel(form.task) : '' }}</span>
              </button>
              <p class="text-center text-xs text-gray-500 mt-4">The zip is kept on this worker so the run can be repeated.</p>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Replay modal -->
    <div v-if="replay" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
         @click.self="replay = null">
      <div class="glass-card w-full max-w-5xl">
        <div class="p-5 border-b border-white/5 flex justify-between items-center">
          <div class="min-w-0">
            <h3 class="text-sm font-black text-white uppercase tracking-widest">Run #{{ replay.id }} · Eval Replay</h3>
            <p class="text-[11px] text-gray-500 mt-1">
              {{ replay.label || replay.zip_name }} · {{ replay.task_name }} · {{ formatRate(replay.success_rate) }}
            </p>
          </div>
          <div class="flex items-center gap-3">
            <a :href="runVideoUrl(replay.id, replay.finished_at)" :download="`run_${replay.id}_eval.mp4`"
               class="text-[10px] font-black text-brand-400 uppercase tracking-widest hover:text-brand-300">Download</a>
            <button @click="replay = null" class="text-gray-400 hover:text-white text-lg">✕</button>
          </div>
        </div>
        <div class="p-5">
          <video :src="runVideoUrl(replay.id, replay.finished_at)" controls autoplay
                 class="w-full rounded-xl border border-white/5 bg-black max-h-[70vh]">
            Your browser does not support HTML5 video.
          </video>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import JSZip from 'jszip'
import {
  listRuns, listTasks, getSettings, createRun, rerunRun, cancelRun, deleteRun,
  runVideoUrl, errorText,
} from '../api'
import { useUiStore } from '../stores/ui'
import { formatLocalCompact } from '../utils/datetime'
import {
  statusPillClass, formatDuration, formatRate, formatBytes, runProgress, taskLabel,
} from '../utils/format'

// Must match _REQUIRED_FILES in local_ui.py.
const REQUIRED_ZIP_FILES = ['config.json', 'model.safetensors']
const USUAL_ZIP_FILES = ['train_config.json', 'policy_preprocessor.json', 'policy_postprocessor.json']
const MAX_ZIP_BYTES = 6 * 1024 * 1024 * 1024
const STATUS_FILTERS = [
  { value: '', label: 'All' },
  { value: 'QUEUED', label: 'Queued' },
  { value: 'RUNNING', label: 'Running' },
  { value: 'FINISHED', label: 'Finished' },
  { value: 'FAILED', label: 'Failed' },
]

const ui = useUiStore()
const route = useRoute()
const router = useRouter()

const runs = ref([])
const current = ref(null)
const tasks = ref([])
const settings = ref(null)
const loading = ref(false)

const statusFilter = ref('')
const taskFilter = ref('')
const search = ref('')

const replay = ref(null)

let pollTimer = null

// ── Derived ──────────────────────────────────────────────────────────
const queuedCount = computed(() => runs.value.filter(r => r.status === 'QUEUED').length)
const finishedOrFailed = computed(() => runs.value.filter(r => ['FINISHED', 'FAILED'].includes(r.status)).length)
const failureRate = computed(() => {
  if (!finishedOrFailed.value) return 0
  const failed = runs.value.filter(r => r.status === 'FAILED').length
  return Math.round((failed / finishedOrFailed.value) * 100)
})
const taskNames = computed(() => [...new Set(runs.value.map(r => r.task_name))].sort())

const filteredRuns = computed(() => {
  const q = search.value.trim().toLowerCase()
  return runs.value.filter(r => {
    if (statusFilter.value && r.status !== statusFilter.value
        && !(statusFilter.value === 'QUEUED' && r.status === 'UPLOADING')) return false
    if (taskFilter.value && r.task_name !== taskFilter.value) return false
    if (!q) return true
    return [String(r.id), r.label, r.zip_name, r.policy_type, r.task_name]
      .some(v => v && String(v).toLowerCase().includes(q))
  })
})

/** Settings a run of this task would get (task override > global). */
function effective(task) {
  const s = settings.value || {}
  return {
    eval_rounds: task.overrides?.eval_rounds ?? s.eval_rounds,
    episode_length_s: task.overrides?.episode_length_s ?? s.episode_length_s,
  }
}

// ── Data ─────────────────────────────────────────────────────────────
async function fetchRuns({ silent = false } = {}) {
  if (!silent) loading.value = true
  try {
    const { data } = await listRuns()
    runs.value = data.runs
    current.value = data.current
  } catch (err) {
    if (err.response?.status !== 401) ui.toast(errorText(err, 'Failed to load runs'), 'error')
  } finally {
    loading.value = false
  }
}

async function fetchTasksAndSettings() {
  try {
    const [t, s] = await Promise.all([listTasks(), getSettings()])
    tasks.value = t.data
    settings.value = s.data
  } catch { /* the runs list still works without them */ }
}

// ── Row actions ──────────────────────────────────────────────────────
async function doCancel(run) {
  const ok = await ui.confirm({
    title: `Cancel run #${run.id}?`,
    message: run.status === 'RUNNING'
      ? 'Isaac Sim is stopped and the run is marked FAILED (cancelled). The zip is kept, so it can be re-run.'
      : 'The run leaves the queue and is marked FAILED (cancelled).',
    danger: true,
    acceptLabel: 'Cancel run',
  })
  if (!ok) return
  try {
    await cancelRun(run.id)
    ui.toast(`Run #${run.id} cancelled`)
  } catch (err) {
    ui.toast(errorText(err), 'error')
  }
  fetchRuns()
}

async function doRerun(run) {
  try {
    await rerunRun(run.id)
    ui.toast(`Run #${run.id} queued again with the current settings`)
  } catch (err) {
    ui.toast(errorText(err), 'error')
  }
  fetchRuns()
}

async function doDelete(run) {
  const ok = await ui.confirm({
    title: `Delete run #${run.id}?`,
    message: 'This permanently removes from this worker:',
    bullets: ['the uploaded policy zip', 'the run log', 'the recorded video', 'the result row'],
    danger: true,
    acceptLabel: 'Delete',
  })
  if (!ok) return
  try {
    await deleteRun(run.id)
    ui.toast(`Run #${run.id} deleted`)
  } catch (err) {
    ui.toast(errorText(err), 'error')
  }
  fetchRuns()
}

function openReplay(run) {
  replay.value = run
}

// ── Submit slide-over ────────────────────────────────────────────────
const isSubmitOpen = ref(false)
const isSubmitting = ref(false)
const uploadProgress = ref(0)
const submitError = ref('')
const file = ref(null)
const zipError = ref('')
const zipWarning = ref('')
const zipChecked = ref(false)
const zipChecking = ref(false)
const form = reactive({ task: '', label: '', eval_rounds: '', episode_length_s: '' })

const selectedTask = computed(() => tasks.value.find(t => t.name === form.task) || null)
const canSubmit = computed(() =>
  !!file.value && !!form.task && !zipError.value && !zipChecking.value && !isSubmitting.value)

function openSubmit() {
  submitError.value = ''
  if (!form.task && tasks.value.length) form.task = tasks.value[0].name
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
  fd.append('label', form.label)
  fd.append('eval_rounds', form.eval_rounds === '' ? '' : String(form.eval_rounds))
  fd.append('episode_length_s', form.episode_length_s === '' ? '' : String(form.episode_length_s))
  try {
    const { data } = await createRun(fd, (p) => { uploadProgress.value = p })
    ui.toast(`Run #${data.id} queued`)
    file.value = null
    zipChecked.value = false
    zipWarning.value = ''
    form.label = ''
    form.eval_rounds = ''
    form.episode_length_s = ''
    isSubmitting.value = false
    closeSubmit()
    router.push(`/runs/${data.id}`)
  } catch (err) {
    submitError.value = errorText(err, 'Upload failed')
  } finally {
    isSubmitting.value = false
  }
}

// ── Lifecycle ────────────────────────────────────────────────────────
watch(() => route.query.submit, (v) => { if (v) openSubmit() })

onMounted(async () => {
  await Promise.all([fetchRuns(), fetchTasksAndSettings()])
  if (route.query.submit) openSubmit()
  pollTimer = setInterval(() => fetchRuns({ silent: true }), 3000)
})

onUnmounted(() => {
  clearInterval(pollTimer)
})
</script>
