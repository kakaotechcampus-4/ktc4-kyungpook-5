import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // '@/shared/api/client' 처럼 src 기준 절대경로로 import 한다.
    alias: { '@': path.resolve(__dirname, 'src') },
  },
})
