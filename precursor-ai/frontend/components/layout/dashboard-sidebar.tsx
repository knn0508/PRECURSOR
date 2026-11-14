"use client";

import { Satellite, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { NAV_ITEMS } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface DashboardSidebarProps {
  open: boolean;
  onClose: () => void;
}

export function DashboardSidebar({ open, onClose }: DashboardSidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {open && <div aria-hidden className="fixed inset-0 z-30 bg-black/60 md:hidden" onClick={onClose} />}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-line bg-surface transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-line px-5">
          <Link href="/dashboard" className="flex items-center gap-2.5" onClick={onClose}>
            <Satellite aria-hidden className="h-5 w-5 text-accent" />
            <span className="text-sm font-semibold tracking-[0.18em]">PRECURSOR AI</span>
          </Link>
          <Button variant="ghost" size="icon" className="md:hidden" onClick={onClose} aria-label="Close navigation">
            <X aria-hidden className="h-4 w-4" />
          </Button>
        </div>
        <nav aria-label="Primary" className="flex-1 space-y-1 overflow-y-auto p-3">
          {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
            const active = href === "/dashboard" ? pathname === href : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={onClose}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  active ? "bg-accent/10 text-accent" : "text-ink-muted hover:bg-surface-2 hover:text-ink",
                )}
              >
                <Icon aria-hidden className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <p className="border-t border-line px-5 py-3 text-[11px] leading-relaxed text-ink-faint">
          Scientific prototype. Risk outputs are not validated forecasts.
        </p>
      </aside>
    </>
  );
}
