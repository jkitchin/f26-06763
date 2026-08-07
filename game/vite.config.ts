import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The deployed path. NOT './': the app is served from a subdirectory of the
  // course site, and a relative base breaks the moment a route is nested.
  // CI greps the built index.html for this string, because a wrong base
  // produces a blank page with 404s on every asset while index.html still
  // exists, which every other check would happily pass.
  base: '/f26-06763/game/',
  build: { outDir: 'dist', emptyOutDir: true },
})
