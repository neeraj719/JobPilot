import { fileURLToPath, URL } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

const BACKEND_URL = process.env.VITE_DEV_BACKEND_URL ?? 'http://localhost:8000'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // PWA baseline (installable web app / APK wrapper): the manifest is the hand-written
    // public/manifest.webmanifest; the service worker precaches the app shell and static
    // assets only and NEVER caches the API. Off in dev.
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'script-defer',
      manifest: false,
      devOptions: { enabled: false },
      workbox: {
        // App shell only: the HTML, the entry chunks and styles, fonts and icons (~0.9 MB).
        // Lazy page chunks are cached on first use (hashed, so cache-first is safe); the
        // three.js scene and marketing images are never precached.
        globPatterns: ['index.html', 'assets/index-*.{js,css}', 'assets/{react,ui}-*.js', 'fonts/{InterVariable-latin,BricolageGrotesque-Variable}.woff2', 'favicon.svg', 'icons/*.png', 'manifest.webmanifest'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/demo-ats\//],
        runtimeCaching: [
          { urlPattern: /\/api\//, handler: 'NetworkOnly' },
          {
            urlPattern: /\/assets\/(?!HeroScene-).*\.(?:js|css)$/,
            handler: 'CacheFirst',
            options: { cacheName: 'jobpilot-chunks', expiration: { maxEntries: 60, maxAgeSeconds: 30 * 24 * 3600 } },
          },
        ],
        cleanupOutdatedCaches: true,
      },
    }),
  ],
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
        // A function, not the object form: `charts: ['recharts']` also claims every package
        // recharts depends on (clsx among them, which `cn()` uses everywhere), so the main
        // bundle imported the whole charts chunk and the launcher downloaded recharts it never
        // renders. Only chart-specific packages go to `charts`; shared ones stay shared.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (/node_modules[\/](react|react-dom|react-router|react-router-dom|@remix-run[\/]router|scheduler)[\/]/.test(id)) {
            return 'react'
          }
          if (/node_modules[\/](recharts|recharts-scale|victory-vendor|d3-[^\/]+|internmap|decimal\.js-light)[\/]/.test(id)) {
            return 'charts'
          }
          // Motion (framer-motion) only ever loads with the lazy pages that animate numbers / rings.
          if (/node_modules[/](framer-motion|motion-dom|motion-utils)[/]/.test(id)) return 'motion'
          // Shared with recharts but used by every component through `cn()`: named explicitly,
          // or Rollup folds them into `charts` and the main bundle imports that chunk again.
          if (/node_modules[\/](clsx|tailwind-merge|class-variance-authority)[\/]/.test(id)) {
            return 'ui'
          }
          return undefined
        },
      },
    },
  },
})
