import type { Metadata, Viewport } from "next";
import { Nav } from "@/components/Nav";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";
import { ArmsCatalogProvider } from "@/lib/armsCatalog";
import "./globals.css";

export const metadata: Metadata = {
  title: "harness-lab",
  description: "Thin UI wrapper over the harness CLI control API",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "harness-lab",
  },
};

export const viewport: Viewport = {
  themeColor: "#e56b4e",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="acqua" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Mono:wght@400;500;600&family=Outfit:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen antialiased">
        <ServiceWorkerRegister />
        <ArmsCatalogProvider>
          <div className="app-shell">
            <Nav />
            <main className="py-8 pb-16">{children}</main>
          </div>
        </ArmsCatalogProvider>
      </body>
    </html>
  );
}
