"use client";

import { MapPinned } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { DataDownloads } from "@/components/data/data-downloads";
import { DataInventory } from "@/components/data/data-inventory";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { EventsTab } from "@/components/environmental/events-tab";
import { LayerManager } from "@/components/environmental/layer-manager";
import { ManifestTab } from "@/components/environmental/manifest-tab";
import { QualityTab } from "@/components/environmental/quality-tab";
import { RainfallTab } from "@/components/environmental/rainfall-tab";
import { TerrainTab } from "@/components/environmental/terrain-tab";
import { InsarWorkbench } from "@/components/insar/insar-workbench";
import { BacktestPanel } from "@/components/displacement/backtest-panel";
import { AoiUpload } from "@/components/workspace/aoi-upload";
import { EarlyWarningPanel } from "@/components/workspace/early-warning-panel";
import { ResearchNotice } from "@/components/workspace/early-warning-views";
import { TimeseriesPanel } from "@/components/workspace/timeseries-panel";
import { useApi } from "@/hooks/use-api";
import { USE_MOCK_PREDICTIONS } from "@/lib/config";
import { cn } from "@/lib/utils";
import { listAreas } from "@/services/areas";
import type { MonitoredArea } from "@/types/api";

const TABS = [
  { id: "map", label: "Map & layers" },
  { id: "terrain", label: "Terrain" },
  { id: "series", label: "Rainfall & series" },
  { id: "events", label: "Landslides & earthquakes" },
  { id: "inventory", label: "Satellite inventory" },
  { id: "jobs", label: "Jobs" },
  { id: "insar", label: "InSAR" },
  { id: "lineage", label: "Metadata & lineage" },
  { id: "backtest", label: "Forecast vs reality" },
  { id: "warning", label: "Early warning" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function Panel({ tab, area }: { tab: TabId; area: MonitoredArea }) {
  switch (tab) {
    case "backtest": return <BacktestPanel key={area.id} areaId={area.id} />;
    case "terrain": return <TerrainTab key={area.id} areaId={area.id} />;
    case "series": return <div className="space-y-6"><RainfallTab key={area.id} areaId={area.id} /><TimeseriesPanel key={`ts-${area.id}`} areaId={area.id} /></div>;
    case "events": return <EventsTab key={area.id} areaId={area.id} />;
    case "inventory": return <DataInventory />;
    case "jobs": return <DataDownloads />;
    case "insar": return <InsarWorkbench />;
    case "lineage": return <div className="space-y-6"><QualityTab key={area.id} areaId={area.id} /><ManifestTab key={`m-${area.id}`} areaId={area.id} /></div>;
    case "warning": return (
      <div className="space-y-4">
        <p className="text-sm text-ink-muted">Prediction views are wired to the model slot. No model is registered, so the API answers MODEL_NOT_TRAINED
          {USE_MOCK_PREDICTIONS ? " and this build shows clearly labelled MOCK layouts." : " and the default view shows N/A."} Real data panels are on the other tabs and are never mixed with these.</p>
        <div className="grid gap-4 lg:grid-cols-2">
          <EarlyWarningPanel key={`s-${area.id}`} areaId={area.id} head="susceptibility" />
          <EarlyWarningPanel key={`t-${area.id}`} areaId={area.id} head="trigger" />
        </div>
      </div>
    );
    default: return <LayerManager key={area.id} area={area} />;
  }
}

export function Workspace() {
  const areas = useApi((s) => listAreas(s));
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tabParam = params.get("tab");
  const tab: TabId = TABS.some((t) => t.id === tabParam) ? (tabParam as TabId) : "map";
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
        <h1 className="text-xl font-semibold">Early-warning workspace</h1>
        <ResearchNotice />
      </div>
      {areas.isLoading && !areas.data ? <LoadingState label="Loading monitored areas" /> :
        areas.error ? <ErrorState title="Could not load monitored areas" message={areas.error.message} onRetry={areas.refetch} /> : (
          <>
            <div className="grid gap-3 lg:grid-cols-[1fr_22rem]">
              {area ? (
                <label className="flex flex-wrap items-center gap-2 text-sm">Area of interest
                  <select value={area.id} onChange={(e) => go({ area: e.target.value })} className="h-8 rounded border border-line bg-surface-2 px-2">
                    {items.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                  </select>
                </label>
              ) : <EmptyState icon={MapPinned} title="No monitored areas" description="Upload a GeoJSON area of interest to begin. Nothing is shown for an area that does not exist." />}
              <AoiUpload onCreated={(a) => { areas.refetch(); go({ area: a.id }); }} />
            </div>
            {area && (
              <>
                <nav aria-label="Workspace sections" className="flex gap-1 overflow-x-auto border-b border-line">
                  {TABS.map((t) => (
                    <button key={t.id} type="button" aria-current={t.id === tab ? "page" : undefined} onClick={() => go({ tab: t.id, area: area.id })}
                      className={cn("-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium",
                        t.id === tab ? "border-accent text-ink" : "border-transparent text-ink-muted hover:text-ink")}>{t.label}</button>
                  ))}
                </nav>
                <Panel tab={tab} area={area} />
              </>
            )}
          </>
        )}
    </div>
  );
}
