<template>
  <div class="max-w-[1600px] mx-auto px-6 py-12 relative min-h-screen pb-20">
    <!-- Header -->
    <div class="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
      <div>
        <h1 class="text-5xl font-black text-white mb-3 tracking-tight">Groups</h1>
        <p class="text-gray-400 text-lg">Student accounts: they sign in on the same login page and submit from the leaderboard</p>
      </div>
      <button @click="fetchUsers()" class="btn-secondary text-sm">Refresh</button>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-8">
      <!-- Add groups -->
      <div class="glass-card p-6 h-fit">
        <h3 class="text-sm font-black text-white uppercase tracking-widest mb-1 flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-brand-500"></span> Add Groups
        </h3>
        <p class="text-[11px] text-gray-500 mb-5">
          One group per line. <span class="font-mono text-gray-400">name</span> gets a generated password;
          <span class="font-mono text-gray-400">name,password</span> sets it (6+ characters).
        </p>

        <label class="block text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2">Groups</label>
        <textarea v-model="bulk" rows="6" spellcheck="false" placeholder="Group 1&#10;Group 2&#10;Group 3,their-password"
                  class="w-full bg-surface-950 border border-white/10 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-brand-500 outline-none mb-4"></textarea>

        <label class="block text-[10px] font-black text-gray-500 uppercase tracking-widest mb-2">Assigned task</label>
        <select v-model="bulkTask"
                class="w-full bg-surface-950 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:border-brand-500 outline-none mb-5">
          <option value="">Any task (group chooses)</option>
          <option v-for="t in tasks" :key="t.name" :value="t.name">{{ taskLabel(t.name) }}</option>
        </select>

        <button @click="addGroups" :disabled="adding || !bulkLines.length"
                class="w-full px-5 py-3 rounded-xl bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-xs font-black text-white uppercase tracking-widest">
          {{ adding ? 'Creating…' : `Create ${bulkLines.length || ''} group${bulkLines.length === 1 ? '' : 's'}` }}
        </button>

        <!-- Credentials just issued -->
        <div v-if="issued.length" class="mt-6 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
          <div class="flex items-center justify-between mb-3">
            <div class="text-[10px] font-black text-emerald-400 uppercase tracking-widest">Credentials — shown once</div>
            <div class="flex gap-3">
              <button @click="copyIssued" class="text-[10px] font-black text-emerald-300 uppercase tracking-widest hover:text-white">{{ copied ? 'Copied' : 'Copy CSV' }}</button>
              <button @click="issued = []" class="text-[10px] font-black text-gray-500 uppercase tracking-widest hover:text-white">Clear</button>
            </div>
          </div>
          <table class="w-full text-xs font-mono">
            <tr v-for="c in issued" :key="c.username">
              <td class="py-1 pr-3 text-white">{{ c.username }}</td>
              <td class="py-1 text-emerald-300 select-all">{{ c.password }}</td>
            </tr>
          </table>
          <p class="text-[10px] text-gray-500 mt-3">Passwords are stored hashed; to give a new one later, use Reset.</p>
        </div>
        <div v-if="addErrors.length" class="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-xs space-y-1">
          <div v-for="e in addErrors" :key="e">{{ e }}</div>
        </div>
      </div>

      <!-- Group list -->
      <div class="glass-card overflow-hidden xl:col-span-2">
        <div class="px-6 py-4 border-b border-white/5 flex items-center justify-between">
          <h3 class="text-sm font-black text-white uppercase tracking-widest flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-brand-500"></span> {{ users.length }} Groups
          </h3>
          <span class="text-[10px] font-black text-gray-500 uppercase tracking-widest">
            Quota: {{ quota ? `${quota} / 24 h` : 'unlimited' }} · <router-link to="/admin/settings" class="text-brand-400 hover:text-brand-300">change</router-link>
          </span>
        </div>
        <table class="w-full">
          <thead class="bg-white/2">
            <tr>
              <th class="px-4 py-3 text-left text-[10px] font-black text-gray-500 uppercase tracking-widest">Group</th>
              <th class="px-4 py-3 text-left text-[10px] font-black text-gray-500 uppercase tracking-widest">Assigned task</th>
              <th class="px-4 py-3 text-center text-[10px] font-black text-gray-500 uppercase tracking-widest">Today</th>
              <th class="px-4 py-3 text-center text-[10px] font-black text-gray-500 uppercase tracking-widest">Total</th>
              <th class="px-4 py-3 text-center text-[10px] font-black text-gray-500 uppercase tracking-widest">Best</th>
              <th class="px-4 py-3 text-left text-[10px] font-black text-gray-500 uppercase tracking-widest">Last submission</th>
              <th class="px-4 py-3 text-right text-[10px] font-black text-gray-500 uppercase tracking-widest">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-white/[0.03]">
            <tr v-if="!users.length">
              <td colspan="7" class="px-4 py-12 text-center text-gray-600 italic text-sm">
                {{ loading ? 'Loading…' : 'No groups yet. Add them on the left; students then sign in with those names.' }}
              </td>
            </tr>
            <tr v-for="u in users" :key="u.id" class="hover:bg-white/[0.02]">
              <td class="px-4 py-3 text-white font-bold text-sm">{{ u.username }}</td>
              <td class="px-4 py-3">
                <select :value="u.assigned_task || ''" @change="changeTask(u, $event.target.value)"
                        class="bg-surface-950 border border-white/10 rounded-lg px-2 py-1 text-xs text-gray-200 focus:border-brand-500 outline-none">
                  <option value="">Any task</option>
                  <option v-for="t in tasks" :key="t.name" :value="t.name">{{ taskLabel(t.name) }}</option>
                </select>
              </td>
              <td class="px-4 py-3 text-center font-mono text-xs"
                  :class="quota && u.submissions_today >= quota ? 'text-red-400' : 'text-gray-300'">
                {{ u.submissions_today }}<span v-if="quota" class="text-gray-600">/{{ quota }}</span>
              </td>
              <td class="px-4 py-3 text-center font-mono text-xs text-gray-300">{{ u.submissions }}</td>
              <td class="px-4 py-3 text-center font-mono text-sm font-black"
                  :class="u.best_score != null ? 'text-white' : 'text-gray-700'">{{ formatRate(u.best_score) }}</td>
              <td class="px-4 py-3 text-xs text-gray-400">{{ u.last_submission ? formatLocal(u.last_submission) : '—' }}</td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <router-link :to="{ path: '/admin/runs', query: { q: u.username } }"
                             class="px-2.5 py-1 rounded-lg bg-white/5 border border-white/5 text-[10px] font-black text-gray-400 hover:text-white uppercase tracking-widest mr-1">Runs</router-link>
                <button @click="resetPassword(u)"
                        class="px-2.5 py-1 rounded-lg bg-white/5 border border-white/5 text-[10px] font-black text-amber-300 hover:text-white uppercase tracking-widest mr-1">Reset</button>
                <button @click="removeUser(u)"
                        class="px-2.5 py-1 rounded-lg bg-white/5 border border-white/5 text-[10px] font-black text-red-400 hover:text-white uppercase tracking-widest">Delete</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  listUsers, createUser, updateUser, deleteUser, listTasks, getSettings, errorText,
} from '../api'
import { useUiStore } from '../stores/ui'
import { formatLocal } from '../utils/datetime'
import { formatRate, taskLabel } from '../utils/format'

const ui = useUiStore()

const users = ref([])
const tasks = ref([])
const quota = ref(0)
const loading = ref(true)

const bulk = ref('')
const bulkTask = ref('')
const adding = ref(false)
const issued = ref([])
const addErrors = ref([])
const copied = ref(false)

const bulkLines = computed(() =>
  bulk.value.split('\n').map(l => l.trim()).filter(Boolean))

async function fetchUsers() {
  try {
    users.value = (await listUsers()).data
  } catch (err) {
    ui.toast(errorText(err, 'Failed to load groups'), 'error')
  } finally {
    loading.value = false
  }
}

async function addGroups() {
  adding.value = true
  addErrors.value = []
  const failed = []
  for (const line of bulkLines.value) {
    const i = line.indexOf(',')
    const username = (i < 0 ? line : line.slice(0, i)).trim()
    const password = i < 0 ? '' : line.slice(i + 1).trim()
    try {
      const { data } = await createUser({ username, password: password || null, assigned_task: bulkTask.value || null })
      issued.value.push({ username: data.username, password: data.password })
    } catch (err) {
      addErrors.value.push(`${username}: ${errorText(err)}`)
      failed.push(line)
    }
  }
  bulk.value = failed.join('\n')  // keep only what still needs fixing
  adding.value = false
  fetchUsers()
}

async function copyIssued() {
  const csv = ['group,password', ...issued.value.map(c => `${c.username},${c.password}`)].join('\n')
  try {
    await navigator.clipboard.writeText(csv)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch {
    ui.toast('Clipboard not available; select the table instead', 'error')
  }
}

async function changeTask(u, task) {
  try {
    await updateUser(u.id, { assigned_task: task || null })
    u.assigned_task = task || null
    ui.toast(`${u.username} → ${task ? taskLabel(task) : 'any task'}`)
  } catch (err) {
    ui.toast(errorText(err, 'Update failed'), 'error')
    fetchUsers()
  }
}

function newPassword() {
  const alphabet = 'abcdefghijkmnpqrstuvwxyzACDEFGHJKLMNPQRSTUVWXYZ23456789'
  const bytes = crypto.getRandomValues(new Uint8Array(10))
  return Array.from(bytes, b => alphabet[b % alphabet.length]).join('')
}

async function resetPassword(u) {
  const ok = await ui.confirm({
    title: `Reset password for ${u.username}?`,
    message: 'A new password is generated and shown once. The group is signed out everywhere.',
    acceptLabel: 'Reset',
  })
  if (!ok) return
  const password = newPassword()
  try {
    await updateUser(u.id, { password })
    issued.value = [...issued.value.filter(c => c.username !== u.username), { username: u.username, password }]
    ui.toast(`New password for ${u.username} is in the credentials box`)
  } catch (err) {
    ui.toast(errorText(err, 'Reset failed'), 'error')
  }
}

async function removeUser(u) {
  const ok = await ui.confirm({
    title: `Delete group ${u.username}?`,
    message: 'The group can no longer sign in and leaves the leaderboard.',
    bullets: [`Its ${u.submissions} run(s) stay in Runs, under the name "${u.username}".`],
    danger: true,
    acceptLabel: 'Delete group',
  })
  if (!ok) return
  try {
    await deleteUser(u.id)
    ui.toast(`${u.username} deleted`)
    fetchUsers()
  } catch (err) {
    ui.toast(errorText(err, 'Delete failed'), 'error')
  }
}

onMounted(async () => {
  fetchUsers()
  try {
    const [t, s] = await Promise.all([listTasks(), getSettings()])
    tasks.value = t.data
    quota.value = s.data.daily_quota || 0
  } catch { /* table still works */ }
})
</script>
