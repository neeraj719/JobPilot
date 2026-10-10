import { fileURLToPath, URL } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const BACKEND_URL = process.env.VITE_DEV_BACKEND_URL ?? 'http://localhost:8000'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': { target: BACKEND_URL, changeOrigin: true },
      '/demo-ats': { target: BACKEND_URL, changeOrigin: true },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': { target: BACKEND_URL, changeOrigin: true },
      '/demo-ats': { target: BACKEND_URL, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
        },
      },
    },
  },
})
