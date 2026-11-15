"use client";

import dynamic from "next/dynamic";
import { LoadingState } from "@/components/dashboard/loading-state";
import type { MapOverlay } from "@/components/maps/area-map";
import type { MonitoredArea } from "@/types/api";

// MapLibre needs the browser (WebGL); skip SSR.
const AreaMap = dynamic(() => import("@/components/maps/area-map").then((m) => m.AreaMap), {
  ssr: false,
  loading: () => <LoadingState label="Loading map" className="p-5" />,
});

export function AreaMapPanel({ areas, overlay }: { areas: MonitoredArea[]; overlay?: MapOverlay | null }) {
  return (
    <div className="relative h-[28rem] overflow-hidden rounded-lg border border-line">
      <AreaMap areas={areas} overlay={overlay} />
      {overlay && (
        <div className="pointer-events-none absolute bottom-3 left-3 rounded-md border border-line bg-surface/90 px-3 py-2 text-[11px] text-ink-muted">
          <p className="mb-1 font-medium text-ink">{overlay.label}</p>
          <div className="h-2 w-40 rounded" style={{ background: "linear-gradient(90deg,#5a6cf5,#f5f5f5,#f55a5a)" }} />
          <div className="mt-0.5 flex w-40 justify-between"><span>away</span><span>0</span><span>toward</span></div>
          <p className="mt-1">Smoothed 3x3 for display. Mostly reverses the last change; not slope motion. Not a warning.</p>
        </div>
      )}
      {areas.length === 0 && !overlay && (
        <p className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-xs text-ink-faint">
          No monitored areas registered. Add one under Monitored Areas.
        </p>
      )}
    </div>
  );
}
