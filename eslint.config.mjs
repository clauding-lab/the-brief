import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Non-source trees that ESLint should never parse. The Python venv and the
    // docs/ tree carry vendored / generated JS that produced 32 spurious lint
    // errors and made `npm run lint` exit 1 (unusable as a gate).
    ".venv/**",
    "docs/**",
    // Agent worktrees (git worktree checkouts under .claude/worktrees/) are
    // whole nested repo copies — linting them re-reports every historical
    // finding and breaks `npm run lint` as a local gate. Absent in CI.
    ".claude/**",
    // Same for `.worktrees/` (already in .gitignore) — a worktree's `.next/`
    // build output is not covered by the root-level ".next/**" ignore above.
    ".worktrees/**",
  ]),
]);

export default eslintConfig;
