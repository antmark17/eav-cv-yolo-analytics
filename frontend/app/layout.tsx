import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EAV Smart Station · Video Events",
  description: "Dashboard operativa per eventi video EAV.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="it">
      <body>{children}</body>
    </html>
  );
}
