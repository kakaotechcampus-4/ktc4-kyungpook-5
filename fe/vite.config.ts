import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Docker(Windows 바인드 마운트)에서는 파일 변경 이벤트가 오지 않아 폴링으로 감시한다.
    watch: process.env.VITE_USE_POLLING ? { usePolling: true, interval: 300 } : undefined,
  },
  resolve: {
    // '@/shared/api/client' 처럼 src 기준 절대경로로 import 한다.
    alias: { '@': path.resolve(__dirname, 'src') },
  },
})
