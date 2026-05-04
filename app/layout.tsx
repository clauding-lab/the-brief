import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["200", "300", "400", "500", "600"],
  variable: "--mono-font",
  display: "swap",
});

export const metadata: Metadata = {
  title: "The Brief — Bangladesh business intelligence",
  description:
    "Daily macro & markets read for Bangladesh treasury desks. Numbers, news, and a banker's read on what matters.",
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
