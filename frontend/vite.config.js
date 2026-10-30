import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// `npm run dev` proxies the API to a running worker; point it elsewhere
// with VITE_WORKER_URL (default: the first port setup.sh hands out).
const worker = process.env.VITE_WORKER_URL || 'http://localhost:8081'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy: {
      '/api': { target: worker, changeOrigin: true },
    },
  },
})
