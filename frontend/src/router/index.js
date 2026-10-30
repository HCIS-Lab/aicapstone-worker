import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/', redirect: '/runs' },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/LoginPage.vue'),
  },
  {
    path: '/runs',
    name: 'Runs',
    component: () => import('../views/RunsPage.vue'),
  },
  {
    path: '/runs/:id',
    name: 'Run',
    component: () => import('../views/RunPage.vue'),
    props: true,
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: () => import('../views/TasksPage.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsPage.vue'),
  },
  { path: '/:pathMatch(.*)*', redirect: '/runs' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Everything except /login needs the session.
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.checked) await auth.refresh()

  if (to.name === 'Login') {
    return auth.isAuthenticated ? { name: 'Runs' } : true
  }
  if (!auth.isAuthenticated) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
