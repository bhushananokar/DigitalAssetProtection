import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { Toaster } from "sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: "Digital Asset Protection",
  description: "Rights holder dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <AppShell>{children}</AppShell>
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
