<template>
  <div class="max-w-[1600px] mx-auto px-6 py-12 relative min-h-screen pb-20">
    <!-- Header -->
    <div class="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
      <div>
        <h1 class="text-5xl font-black text-white mb-3 tracking-tight">Settings</h1>
        <p class="text-gray-400 text-lg">Evaluation parameters for every run on this worker</p>
      </div>
    </div>

    <div class="space-y-8">
      <!-- Eval settings -->
      <div class="glass-card p-6">
        <div class="flex justify-between items-center mb-4 flex-wrap gap-3">
          <div>
            <h3 class="text-sm font-black text-white uppercase tracking-widest flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-brand-500"></span> Eval Settings
            </h3>
            <p class="text-[11px] text-gray-500 mt-1">
              Apply to the next run that starts (no restart). A task can override episodes and episode
              length, and a single run can override them again. Set
              <span class="font-mono text-gray-300">Total eval timeout</span> to
              <span class="font-mono text-gray-300">0</span> to remove the total-execution-time limit.
            </p>
          </div>
          <button @click="fetchSettings" class="text-[10px] font-black text-gray-400 uppercase tracking-widest hover:text-white">Refresh</button>
        </div>

        <div v-if="!form" class="text-sm text-gray-500 italic py-4">Loading…</div>
        <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div v-for="s in FIELDS" :key="s.key" class="rounded-xl border border-white/10 bg-surface-900 p-4">
            <div class="flex items-center justify-between gap-2 mb-2">
              <label class="text-[11px] font-bold text-gray-300">{{ s.label }}</label>
              <span v-if="isChanged(s.key)" class="text-[9px] font-black text-sky-400 uppercase tracking-widest">unsaved</span>
              <span v-else-if="isOverridden(s.key)" class="text-[9px] font-black text-amber-400 uppercase tracking-widest">overridden</span>
              <span v-else class="text-[9px] font-black text-gray-600 uppercase tracking-widest">default</span>
            </div>
            <div class="flex items-center gap-2">
              <button v-if="s.type === 'bool'" @click="form[s.key] = !form[s.key]"
                      :class="form[s.key] ? 'bg-emerald-500 border-emerald-400' : 'bg-white/5 border-white/10'"
                      class="w-14 h-8 rounded-full border flex items-center px-1 transition-colors">
                <span class="w-6 h-6 rounded-full bg-white shadow-md transition-transform duration-200"
                      :class="form[s.key] ? 'translate-x-6' : 'translate-x-0'"></span>
              </button>
              <input v-else v-model="form[s.key]" :type="s.type === 'text' ? 'text' : 'number'"
                     :min="s.min" :step="s.step" :placeholder="s.placeholder"
                     class="flex-1 bg-surface-950 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-brand-500 outline-none" />
              <span class="text-[10px] text-gray-500 font-mono">key: {{ s.key }}</span>
            </div>
            <div class="text-[10px] text-gray-600 mt-1.5">{{ s.help }}</div>
            <div class="text-[10px] text-gray-600 mt-1 font-mono">
              default: {{ display(s.key, defaults?.[s.key]) }} · effective: {{ display(s.key, saved?.[s.key]) }}
            </div>
          </div>
        </div>

        <div v-if="saveError" class="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs">{{ saveError }}</div>

        <div class="flex gap-2 mt-4 flex-wrap">
          <button @click="save" :disabled="saving || !form"
                  class="px-5 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-xs font-black text-white uppercase tracking-widest">
            {{ saving ? 'Saving…' : 'Save Eval Settings' }}
          </button>
          <button @click="form.timeout_sec = 0" :disabled="saving || !form"
                  class="px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-xs font-black text-gray-300 uppercase tracking-widest hover:text-white disabled:opacity-50">
            Set timeout = unlimited
          </button>
          <button @click="restoreDefaults" :disabled="saving || !form || !defaults"
                  class="px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-xs font-black text-gray-300 uppercase tracking-widest hover:text-white disabled:opacity-50">
            Restore defaults
          </button>
        </div>
      </div>

      <!-- Worker info -->
      <div v-if="auth.me" class="glass-card p-6">
        <h3 class="text-sm font-black text-white uppercase tracking-widest mb-4 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-brand-500"></span> Worker
        </h3>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Name</div>
            <div class="text-white font-bold">{{ auth.me.worker_name }}</div>
          </div>
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">GPU</div>
            <div class="text-white font-bold font-mono">{{ auth.me.gpu_id }}</div>
          </div>
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Mode</div>
            <div class="font-bold uppercase" :class="auth.me.eval_mode === 'real' ? 'text-emerald-400' : 'text-amber-400'">
              {{ auth.me.eval_mode }}
            </div>
          </div>
          <div>
            <div class="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-1">Changed in</div>
            <div class="text-gray-300 font-mono text-xs">.env → <span class="text-gray-500">docker compose up -d</span></div>
          </div>
        </div>
        <p v-if="auth.me.eval_mode === 'mock'" class="mt-4 text-xs text-amber-300/80">
          Mock mode: runs return synthetic scores without Isaac Sim. Use it to try the UI, never for grading.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getSettings, getDefaultSettings, updateSettings, errorText } from '../api'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'
import { formatDuration } from '../utils/format'

const FIELDS = [
  { key: 'eval_rounds', label: 'Episodes per eval', type: 'int', min: 1, step: 1,
    help: 'How many episodes one run evaluates; the success rate is over these.' },
  { key: 'episode_length_s', label: 'Episode length (seconds)', type: 'float', min: 1, step: 'any',
    help: 'Simulated time before an episode counts as failed.' },
  { key: 'timeout_sec', label: 'Total eval timeout (seconds)', type: 'int', min: 0, step: 1,
    help: 'Wall-clock limit for a whole run, Isaac Sim start-up included. 0 = unlimited.' },
  { key: 'device', label: 'Policy device', type: 'text', placeholder: 'cuda:0',
    help: 'cpu, cuda or cuda:N inside the container (the container only sees its own GPU, as cuda:0).' },
  { key: 'action_horizon', label: 'Action horizon override', type: 'int', min: 1, step: 1, placeholder: 'from checkpoint',
    help: 'Actions executed per policy query. Empty = the checkpoint / policy default.' },
  { key: 'daily_quota', label: 'Submissions per group per 24 h', type: 'int', min: 0, step: 1,
    help: 'How many models each student group may submit in any 24-hour window. 0 = unlimited. Admin uploads are not counted.' },
  { key: 'record_video', label: 'Record eval video', type: 'bool',
    help: 'Save an mp4 of the run for replay. Costs some GPU time and disk.' },
]

const auth = useAuthStore()
const ui = useUiStore()

const saved = ref(null)
const defaults = ref(null)
const form = ref(null)
const saving = ref(false)
const saveError = ref('')

function display(key, v) {
  if (v === undefined) return '…'
  if (v === null || v === '') return 'auto'
  if (typeof v === 'boolean') return v ? 'on' : 'off'
  if (key === 'daily_quota' && Number(v) === 0) return 'unlimited'
  if (key === 'timeout_sec') return Number(v) === 0 ? 'unlimited' : `${v}s (${formatDuration(Number(v))})`
  return String(v)
}

const norm = (v) => (v === null || v === undefined ? '' : String(v))
const isChanged = (key) => !!saved.value && norm(form.value?.[key]) !== norm(saved.value[key])
const isOverridden = (key) => !!defaults.value && norm(saved.value?.[key]) !== norm(defaults.value[key])

async function fetchSettings() {
  try {
    const [s, d] = await Promise.all([getSettings(), getDefaultSettings()])
    saved.value = s.data
    defaults.value = d.data
    form.value = { ...s.data }
    saveError.value = ''
  } catch (err) {
    ui.toast(errorText(err, 'Failed to load settings'), 'error')
  }
}

function restoreDefaults() {
  form.value = { ...defaults.value }
}

async function save() {
  saving.value = true
  saveError.value = ''
  try {
    saved.value = (await updateSettings(form.value)).data
    form.value = { ...saved.value }
    ui.toast('Settings saved — they apply to runs that start from now on')
  } catch (err) {
    saveError.value = errorText(err, 'Save failed')
  } finally {
    saving.value = false
  }
}

onMounted(fetchSettings)
</script>
