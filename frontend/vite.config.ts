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
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
