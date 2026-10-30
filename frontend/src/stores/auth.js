import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMe, login as apiLogin, logout as apiLogout } from '../api'

// The worker has one admin login (WORKER_ADMIN_PASSWORD); the session
// lives in an HttpOnly cookie, so the store only remembers who we are.
export const useAuthStore = defineStore('auth', () => {
  const me = ref(null)
  const checked = ref(false)

  const isAuthenticated = computed(() => !!me.value)

  async function refresh() {
    try {
      me.value = (await getMe()).data
    } catch {
      me.value = null
    } finally {
      checked.value = true
    }
    return me.value
  }

  async function login(password) {
    await apiLogin(password)
    return refresh()
  }

  async function logout() {
    try { await apiLogout() } catch { /* session already gone */ }
    me.value = null
  }

  function clear() {
    me.value = null
  }

  return { me, checked, isAuthenticated, refresh, login, logout, clear }
})
