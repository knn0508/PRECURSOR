"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { label: "Overview", href: "/dashboard/data" },
  { label: "Search", href: "/dashboard/data/search" },
  { label: "Downloads", href: "/dashboard/data/downloads" },
  { label: "Inventory", href: "/dashboard/data/inventory" },
];

export function DataTabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="Data acquisition sections" className="flex gap-1 border-b border-line">
      {TABS.map(({ label, href }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium",
              active ? "border-accent text-ink" : "border-transparent text-ink-muted hover:text-ink",
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

/** Page heading + tabs shared by the four pages. */
export function DataHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="mt-1 text-sm text-ink-muted">{description}</p>
      </div>
      <DataTabs />
    </div>
  );
}
