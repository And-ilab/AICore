import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxyTarget =
    env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port: 5173,
      hmr: process.env.VITE_DISABLE_HMR === '1' ? false : undefined,
      // Docker Desktop on Windows often misses bind-mount file events without polling.
      watch:
        process.env.VITE_USE_POLLING === '1'
          ? { usePolling: true, interval: 1000 }
          : undefined,
      proxy: {
        '/api': apiProxyTarget,
        '/ws': {
          target: apiProxyTarget,
          ws: true,
          changeOrigin: true,
        },
      },
    },
  }
})
