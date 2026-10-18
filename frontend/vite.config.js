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
  },
});
