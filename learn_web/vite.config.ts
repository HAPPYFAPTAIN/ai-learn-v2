import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss()],
  // Prebundle the lazy PDF reader before navigation so its first import does
  // not restart the dev page and discard an open preview or unsaved draft.
  optimizeDeps: { include: ["pdfjs-dist/legacy/build/pdf.mjs"] },
  base:
    mode === "production"
      ? process.env.LEARN_WEB_BASE || "/official/learn-everything/app/"
      : "/",
  define: { __DEMO__: JSON.stringify(mode === "demo") },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api/v2": { target: "http://127.0.0.1:8000", changeOrigin: false },
      "/official-api": {
        target: "http://127.0.0.1:18030",
        changeOrigin: false,
      },
    },
  },
}));
