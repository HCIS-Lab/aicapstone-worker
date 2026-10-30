import axios from 'axios'

// Same-origin API; auth is the worker's HttpOnly session cookie, so no
// token handling here.
const api = axios.create({
  baseURL: '/api',
  timeout: 600000,
})

// 401 means the session expired (or the worker restarted, which drops
// all sessions). App.vue listens for this and sends the user to /login.
// /login and /me answer 401 as part of the normal flow, so they're exempt.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error?.config?.url || ''
    if (error?.response?.status === 401 && !['/login', '/me'].includes(url)) {
      window.dispatchEvent(new Event('auth:expired'))
    }
    return Promise.reject(error)
  },
)

/** FastAPI error → readable string. */
export function errorText(err, fallback = 'Request failed') {
  const d = err?.response?.data?.detail
  if (typeof d === 'string') return d
  if (d) return JSON.stringify(d)
  return err?.message || fallback
}

// Session
export const login = (password) => api.post('/login', { password })
export const logout = () => api.post('/logout')
export const getMe = () => api.get('/me')

// Settings
export const getSettings = () => api.get('/settings')
export const getDefaultSettings = () => api.get('/settings/defaults')
export const updateSettings = (body) => api.put('/settings', body)

// Tasks
export const listTasks = () => api.get('/tasks')
export const getTask = (name) => api.get(`/tasks/${encodeURIComponent(name)}`)
export const saveTask = (name, body) => api.put(`/tasks/${encodeURIComponent(name)}`, body)
export const deleteTask = (name) => api.delete(`/tasks/${encodeURIComponent(name)}`)

// Runs
export const listRuns = () => api.get('/runs')
export const getRun = (id) => api.get(`/runs/${id}`)
export const getRunLog = (id, tail = 1000) =>
  api.get(`/runs/${id}/log`, { params: { tail }, responseType: 'text', transformResponse: (d) => d })
export const rerunRun = (id) => api.post(`/runs/${id}/rerun`)
export const cancelRun = (id) => api.post(`/runs/${id}/cancel`)
export const deleteRun = (id) => api.delete(`/runs/${id}`)

/** Multipart upload; zips run to several GB, so no timeout. */
export const createRun = (formData, onProgress) =>
  api.post('/runs', formData, {
    timeout: 0,
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })

/** <video src>: the session cookie authenticates it. `v` busts the cache after a re-run. */
export const runVideoUrl = (id, v = '') => `/api/runs/${id}/video?v=${encodeURIComponent(v || '')}`

export default api
