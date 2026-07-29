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
    server: {
      port: 5173,
      // The API runs on the host; proxying keeps the browser same-origin so no CORS config is needed.
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
        },
        // n8n is no longer proxied here. GET /n8n/workflows and /n8n/executions
        // on the API attach X-N8N-API-KEY server-side and sit behind the session
        // gate, so the panels also work from a static build (where no dev server
        // exists to hold the key).
      },
    },
  }
})
