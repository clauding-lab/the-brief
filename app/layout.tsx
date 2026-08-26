import type { Metadata } from "next";
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
  },
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
