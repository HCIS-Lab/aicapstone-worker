import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMe, getMyStats, login as apiLogin, logout as apiLogout } from '../api'

// One login form for both roles: `admin` (WORKER_ADMIN_PASSWORD) and the
// student groups the admin creates. The session lives in an HttpOnly
// cookie, so the store only remembers who we are.
export const useAuthStore = defineStore('auth', () => {
  const me = ref(null)
  const stats = ref(null)   // groups only: quota, best score, rank
  const checked = ref(false)

  const isAuthenticated = computed(() => !!me.value)
  const isAdmin = computed(() => !!me.value?.is_admin)
  const home = computed(() => (isAdmin.value ? '/admin/runs' : '/leaderboard'))

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

  async function refreshStats() {
    if (!me.value || me.value.is_admin) return
    try {
      stats.value = (await getMyStats()).data
    } catch { /* navbar only */ }
  }

  async function login(username, password) {
    await apiLogin(username, password)
    return refresh()
  }

  async function logout() {
    try { await apiLogout() } catch { /* session already gone */ }
    clear()
  }

  function clear() {
    me.value = null
    stats.value = null
  }

  return { me, stats, checked, isAuthenticated, isAdmin, home, refresh, refreshStats, login, logout, clear }
})
