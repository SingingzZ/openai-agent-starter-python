import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * Local dev agent server (dev_server.py).
 *
 * Cloud (EdgeOne Makers) maps agents/chat/index.py to POST /chat automatically,
 * but locally there is no such runtime — hence `dev_server.py`, which speaks the
 * same protocol on this port. These proxies only apply to `npm run dev`; they
 * have no effect on the production build.
 */
const AGENT_SERVER = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/chat': { target: AGENT_SERVER, changeOrigin: true },
      '/stop': { target: AGENT_SERVER, changeOrigin: true },
      '/history': { target: AGENT_SERVER, changeOrigin: true },
      '/conversations': { target: AGENT_SERVER, changeOrigin: true },
      '/clear-history': { target: AGENT_SERVER, changeOrigin: true },
      '/delete-conversation': { target: AGENT_SERVER, changeOrigin: true },
    },
  },
})
