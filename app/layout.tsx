import type { Metadata, Viewport } from "next";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["200", "300", "400", "500", "600"],
  variable: "--mono-font",
  display: "swap",
});

const SITE_URL = "https://thebrief.clauding-lab.com";
const SITE_TITLE = "The Brief — Bangladesh business intelligence";
const SITE_DESCRIPTION =
  "Daily macro & markets read for Bangladesh banking professionals. Numbers, news, and a banker's read on what matters.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: SITE_TITLE,
    template: "%s",
  },
  description: SITE_DESCRIPTION,
  alternates: { canonical: "/" },
  // No dedicated 1200x630 OG asset exists yet — app/icon.png is a real,
  // already-served image, so this points there rather than fabricating a
  // path. A purpose-built social card is a reasonable follow-up.
  openGraph: {
    type: "website",
    siteName: "The Brief",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    url: SITE_URL,
    images: ["/icon.png"],
  },
  twitter: {
    card: "summary",
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    images: ["/icon.png"],
  },
  appleWebApp: {
    title: "The Brief",
    // Next 16 emits only the modern <meta name="mobile-web-app-capable">
    // for this flag (verified in next/dist/lib/metadata/metadata.js) — it
    // buys nothing on pre-16.4 iOS, which only read the retired apple-
    // prefixed tag. Kept for the standards-track tag current browsers read.
    capable: true,
    // "default" (v2.4.0): an opaque system bar whose glyphs follow the OS
    // appearance. black-translucent (PR C) drew WHITE glyphs over the
    // page's own pixels — sound only while the top of EVERY route was ink
    // in both themes; it was already broken on /archive (no band there),
    // and the light-mode paper band re-creates it on every route. iOS has
    // no per-theme API for this static launch-time meta, so "default" is
    // the honest choice: always correct in light; in dark standalone the
    // bar follows the OS and mismatches only when the in-app toggle
    // diverges from the OS setting (accepted, spec §12). §4.3's env()
    // insets degrade gracefully to their base constants.
    statusBarStyle: "default",
  },
};

// PWA viewport (facelift spec §4.2, PR B; amended v2.4.0 §12). theme-color
// is a per-scheme media pair — light chrome over the paper band, ink
// chrome in dark. This overturns the §11.6 owner veto (owner decision
// 2026-08-28: light mode is completely paper, so ink chrome above it is
// the mismatch, not the brand). The media pair is the no-JS baseline and
// tracks the OS scheme; ClientApp mutates the metas at runtime so the
// in-app toggle wins when it diverges from the OS. Raw hex here is the
// Design.md carve-out (§10.3 item 8); values must match --paper (light
// steel) and --band (ink) in globals.css.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#E6E9EB" },
    { media: "(prefers-color-scheme: dark)", color: "#0B0F12" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // suppressHydrationWarning: the head script below writes data-theme onto
  // <html> before hydration; without it React 19 warns about the
  // server/client attribute mismatch and could reconcile the attribute away.
  // Scope is one level deep — it covers only <html>'s own attributes.
  return (
    <html
      lang="en"
      data-palette="steel-crimson"
      suppressHydrationWarning
      className={jetbrainsMono.variable}
    >
      <head>
        {/* FOUC guard (facelift spec §2): blocking inline script, the
            documented Next.js placement — runs before paint so a dark
            visitor never flashes light. localStorage gets its own inner
            try: with site data blocked the getter itself throws, and a
            single catch would skip the OS-preference fallback entirely.
            This is the app's first inline script: if a nonce-based CSP
            ever lands it needs the nonce. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=null;try{t=localStorage.getItem("thebrief.theme")}catch(e){}if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){}`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
