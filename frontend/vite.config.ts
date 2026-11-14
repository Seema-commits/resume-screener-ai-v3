/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API runs separately (uvicorn backend.main:app). In development and
// preview, /api is forwarded to it so the session cookie stays same-origin.
const api = { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false } }

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: api },
  preview: { proxy: api },
  test: {
    environment: 'jsdom', globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
