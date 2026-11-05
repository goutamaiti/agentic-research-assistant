import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The browser only ever talks to /api on the Vite origin; the dev server forwards it to
// FastAPI. BACKEND_URL is read here at config time and is never exposed to client code
// (only VITE_-prefixed variables reach the bundle, and none hold secrets).
const backendUrl = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: backendUrl, changeOrigin: true },
    },
  },
  test: {
    environment: 'node',
  },
})
