import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 官网线上挂在 /official/learn-everything/app/ 下，dev 用根路径，build 用同一 base。
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "production" ? "/official/learn-everything/app/" : "/",
  server: {
    port: 5173,
    proxy: {
      "/api/v2": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
}));
