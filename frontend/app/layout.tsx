import type { Metadata } from "next";

import { Shell } from "@/components/shell";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Sitemend",
  description: "Scans a site, proposes checked SEO fixes, ships approved ones at the edge and rolls them back.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
