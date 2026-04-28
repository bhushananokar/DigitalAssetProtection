"use client";

import { BarChart3, Radar, Search, ShieldAlert, Upload } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/ThemeToggle";

const nav = [
  { href: "/", label: "Overview", icon: BarChart3 },
  { href: "/violations", label: "Violations", icon: ShieldAlert },
  { href: "/assets", label: "Assets", icon: Upload },
  { href: "/scanner", label: "Scanner", icon: Radar },
  { href: "/check", label: "Manual Check", icon: Search },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      <aside className="w-72 border-r p-5" style={{ borderColor: "var(--border)", background: "var(--panel)" }}>
        <div className="mb-8">
          <p className="text-xs uppercase tracking-widest" style={{ color: "var(--muted)" }}>
            Digital Asset Protection
          </p>
          <h1 className="mt-2 text-xl font-semibold">Rights Dashboard</h1>
        </div>
        <nav className="space-y-2">
          {nav.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition"
                style={{
                  background: active ? "var(--primary-soft)" : "transparent",
                  color: active ? "var(--primary)" : "var(--text)",
                }}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <main className="flex-1 p-6 md:p-8">
        <div className="mb-6 flex items-center justify-end">
          <ThemeToggle />
        </div>
        {children}
      </main>
    </div>
  );
}
