import path from "node:path";
import { defineConfig } from "vitest/config";

// Manual alias (not the tsconfig-paths plugin — one new devDependency
// (vitest) is enough to flag for sign-off per VISION.md; this mirrors
// tsconfig.json's `"@/*": ["./*"]` without adding a second package).
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname),
    },
  },
  test: {
    environment: "node",
  },
});
