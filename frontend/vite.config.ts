import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 시 VITE_API_BASE_URL을 비우면 `/api`가 Vite 프록시를 통해 백엔드로 전달됩니다.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // Windows: localhost → IPv6 [::1] 우선 시 Docker/WSL 등이 8000을 잡으면 404.
        // uvicorn은 보통 127.0.0.1:8000 에만 떠 있으므로 IPv4로 고정합니다.
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
