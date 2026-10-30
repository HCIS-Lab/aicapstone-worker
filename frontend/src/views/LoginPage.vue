<template>
  <div class="max-w-md mx-auto px-6 py-24">
    <div class="glass-card p-10 shadow-2xl">
      <div class="text-center mb-8">
        <div class="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-brand-500 to-purple-500 flex items-center justify-center shadow-lg shadow-brand-500/20 mb-6">
          <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>
        <h1 class="text-3xl font-bold text-white mb-2">Worker Login</h1>
        <p class="text-gray-400">Access this school's evaluation worker</p>
      </div>

      <form @submit.prevent="handleLogin" class="space-y-6">
        <div>
          <label class="block text-sm font-medium text-gray-400 mb-2">Admin Password</label>
          <input v-model="password" type="password" class="input-field" placeholder="Enter password"
                 required autofocus id="login-password" autocomplete="current-password" />
        </div>

        <button type="submit" :disabled="isSubmitting"
                class="w-full btn-primary py-4 text-lg flex items-center justify-center gap-3">
          <svg v-if="isSubmitting" class="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
          </svg>
          {{ isSubmitting ? 'Authenticating...' : 'Sign In' }}
        </button>

        <div v-if="errorMsg" class="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-sm text-center">
          {{ errorMsg }}
        </div>
      </form>

      <div class="mt-8 pt-8 border-t border-white/5 text-center">
        <p class="text-gray-500 text-xs">
          The password is <span class="font-mono text-gray-400">WORKER_ADMIN_PASSWORD</span> in this worker's
          <span class="font-mono text-gray-400">.env</span>,
          <br />or printed by <span class="font-mono text-gray-400">./setup.sh</span> when it finished.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { errorText } from '../api'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const password = ref('')
const isSubmitting = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  isSubmitting.value = true
  errorMsg.value = ''
  try {
    await auth.login(password.value)
    router.push(route.query.redirect || '/runs')
  } catch (err) {
    errorMsg.value = err.response?.status === 401
      ? 'Wrong password.'
      : errorText(err, 'Login failed.')
  } finally {
    isSubmitting.value = false
  }
}
</script>
