import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: '..', // one .env at the repo root (VITE_N8N_WEBHOOK_URL lives there)
})
