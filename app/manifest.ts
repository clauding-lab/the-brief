// PWA manifest (facelift spec §4.1, PR B). Next serves this at
// /manifest.webmanifest and injects <link rel="manifest"> automatically
// (Context7-verified against Next 16 docs). The 192/512 entries point at
// the EXISTING file-convention icon routes (app/icon.png, app/apple-icon.png)
// rather than duplicating files; only the maskable icon is a new asset —
// it must exist, because Chrome silently withholds the install prompt when
// a declared icon 404s. Installed app is ONLINE-ONLY in this pass (§4.4):
// the thebrief.lastBrief cache is write-only today, so there is no offline
// shell to serve — a minimal service worker is the queued follow-up.
import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "The Brief — Bangladesh business intelligence",
    short_name: "The Brief",
    description: "Daily macro & markets read for Bangladesh banking professionals.",
    start_url: "/",
    display: "standalone",
    background_color: "#0B0F12",
    theme_color: "#0B0F12",
    icons: [
      { src: "/icon.png", sizes: "192x192", type: "image/png" },
      { src: "/apple-icon.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
