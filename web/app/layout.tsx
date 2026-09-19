import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ponder — Mission Control",
  description: "An agent that decides how hard to think.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
