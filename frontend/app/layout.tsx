import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Lenny Growth Assistant", description: "Grounded growth insight from Lenny's Podcast" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
