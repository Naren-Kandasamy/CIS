import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  // BUG FIX: Catalyst serves the deployed client under /app/, but index.html's
  // asset tags were generated as root-absolute ("/assets/...") since base was
  // never set, causing every JS/CSS asset to 404 and the page to render blank.
  base: '/app/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
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
