import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 시 VITE_API_BASE_URL을 비우면 `/api`가 Vite 프록시를 통해 백엔드로 전달됩니다.
// Docker Compose: VITE_DEV_PROXY_TARGET=http://host.docker.internal:8000 (브라우저는 여전히 호스트 localhost:8000 직접 호출 가능)
const proxyTarget =
  process.env.VITE_DEV_PROXY_TARGET?.trim() || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
});
