import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Meeting Notes · Biên bản họp",
  description: "Phiên âm, soát lại và lưu biên bản cuộc họp tiếng Việt.",
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="vi"><body>{children}</body></html>;
}
