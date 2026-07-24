"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CreditCard, ShieldCheck, UserCheck, Activity, Cpu } from "lucide-react";

export default function Navbar() {
  const pathname = usePathname();

  const navItems = [
    { name: "Customer Chat", path: "/", icon: CreditCard },
    { name: "Supervisor Dashboard", path: "/supervisor", icon: UserCheck },
    { name: "Audit Trail & Compliance", path: "/audit", icon: ShieldCheck },
  ];

  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-slate-800 px-6 py-3.5">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        {/* Brand Logo */}
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl amex-gradient flex items-center justify-center font-bold text-white shadow-lg glow-blue">
            AX
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-semibold text-lg text-white tracking-wide">
                American Express
              </h1>
              <span className="bg-blue-950/80 text-blue-400 text-xs px-2 py-0.5 rounded-full border border-blue-800/50 flex items-center gap-1 font-mono">
                <Cpu className="w-3 h-3" /> AI Servicing
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Autonomous Financial Servicing & Audit Agent
            </p>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="flex items-center gap-1 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.path;
            return (
              <Link
                key={item.path}
                href={item.path}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? "bg-blue-600 text-white shadow-md glow-blue"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Pipeline Status Indicator */}
        <div className="hidden md:flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-900/90 px-3 py-1.5 rounded-lg border border-slate-800 text-xs">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-slate-300 font-mono">Policy Engine Online</span>
          </div>
        </div>
      </div>
    </header>
  );
}
