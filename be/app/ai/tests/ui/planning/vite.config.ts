import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // 로컬 AI API만 연결한다. 제품 fe/의 Vite 설정·라우트는 사용하지 않는다.
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: { '/__planning-test': 'http://127.0.0.1:8011' },
  },
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
})
