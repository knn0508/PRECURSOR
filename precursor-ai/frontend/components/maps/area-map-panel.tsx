"use client";

import dynamic from "next/dynamic";
import { LoadingState } from "@/components/dashboard/loading-state";
import type { MonitoredArea } from "@/types/api";

// MapLibre needs the browser (WebGL); skip SSR.
const AreaMap = dynamic(() => import("@/components/maps/area-map").then((m) => m.AreaMap), {
  ssr: false,
  loading: () => <LoadingState label="Loading map" className="p-5" />,
});

export function AreaMapPanel({ areas }: { areas: MonitoredArea[] }) {
  return (
    <div className="relative h-80 overflow-hidden rounded-lg border border-line">
      <AreaMap areas={areas} />
      {areas.length === 0 && (
        <p className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-xs text-ink-faint">
          No monitored areas or data layers to display yet.
        </p>
      )}
    </div>
  );
}
