<template>
  <div class="max-w-[1600px] mx-auto px-6 py-12 relative min-h-screen pb-20">
    <!-- Header -->
    <div class="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
      <div>
        <h1 class="text-5xl font-black text-white mb-3 tracking-tight">Tasks</h1>
        <p class="text-gray-400 text-lg">What a checkpoint is evaluated on: built-in simulator tasks or your own eval configs</p>
      </div>
      <div class="flex items-center gap-4">
        <button @click="fetchTasks"
                class="px-5 py-3 rounded-2xl bg-white/5 border border-white/10 text-xs font-black text-gray-300 hover:text-white hover:bg-white/10 uppercase tracking-widest transition-all">
          Reload
        </button>
        <button @click="openEditor(null)" class="btn-primary text-sm">+ New task</button>
      </div>
    </div>

    <div class="space-y-6">
      <!-- Editor -->
      <div v-if="editor" ref="editorEl" class="glass-card p-6">
        <div class="flex items-start justify-between gap-4 flex-wrap mb-6">
          <div>
            <h3 class="text-sm font-black text-white uppercase tracking-widest flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-brand-500"></span>
              {{ editor.isNew ? 'New task' : `Edit task · ${editor.name}` }}
            </h3>
            <p class="text-xs text-gray-500 mt-2 max-w-2xl">
              An eval config is a Python file that registers an IsaacLab task — anything
              <span class="font-mono text-gray-400">rollout.py --task=&lt;file.py&gt;</span> accepts. Start from a
              built-in task in <span class="font-mono text-gray-400">sim/packages/simulator/src/simulator/tasks/</span>.
              A gym id points at a task that is already registered in the simulator package.
            </p>
          </div>
        </div>

        <div class="rounded-2xl border border-white/10 bg-surface-900 p-5 space-y-5">
          <div class="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
            <div>
              <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Name</label>
              <input v-model="editor.name" type="text" :readonly="!editor.isNew" maxlength="64"
                     placeholder="e.g. cup_stacking_lowlight"
                     class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-brand-500 outline-none read-only:opacity-60" />
            </div>
            <div>
              <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Type</label>
              <div class="mt-1 flex gap-1 p-1 rounded-lg bg-white/5 border border-white/10">
                <button v-for="k in KINDS" :key="k.value" @click="editor.kind = k.value"
                        :class="[
                          'flex-1 px-3 py-1.5 rounded-md text-[10px] font-black uppercase tracking-widest transition-all',
                          editor.kind === k.value ? 'bg-brand-500 text-white' : 'text-gray-500 hover:text-white'
                        ]">
                  {{ k.label }}
                </button>
              </div>
            </div>
            <div>
              <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Episodes</label>
              <input v-model="editor.eval_rounds" type="number" min="1" step="1" :placeholder="`default (${settings?.eval_rounds ?? '…'})`"
                     class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-brand-500 outline-none" />
            </div>
            <div>
              <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Episode length (s)</label>
              <input v-model="editor.episode_length_s" type="number" min="1" step="any" :placeholder="`default (${settings?.episode_length_s ?? '…'})`"
                     class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-brand-500 outline-none" />
            </div>
          </div>

          <div>
            <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Description</label>
            <input v-model="editor.description" type="text" maxlength="300" placeholder="Optional — shown in the task list"
                   class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:border-brand-500 outline-none" />
          </div>

          <div v-if="editor.kind === 'builtin'">
            <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Gym id</label>
            <input v-model="editor.gym_id" type="text" placeholder="HCIS-CupStacking-SingleArm-v0"
                   class="mt-1 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-brand-500 outline-none" />
          </div>

          <div v-else>
            <div class="flex items-center justify-between gap-3 mb-1 flex-wrap">
              <label class="text-[10px] font-black text-gray-500 uppercase tracking-widest">Eval config (.py)</label>
              <label class="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-[10px] font-black text-gray-300 uppercase tracking-widest hover:text-white cursor-pointer">
                Load .py file
                <input type="file" accept=".py,text/x-python" class="hidden" @change="loadPyFile" />
              </label>
            </div>
            <textarea v-model="editor.content" spellcheck="false" rows="18"
                      placeholder="# paste the eval config here, or load a .py file"
                      class="w-full bg-surface-950 border border-white/10 rounded-xl px-4 py-3 text-xs text-gray-200 font-mono leading-relaxed focus:border-brand-500 outline-none"></textarea>
            <div class="text-[10px] text-gray-600 font-mono mt-1">
              {{ contentStats.lines }} lines · {{ contentStats.kb }} KB (max 1 MB) · syntax checked on save
            </div>
          </div>

          <div v-if="editorError" class="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs">{{ editorError }}</div>

          <div class="flex gap-2">
            <button @click="saveEditor" :disabled="saving || !editor.name"
                    class="px-5 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-xs font-black text-white uppercase tracking-widest">
              {{ saving ? 'Saving…' : 'Save task' }}
            </button>
            <button @click="editor = null"
                    class="px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-xs font-black text-gray-300 uppercase tracking-widest hover:text-white">
              Cancel
            </button>
          </div>
        </div>
      </div>

      <!-- Task list -->
      <div class="glass-card p-6">
        <div class="flex items-start justify-between gap-4 flex-wrap mb-6">
          <div>
            <h3 class="text-sm font-black text-white uppercase tracking-widest flex items-center gap-2">
              <span class="w-2 h-2 rounded-full bg-brand-500"></span> Task Configurations
            </h3>
            <p class="text-xs text-gray-500 mt-2 max-w-2xl">
              Each run evaluates one task. A task can override the episode count and length from
              Settings; a single run can override them again when it's queued.
              Deleting a task keeps the results of runs that used it.
            </p>
          </div>
          <span class="text-[10px] font-black text-gray-400 uppercase tracking-widest bg-white/5 px-4 py-2 rounded-xl border border-white/5">
            {{ tasks.length }} tasks
          </span>
        </div>

        <div v-if="loading" class="text-center py-8 text-sm text-gray-500">Loading...</div>
        <div v-else-if="!tasks.length" class="text-center py-12 text-gray-600 italic text-sm">No tasks — add one to start evaluating.</div>
        <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div v-for="t in tasks" :key="t.name" class="rounded-2xl border border-white/10 bg-surface-900 p-5">
            <div class="flex items-center gap-3 mb-3 flex-wrap">
              <span class="text-sm font-black text-white">{{ taskLabel(t.name) }}</span>
              <span class="text-[10px] font-mono text-gray-500">{{ t.name }}</span>
              <span :class="[
                'px-2 py-0.5 rounded-md text-[10px] font-black uppercase ml-auto',
                t.kind === 'builtin' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-brand-500/20 text-brand-400'
              ]">
                {{ t.kind === 'builtin' ? 'built-in' : 'eval config' }}
              </span>
            </div>
            <p v-if="t.description" class="text-xs text-gray-400 mb-3">{{ t.description }}</p>
            <div class="bg-white/5 rounded-lg px-3 py-2 text-xs font-mono text-gray-300 mb-3 truncate">
              {{ t.kind === 'builtin' ? t.gym_id : `${t.name}_eval.py` }}
            </div>
            <div class="flex items-center gap-2 flex-wrap text-[10px]">
              <span class="px-1.5 py-0.5 rounded font-black uppercase tracking-wider"
                    :class="t.overrides?.eval_rounds != null ? 'bg-amber-500/20 text-amber-300' : 'bg-white/5 text-gray-500'">
                {{ effective(t).eval_rounds }} episodes
              </span>
              <span class="px-1.5 py-0.5 rounded font-black uppercase tracking-wider"
                    :class="t.overrides?.episode_length_s != null ? 'bg-amber-500/20 text-amber-300' : 'bg-white/5 text-gray-500'">
                {{ effective(t).episode_length_s }}s / episode
              </span>
              <span class="text-gray-600" v-if="t.updated_at">· updated {{ formatLocalCompact(t.updated_at) }}</span>
              <div class="ml-auto flex gap-3">
                <button @click="editTask(t)" class="text-brand-400 hover:text-brand-300 font-black uppercase tracking-widest">edit</button>
                <button @click="removeTask(t)" class="text-red-400 hover:text-red-300 font-black uppercase tracking-widest">delete</button>
              </div>
            </div>
          </div>
        </div>
        <p class="text-[10px] text-gray-600 mt-4">
          <span class="text-amber-300">Amber</span> values are set on the task; grey ones come from Settings.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { listTasks, getTask, saveTask, deleteTask, getSettings, errorText } from '../api'
import { useUiStore } from '../stores/ui'
import { formatLocalCompact } from '../utils/datetime'
import { taskLabel } from '../utils/format'

const KINDS = [
  { value: 'config', label: 'Eval .py' },
  { value: 'builtin', label: 'Gym id' },
]

const ui = useUiStore()

const tasks = ref([])
const settings = ref(null)
const loading = ref(true)

const editor = ref(null)
const editorEl = ref(null)
const editorError = ref('')
const saving = ref(false)

const contentStats = computed(() => {
  const c = editor.value?.content || ''
  return { lines: c.split('\n').length, kb: (new Blob([c]).size / 1024).toFixed(1) }
})

function effective(t) {
  return {
    eval_rounds: t.overrides?.eval_rounds ?? settings.value?.eval_rounds ?? '…',
    episode_length_s: t.overrides?.episode_length_s ?? settings.value?.episode_length_s ?? '…',
  }
}

async function fetchTasks() {
  try {
    const [t, s] = await Promise.all([listTasks(), getSettings()])
    tasks.value = t.data
    settings.value = s.data
  } catch (err) {
    ui.toast(errorText(err, 'Failed to load tasks'), 'error')
  } finally {
    loading.value = false
  }
}

async function openEditor(task) {
  editorError.value = ''
  editor.value = {
    isNew: !task,
    name: task?.name || '',
    kind: task?.kind || 'config',
    description: task?.description || '',
    gym_id: task?.gym_id || '',
    content: task?.content || '',
    eval_rounds: task?.overrides?.eval_rounds ?? '',
    episode_length_s: task?.overrides?.episode_length_s ?? '',
  }
  await nextTick()
  editorEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function editTask(t) {
  try {
    openEditor((await getTask(t.name)).data)
  } catch (err) {
    ui.toast(errorText(err), 'error')
  }
}

async function loadPyFile(e) {
  const f = e.target.files[0]
  e.target.value = ''
  if (!f) return
  editor.value.content = await f.text()
  if (editor.value.isNew && !editor.value.name) {
    editor.value.name = f.name.replace(/(_eval)?\.py$/i, '').replace(/[^A-Za-z0-9_.-]/g, '_')
  }
}

async function saveEditor() {
  const e = editor.value
  editorError.value = ''
  saving.value = true
  const builtin = e.kind === 'builtin'
  try {
    await saveTask(e.name.trim(), {
      gym_id: builtin ? e.gym_id : null,
      content: builtin ? null : e.content,
      description: e.description || null,
      overrides: { eval_rounds: e.eval_rounds, episode_length_s: e.episode_length_s },
    })
    ui.toast(`Task "${e.name}" saved`)
    editor.value = null
    fetchTasks()
  } catch (err) {
    editorError.value = errorText(err, 'Save failed')
  } finally {
    saving.value = false
  }
}

async function removeTask(t) {
  const ok = await ui.confirm({
    title: `Delete task "${t.name}"?`,
    message: 'Runs already evaluated on it keep their results. Queued runs for this task will fail.',
    danger: true,
    acceptLabel: 'Delete',
  })
  if (!ok) return
  try {
    await deleteTask(t.name)
    ui.toast(`Task "${t.name}" deleted`)
    if (editor.value?.name === t.name) editor.value = null
    fetchTasks()
  } catch (err) {
    ui.toast(errorText(err), 'error')
  }
}

onMounted(fetchTasks)
</script>
