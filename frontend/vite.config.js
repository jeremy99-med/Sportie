import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // File events don't cross the Docker bind mount on macOS, so poll instead.
    watch: {
      usePolling: true,
      interval: 300,
    },
    // Send API calls to Django through this origin so session cookies and CSRF work
    // without CORS. Docker sets the target to the backend service.
    proxy: {
      "/api": process.env.VITE_API_TARGET || "http://localhost:8000",
    },
  },
});
