import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/data.json": "http://127.0.0.1:8091",
      "/api": "http://127.0.0.1:8091",
      "/login": "http://127.0.0.1:8091",
      "/health": "http://127.0.0.1:8091",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
