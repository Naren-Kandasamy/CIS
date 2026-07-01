import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',   // listen on all interfaces so both IPv4 and IPv6 work
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',  // force IPv4 to avoid ::1 refusal
        changeOrigin: true,
      }
    }
  }
})
