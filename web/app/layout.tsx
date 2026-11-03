import type { Metadata } from "next";
import { Be_Vietnam_Pro } from "next/font/google";
import "./globals.css";

const sans = Be_Vietnam_Pro({
  subsets: ["vietnamese", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-sans",
});

export const metadata: Metadata = {
  title: "Meeting Notes · Biên bản họp",
  description: "Phiên âm, soát lại và chốt biên bản cuộc họp tiếng Việt.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" className={sans.variable} suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
