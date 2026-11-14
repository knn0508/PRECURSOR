"use client";

import { MapPinned } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { EventsTab } from "@/components/environmental/events-tab";
import { LayerManager } from "@/components/environmental/layer-manager";
import { ManifestTab } from "@/components/environmental/manifest-tab";
import { OverviewTab } from "@/components/environmental/overview-tab";
import { QualityTab } from "@/components/environmental/quality-tab";
import { RainfallTab } from "@/components/environmental/rainfall-tab";
import { TerrainTab } from "@/components/environmental/terrain-tab";
import { useApi } from "@/hooks/use-api";
import { ENV_DISCLAIMER } from "@/lib/environmental-helpers";
import { cn } from "@/lib/utils";
import { listAreas } from "@/services/areas";
import type { MonitoredArea } from "@/types/api";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "map", label: "Map layers" },
  { id: "terrain", label: "Terrain" },
  { id: "rainfall", label: "Rainfall" },
  { id: "events", label: "Events" },
  { id: "quality", label: "Quality" },
  { id: "manifest", label: "Manifest" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function Panel({ tab, area }: { tab: TabId; area: MonitoredArea }) {
  // key on area so every panel refetches cleanly when the selection changes
  switch (tab) {
    case "map": return <LayerManager key={area.id} area={area} />;
    case "terrain": return <TerrainTab key={area.id} areaId={area.id} />;
    case "rainfall": return <RainfallTab key={area.id} areaId={area.id} />;
    case "events": return <EventsTab key={area.id} areaId={area.id} />;
    case "quality": return <QualityTab key={area.id} areaId={area.id} />;
    case "manifest": return <ManifestTab key={area.id} areaId={area.id} />;
    default: return <OverviewTab key={area.id} areaId={area.id} />;
  }
}

export function EnvironmentalSection() {
  const areas = useApi((s) => listAreas(s));
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tabParam = params.get("tab");
  const tab: TabId = TABS.some((t) => t.id === tabParam) ? (tabParam as TabId) : "overview";
  const items = areas.data?.items ?? [];
  const area = items.find((a) => a.id === params.get("area")) ?? items[0];

  const go = (next: { tab?: string; area?: string }) => {
    const q = new URLSearchParams(params.toString());
    if (next.tab) q.set("tab", next.tab);
    if (next.area) q.set("area", next.area);
    router.replace(`${pathname}?${q.toString()}`, { scroll: false });
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Environmental &amp; Geospatial</h1>
        <p className="mt-1 text-sm font-medium text-warn">{ENV_DISCLAIMER}</p>
      </div>

      {areas.isLoading && !areas.data ? <LoadingState label="Loading monitored areas" /> :
        areas.error ? <ErrorState title="Could not load monitored areas" message={areas.error.message} onRetry={areas.refetch} /> :
        !area ? (
          <EmptyState icon={MapPinned} title="No monitored areas"
            description="Environmental layers are computed per monitored area. Create an area first, then come back to process its data."
            action={<Link className="text-sm text-accent underline" href="/dashboard/areas">Open Monitored Areas</Link>} />
        ) : (
          <>
            <label className="flex flex-wrap items-center gap-2 text-sm">
              Monitored area
              <select value={area.id} onChange={(e) => go({ area: e.target.value })}
                className="h-8 rounded border border-line bg-surface-2 px-2">
                {items.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
            <nav aria-label="Environmental sections" className="flex gap-1 overflow-x-auto border-b border-line">
              {TABS.map((t) => (
                <button key={t.id} type="button" aria-current={t.id === tab ? "page" : undefined}
                  onClick={() => go({ tab: t.id, area: area.id })}
                  className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium",
                    t.id === tab ? "border-accent text-ink" : "border-transparent text-ink-muted hover:text-ink")}>
                  {t.label}
                </button>
              ))}
            </nav>
            <Panel tab={tab} area={area} />
          </>
        )}
    </div>
  );
}
