"use client";

import { Mountain } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { AlertBlock } from "@/components/data/badges";
import { OriginBadge, OriginBanner } from "@/components/environmental/shared";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { formatValue, splitValues, type Bin } from "@/lib/environmental-helpers";
import { getTerrain } from "@/services/environmental";

export function BinChart({ title, bins, xLabel }: { title: string; bins: Bin[]; xLabel?: string }) {
  const summary = bins.map((b) => `${b.label}: ${b.count}`).join(", ");
  return (
    <figure className="space-y-1">
      <figcaption className="text-sm font-medium">{title}</figcaption>
      <div className="h-56 w-full" role="img" aria-label={`${title}. ${summary}`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={bins} margin={{ top: 4, right: 8, bottom: 16, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#94a3b8" }} label={xLabel ? { value: xLabel, position: "insideBottom", offset: -10, fill: "#94a3b8", fontSize: 11 } : undefined} />
            <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} />
            <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
            <Bar dataKey="count" name="pixels" fill="#38bdf8" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <details className="text-xs text-ink-muted"><summary>Data table</summary><p>{summary}</p></details>
    </figure>
  );
}

export function TerrainTab({ areaId }: { areaId: string }) {
  const t = useApi((s) => getTerrain(areaId, s));
  if (t.isLoading && !t.data) return <LoadingState label="Loading terrain" />;
  if (t.error) return <ErrorState title="Could not load terrain" message={t.error.message} onRetry={t.refetch} />;
  const d = t.data;
  if (!d || d.status === "NOT_AVAILABLE") {
    return <EmptyState icon={Mountain} title="No terrain data" description="No elevation layer has been processed for this area. Run processing from the Overview tab. Nothing is shown rather than zeros." />;
  }
  const { stats, charts } = splitValues(d.values, d.units);
  const cols: Column<(typeof stats)[number]>[] = [
    { key: "k", header: "Measure", render: (s) => <span className="font-mono text-xs text-ink">{s.key}</span> },
    { key: "v", header: "Value", render: (s) => (typeof s.value === "number" ? formatValue(s.value, s.unit) : s.value === null ? "n/a" : String(s.value)) },
  ];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <OriginBadge origin={d.data_origin} />
        <span className="text-xs text-ink-muted">{d.measurement_kind.replaceAll("_", " ").toLowerCase()} · status {d.status}</span>
      </div>
      <OriginBanner origin={d.data_origin} />
      <AlertBlock title="Warnings" items={d.warnings} />
      <Card><CardContent className="space-y-3">
        <DataTable caption="Terrain statistics" columns={cols} rows={stats} rowKey={(s) => s.key} emptyMessage="No statistics reported." />
        <p className="text-xs text-ink-muted">
          Aspect convention: degrees clockwise from north, the downslope direction. Flat pixels have no defined aspect and are counted separately, not as 0 degrees.
        </p>
      </CardContent></Card>
      {charts.length === 0 ? (
        <p className="text-sm text-ink-muted">No slope histogram or aspect distribution was reported.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {charts.map((c) => <Card key={c.key}><CardContent><BinChart title={c.key.replaceAll("_", " ")} bins={c.bins} /></CardContent></Card>)}
        </div>
      )}
    </div>
  );
}
