import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the browser talks to this dev server and Vite forwards /api and /health to the FastAPI backend.
// That keeps requests same-origin (no CORS setup needed) and keeps the backend bound to 127.0.0.1.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.DEV_API_PROXY_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: { "/api": target, "/health": target },
    },
  };
});
