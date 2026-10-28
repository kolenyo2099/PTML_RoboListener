import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const BACKEND = `http://127.0.0.1:${process.env.BACKEND_PORT || "8000"}`;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api":      { target: BACKEND, changeOrigin: true },
      "/monitor":  { target: BACKEND, changeOrigin: true },
      "/status":   { target: BACKEND, changeOrigin: true },
      "/keywords": { target: BACKEND, changeOrigin: true },
      "/pipeline": { target: BACKEND, changeOrigin: true },
      "/alerts":   { target: BACKEND, changeOrigin: true },
      "/hardware": { target: BACKEND, changeOrigin: true },
      "/ws":       { target: BACKEND, changeOrigin: true, ws: true },
    },
  },
});
