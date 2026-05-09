/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import path from "path";

// Vitest-konfiguration. Vi bruger jsdom som test-environment fordi flere
// af vores komponenter rør window/document (toast, downloads, fetch).
//
// Path-aliaset @/* matcher tsconfig.json så imports virker identisk i
// tests og prod-kode.
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}", "tests/**/*.test.{ts,tsx}"],
    // Eksklusion er IKKE nødvendig i normalt brug, men vi sikrer at
    // vitest ikke tager hånd om Next.js' egne build-artefakter.
    exclude: ["node_modules", ".next"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
