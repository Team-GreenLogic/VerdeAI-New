import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',      // bind to all interfaces inside Docker
    allowedHosts: [
      'verdeai.duckdns.org',
      '44.215.55.218',
    ],
    watch: {
      usePolling: true,    // required for hot-reload inside Docker on macOS
    },
  },
})
