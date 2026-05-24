import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Code Review Crew",
  description: "5-agent parallel AI code review for GitHub PRs",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-neutral-50 text-neutral-900">
        <header className="border-b border-neutral-200 bg-white">
          <nav className="mx-auto max-w-5xl flex items-center gap-6 px-6 py-4">
            <Link href="/" className="font-semibold text-lg flex items-center gap-2">
              🤖 Code Review Crew
            </Link>
          </nav>
        </header>
        <main className="flex-1 mx-auto w-full max-w-5xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
