<template>
  <div class="min-h-screen bg-surface-900">
    <!-- Navigation -->
    <nav class="fixed top-0 left-0 right-0 z-50 glass-card border-t-0 rounded-t-none border-x-0">
      <div class="max-w-7xl mx-auto px-6 py-4">
        <div class="flex items-center justify-between">
          <!-- Logo -->
          <router-link to="/" class="flex items-center gap-3 group">
            <div class="w-10 h-10 rounded-xl bg-white/5 ring-1 ring-white/10 flex items-center justify-center overflow-hidden shadow-lg shadow-brand-500/10 group-hover:shadow-brand-500/30 transition-all duration-300">
              <img src="/hcis-lab.png" alt="HCIS Lab" class="w-full h-full object-contain" />
            </div>
            <span class="text-xl font-bold gradient-text tracking-tighter">Physical AI</span>
            <span class="hidden sm:inline text-[10px] font-black text-gray-500 uppercase tracking-widest mt-1">Eval Worker</span>
          </router-link>

          <!-- Nav Links -->
          <div class="flex items-center gap-1">
            <template v-if="auth.isAuthenticated">
              <router-link
                v-for="l in links" :key="l.to" :to="l.to"
                class="px-4 py-2 rounded-lg text-sm font-medium text-gray-400 hover:text-white hover:bg-white/5 transition-all duration-200"
                active-class="!text-white !bg-white/10"
              >
                {{ l.label }}
              </router-link>
            </template>

            <!-- Worker telemetry (persistent) -->
            <div v-if="auth.me" class="hidden md:flex items-center gap-6 ml-6 pl-6 border-l border-white/10">
              <div class="flex flex-col">
                <span class="text-[10px] text-gray-500 uppercase tracking-widest font-bold">Worker</span>
                <span class="text-white font-black leading-none mt-1 truncate max-w-[160px]">{{ auth.me.worker_name }}</span>
              </div>
              <div class="flex flex-col">
                <span class="text-[10px] text-gray-500 uppercase tracking-widest font-bold">GPU</span>
                <span class="text-white font-black leading-none mt-1 font-mono">{{ auth.me.gpu_id }}</span>
              </div>
              <div class="flex flex-col">
                <span class="text-[10px] text-gray-500 uppercase tracking-widest font-bold">Mode</span>
                <span class="font-black leading-none mt-1 uppercase"
                      :class="auth.me.eval_mode === 'real' ? 'text-emerald-400' : 'text-amber-400'">
                  {{ auth.me.eval_mode }}
                </span>
              </div>
            </div>

            <!-- Auth Section -->
            <div v-if="auth.isAuthenticated" class="flex items-center gap-2 ml-4 pl-4 border-l border-white/10">
              <span class="hidden lg:inline text-sm font-medium text-brand-300">admin</span>
              <button @click="handleLogout" class="p-2 rounded-lg text-gray-400 hover:text-red-400 hover:bg-red-400/5 transition-all duration-200" title="Logout">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </nav>

    <!-- Page content -->
    <main class="pt-20">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- Footer -->
    <footer class="border-t border-white/5 mt-20">
      <div class="max-w-7xl mx-auto px-6 py-8 flex items-center justify-between text-sm text-gray-500 font-medium">
        <span>© 2026 Physical AI Course Project Evaluation Platform</span>
        <span>Self-hosted Isaac Sim eval worker</span>
      </div>
    </footer>

    <!-- Confirmation modal (replaces native confirm() for destructive ops) -->
    <div v-if="ui.confirmState.open" class="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
         @click.self="ui.settleConfirm(false)">
      <div class="glass-card w-full max-w-lg p-7 border" :class="ui.confirmState.danger ? 'border-red-500/40' : 'border-white/10'">
        <h3 class="text-base font-black text-white mb-2 flex items-center gap-2">
          <span v-if="ui.confirmState.danger" class="text-red-400">⚠</span>{{ ui.confirmState.title }}
        </h3>
        <p class="text-sm text-gray-300 whitespace-pre-line">{{ ui.confirmState.message }}</p>
        <ul v-if="ui.confirmState.bullets?.length" class="mt-3 space-y-1.5 text-sm text-gray-400">
          <li v-for="(b, i) in ui.confirmState.bullets" :key="i">• {{ b }}</li>
        </ul>
        <div class="mt-7 flex gap-3 justify-end">
          <button @click="ui.settleConfirm(false)" class="px-5 py-2.5 rounded-xl bg-white/5 border border-white/10 text-gray-300 text-xs font-black uppercase tracking-widest hover:bg-white/10">Cancel</button>
          <button @click="ui.settleConfirm(true)"
                  class="px-5 py-2.5 rounded-xl text-white text-xs font-black uppercase tracking-widest"
                  :class="ui.confirmState.danger ? 'bg-red-500 hover:bg-red-600' : 'bg-brand-500 hover:bg-brand-600'">
            {{ ui.confirmState.acceptLabel }}
          </button>
        </div>
      </div>
    </div>

    <!-- Toasts -->
    <div v-if="ui.successMessage" class="fixed bottom-8 left-8 px-5 py-3 rounded-xl bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 text-sm font-bold flex items-center gap-3 z-[60] backdrop-blur-md">
      {{ ui.successMessage }}
      <button @click="ui.successMessage = ''" class="opacity-60 hover:opacity-100">✕</button>
    </div>
    <div v-if="ui.errorMessage" class="fixed bottom-8 left-8 px-5 py-3 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 text-sm font-bold flex items-center gap-3 z-[60] backdrop-blur-md">
      {{ ui.errorMessage }}
      <button @click="ui.errorMessage = ''" class="opacity-60 hover:opacity-100">✕</button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useUiStore } from './stores/ui'

const auth = useAuthStore()
const ui = useUiStore()
const router = useRouter()

const links = [
  { to: '/runs', label: 'Runs' },
  { to: '/tasks', label: 'Tasks' },
  { to: '/settings', label: 'Settings' },
]

function onExpired() {
  if (!auth.isAuthenticated) return
  auth.clear()
  router.push({ name: 'Login', query: { redirect: router.currentRoute.value.fullPath } })
}

function onKey(e) {
  if (e.key === 'Escape' && ui.confirmState.open) ui.settleConfirm(false)
}

onMounted(() => {
  window.addEventListener('auth:expired', onExpired)
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => {
  window.removeEventListener('auth:expired', onExpired)
  window.removeEventListener('keydown', onKey)
})

async function handleLogout() {
  await auth.logout()
  router.push({ name: 'Login' })
}
</script>

<style>
.page-enter-active,
.page-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
