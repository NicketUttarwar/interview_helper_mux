import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: fileURLToPath(new URL("../src/interview_mux/web/static", import.meta.url)),
    emptyOutDir: true,
    assetsDir: "assets",
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/")) {
            return "react-vendor";
          }
          if (id.includes("node_modules/zod")) {
            return "zod-vendor";
          }
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
});
