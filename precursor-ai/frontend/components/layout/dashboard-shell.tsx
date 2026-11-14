"use client";

import { useState } from "react";
import { DashboardHeader } from "@/components/layout/dashboard-header";
import { DashboardSidebar } from "@/components/layout/dashboard-sidebar";

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  return (
    <div className="flex min-h-screen">
      <DashboardSidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <DashboardHeader onMenuClick={() => setNavOpen(true)} />
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
