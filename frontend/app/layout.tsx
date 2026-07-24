import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AmEx AI Servicing Agent — FinTech at Scale",
  description: "End-to-End Autonomous Customer Servicing & Audit Pipeline",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#f4f4f0] text-slate-100 flex flex-col antialiased">
        <main className="flex-1 w-full mx-auto">
          {children}
        </main>
      </body>
    </html>
  );
}
