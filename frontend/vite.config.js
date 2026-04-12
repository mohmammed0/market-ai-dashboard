import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const devApiTarget = process.env.MARKET_AI_DEV_API_ORIGIN || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("/node_modules/")) {
            return undefined;
          }
          if (
            id.includes("/node_modules/react/")
            || id.includes("/node_modules/react-dom/")
            || id.includes("/node_modules/react-router-dom/")
          ) {
            return "react_vendor";
          }
          if (
            id.includes("/node_modules/react-hook-form/")
            || id.includes("/node_modules/@hookform/")
            || id.includes("/node_modules/zod/")
          ) {
            return "forms_vendor";
          }
          if (
            id.includes("/node_modules/echarts/")
            || id.includes("/node_modules/echarts-for-react/")
            || id.includes("/node_modules/zrender/")
          ) {
            return "charts_vendor";
          }
          if (id.includes("/node_modules/@tanstack/react-table/")) {
            return "table_vendor";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    host: true,
    port: Number(process.env.VITE_PORT || 5173),
    proxy: {
      "/api": devApiTarget,
      "/health": devApiTarget,
      "/ready": devApiTarget,
    },
  },
  preview: {
    host: true,
    port: Number(process.env.VITE_PREVIEW_PORT || 4173),
  },
});
