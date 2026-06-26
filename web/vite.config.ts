import { defineConfig } from "vite";

// Dev server proxies /api to the FastAPI serving layer (gie.serving over DuckDB).
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8077",
    },
  },
});
