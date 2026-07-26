import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  // No VITE_ prefix on these: they must stay server-side and never be inlined
  // into the client bundle.
  const env = loadEnv(mode, process.cwd(), '')

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
        /*
         * n8n's public API needs X-N8N-API-KEY. The header is attached here, in the
         * dev server, so the key never reaches client JavaScript.
         *
         * ponytail: dev-proxy only, which is fine because the dashboard runs from
         * `npm run dev` on the admin's machine. If it is ever served as a static
         * build, move this to a FastAPI endpoint so the key still stays server-side.
         */
        '/n8n': {
          target: env.N8N_URL || 'http://127.0.0.1:5678',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/n8n/, ''),
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              if (env.N8N_API_KEY) proxyReq.setHeader('X-N8N-API-KEY', env.N8N_API_KEY)
            })
          },
        },
      },
    },
  }
})
