import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lock Turbopack's workspace root to this directory so it does not walk up
  // and trip on adjacent project markers (e.g. a sibling .venv on Vercel's
  // build cache restoration path). See:
  // https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopack#root-directory
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
