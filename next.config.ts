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
  // HSTS is the only security header currently in place (added by Vercel for
  // the custom domain, not by this file) — these four are the site's own.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
