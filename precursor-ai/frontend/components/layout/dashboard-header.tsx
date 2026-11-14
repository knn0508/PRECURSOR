"use client";

import { Menu } from "lucide-react";
import { StatusIndicator, type Status } from "@/components/dashboard/status-indicator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import { getHealth } from "@/services/system";

export function DashboardHeader({ onMenuClick }: { onMenuClick: () => void }) {
  const { data, error, isLoading } = useApi(getHealth);

  const status: Status = isLoading ? "loading" : error ? "down" : data?.status === "ok" ? "ok" : "degraded";
  const label = isLoading
    ? "Checking system"
    : error
      ? "API unreachable"
      : data?.status === "ok"
        ? "All systems operational"
        : "Degraded: database unavailable";

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-canvas/90 px-4 backdrop-blur md:px-6">
      <Button variant="ghost" size="icon" className="md:hidden" onClick={onMenuClick} aria-label="Open navigation">
        <Menu aria-hidden className="h-5 w-5" />
      </Button>
      <p className="hidden text-sm text-ink-muted sm:block">SAR deformation monitoring</p>
      <div className="ml-auto flex items-center gap-4">
        {data && <Badge>v{data.version}</Badge>}
        <StatusIndicator status={status} label={label} />
      </div>
    </header>
  );
}
