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
  return (
    <html lang="en" data-palette="steel-crimson" className={jetbrainsMono.variable}>
      <body>{children}</body>
    </html>
  );
}
