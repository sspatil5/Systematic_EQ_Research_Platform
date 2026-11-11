import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: { rollupOptions: { output: { manualChunks(id) {
    if (/node_modules\/(recharts|d3-|victory|decimal\.js|@reduxjs|react-redux|immer|reselect)/.test(id)) return 'charts'
    if (/node_modules\/@tanstack/.test(id)) return 'tables'
    if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react'
  } } } },
  test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'], exclude: ['node_modules/**', 'e2e/**'] },
})
