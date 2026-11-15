"use client";

import { LineChart } from "lucide-react";
import { useState } from "react";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { Notice } from "@/components/data/badges";
import { SourceBadge } from "@/components/workspace/source-badge";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { sourceKindForSeries } from "@/lib/source-badges";
import { getSeriesAnalysis, listSeries } from "@/services/prediction";
import type { SeriesMeta } from "@/types/prediction";

function Analysis({ areaId, s }: { areaId: string; s: SeriesMeta }) {
  const a = useApi((sig) => getSeriesAnalysis(areaId, s.zone, s.kind, sig));
  if (a.isLoading && !a.data) return <LoadingState label="Analysing series" />;
  if (a.error || !a.data) return <ErrorState title="Could not analyse this series" message={a.error?.message ?? "no data"} onRetry={a.refetch} />;
  const lim = a.data.limitations as Record<string, unknown>;
  return (
    <div className="space-y-2 text-xs">
      <p>Valid points {String(lim.n_valid)} of {String(lim.n_points)}; median interval {String(lim.median_interval_days ?? "n/a")} d; gaps {Array.isArray(lim.gaps) ? lim.gaps.length : 0}; aliasing {String(lim.aliasing)}.</p>
      <ul className="space-y-1">
        {Object.entries(a.data.indicators).map(([k, v]) => (
          <li key={k}><span className="font-medium">{k.replaceAll("_", " ")}:</span>{" "}
            {v.status === "NOT_AVAILABLE" ? <span className="text-ink-muted">not available ({String(v.reason)})</span>
              : typeof v.slope_per_year === "number" ? `${v.slope_per_year.toFixed(3)} per year` : typeof v.acceleration_per_year2 === "number"
                ? `${v.acceleration_per_year2.toFixed(3)} per year^2` : String(v.trend ?? "computed")}
          </li>
        ))}
      </ul>
      {a.data.notes.map((n) => <p key={n} className="text-ink-muted">{n}</p>)}
    </div>
  );
}

/** Stored series for the area and their descriptive indicators (Phase 6). Statistics of observed values: not a forecast, not risk. */
export function TimeseriesPanel({ areaId }: { areaId: string }) {
  const list = useApi((s) => listSeries(areaId, s));
  const [sel, setSel] = useState<string>("");
  if (list.isLoading && !list.data) return <LoadingState label="Loading series" />;
  if (list.error) return <ErrorState title="Could not load series" message={list.error.message} onRetry={list.refetch} />;
  const items = list.data?.series ?? [];
  if (!items.length) return <EmptyState icon={LineChart} title="No stored time series" description="No series exists for this area. Series are written by services from processed rainfall, soil moisture or InSAR data; nothing is shown until they exist." />;
  const cur = items.find((s) => `${s.zone}/${s.kind}` === sel) ?? items[0];
  return (
    <div className="space-y-3">
      <Notice>Descriptive statistics of observed values only: no forecast, no extrapolation, no risk label. Confidence intervals assume independent errors.</Notice>
      <div className="flex flex-wrap gap-2">
        {items.map((s) => {
          const id = `${s.zone}/${s.kind}`;
          return <button key={id} type="button" aria-pressed={id === `${cur.zone}/${cur.kind}`} onClick={() => setSel(id)}
            className="rounded border border-line px-2 py-1 text-xs aria-pressed:border-accent">{s.zone} · {s.kind}</button>;
        })}
      </div>
      <Card><CardContent className="space-y-2 p-4">
        <div className="flex flex-wrap items-center gap-2 text-sm font-medium">{cur.kind} ({cur.units}) <SourceBadge kind={sourceKindForSeries(cur.contains_synthetic_data)} /></div>
        {cur.contains_synthetic_data && <p role="alert" className="text-xs font-semibold text-warn">SYNTHETIC TEST DATA: not a real measurement.</p>}
        <p className="text-xs text-ink-muted">{cur.sensor} · {cur.orbit_direction ?? "no orbit"} track {cur.track ?? "n/a"} · {cur.first_time.slice(0, 10)} to {cur.last_time.slice(0, 10)} · real-data validation {cur.real_data_validation}</p>
        <Analysis key={`${cur.zone}/${cur.kind}`} areaId={areaId} s={cur} />
      </CardContent></Card>
    </div>
  );
}
