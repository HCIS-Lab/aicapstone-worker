import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'

// Groups: /leaderboard (submit there) and /status/:id for their own runs.
// Admin: everything under /admin. Both sign in on /login.
const routes = [
  { path: '/', name: 'Home', redirect: () => useAuthStore().home },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginPage.vue'),
  },
  {
    path: '/leaderboard',
    name: 'Leaderboard',
    component: () => import('../views/LeaderboardPage.vue'),
    meta: { role: 'group' },
  },
  {
    path: '/status/:id',
    name: 'Status',
    component: () => import('../views/StatusPage.vue'),
    props: true,
    meta: { role: 'group' },
  },
  {
    path: '/admin/runs',
    name: 'Runs',
    component: () => import('../views/RunsPage.vue'),
    meta: { role: 'admin' },
  },
  {
    path: '/admin/runs/:id',
    name: 'Run',
    component: () => import('../views/RunPage.vue'),
    props: true,
    meta: { role: 'admin' },
  },
  {
    path: '/admin/groups',
    name: 'Groups',
    component: () => import('../views/GroupsPage.vue'),
    meta: { role: 'admin' },
  },
  {
    path: '/admin/tasks',
    name: 'Tasks',
    component: () => import('../views/TasksPage.vue'),
    meta: { role: 'admin' },
  },
  {
    path: '/admin/settings',
    name: 'Settings',
    component: () => import('../views/SettingsPage.vue'),
    meta: { role: 'admin' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.checked) await auth.refresh()

  if (to.name === 'Login') {
    return auth.isAuthenticated ? auth.home : true
  }
  if (!auth.isAuthenticated) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  // Each role stays on its own pages; the API enforces the same split.
  const role = auth.isAdmin ? 'admin' : 'group'
  if (to.meta.role && to.meta.role !== role) return auth.home
  return true
})

export default router
