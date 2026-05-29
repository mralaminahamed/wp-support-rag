// Author: Al Amin Ahamed
import path from "path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    host: "0.0.0.0",
    port: 5174,
    // Dev convenience: proxy API calls to the backend so the browser stays same-origin.
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});
