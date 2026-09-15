import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发期 /api 代理到 FastAPI（:8000），前端不配置任何绝对后端地址
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
