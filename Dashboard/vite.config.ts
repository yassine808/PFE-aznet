import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': path.resolve(__dirname, './src') },
    },
    build: {
      rollupOptions: {
        output: {
          // Stable vendor chunks: react/motion/phosphor rarely change, so the
          // immutable-cache header (nginx /assets/) keeps serving them from
          // the browser after a deploy. Page chunks come from the lazy()
          // splits in App.tsx; docx stays in the page chunk that uses it.
          manualChunks(id) {
            if (!id.includes('node_modules')) return
            // Phosphor first: its package path is `@phosphor-icons/react`, so a
            // bare `includes('react')` swallows the whole icon set into the
            // react chunk and the split does nothing.
            if (id.includes('@phosphor-icons')) return 'phosphor'
            if (id.includes('motion')) return 'motion'
            if (id.includes('react')) return 'react'
          },
        },
      },
    },
    server: {
      port: 5173,
      // Target the compose stack's nginx, not the API directly: the api service
      // publishes no host port on purpose (one public origin, see docker-compose.yml),
      // so 127.0.0.1:8000 refuses and every call 502s. nginx already maps
      // /api/ -> api:8000/, hence no rewrite here -- stripping the prefix would
      // land on the SPA's try_files and return index.html instead of JSON.
      // Proxying at all keeps the browser same-origin, so no CORS config is needed.
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8080',
          changeOrigin: true,
        },
        // n8n is no longer proxied here. GET /n8n/workflows and /n8n/executions
        // on the API attach X-N8N-API-KEY server-side and sit behind the session
        // gate, so the panels also work from a static build (where no dev server
        // exists to hold the key).
      },
    },
  }
})
