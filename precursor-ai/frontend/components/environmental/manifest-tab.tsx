"use client";

import { FileJson } from "lucide-react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { AlertBlock, Notice } from "@/components/data/badges";
import { OriginBadge, ToneBadge, layerStatusTone } from "@/components/environmental/shared";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { coveragePct, formatResolution, layerTypeLabel, manifestCounts, manifestFilename, shortHash } from "@/lib/environmental-helpers";
import { getManifest } from "@/services/environmental";
import type { ManifestEntry, ManifestRead } from "@/types/environmental";

const str = (v: unknown) => (typeof v === "string" || typeof v === "number" ? String(v) : "n/a");

/** Client-side blob of the already-fetched manifest; no endpoint, no path. */
function download(m: ManifestRead) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(m, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = manifestFilename(m.area_id);
  a.click();
  URL.revokeObjectURL(url);
}

const cols: Column<ManifestEntry>[] = [
  { key: "t", header: "Layer", render: (e) => <span className="text-ink">{layerTypeLabel(e.layer_type)}{e.source?.dataset_name ? ` (${str(e.source.dataset_name)})` : ""}</span> },
  { key: "k", header: "Kind", render: (e) => e.kind },
  { key: "tk", header: "Temporal", render: (e) => e.temporal_kind },
  { key: "s", header: "Status", render: (e) => <ToneBadge tone={layerStatusTone(e.status)}>{e.status.replaceAll("_", " ")}</ToneBadge> },
  { key: "u", header: "Units", render: (e) => e.units ?? "n/a" },
  { key: "c", header: "CRS", render: (e) => e.crs ?? "n/a" },
  { key: "n", header: "Native res.", render: (e) => formatResolution(e.native_resolution) },
  { key: "p", header: "Processing res.", render: (e) => formatResolution(e.processing_resolution) },
  { key: "g", header: "On ref. grid", render: (e) => (e.kind === "raster" ? (e.on_reference_grid ? "yes" : "no") : "n/a") },
  { key: "d", header: "Date range", render: (e) => (e.temporal_start ? `${e.temporal_start.slice(0, 10)} to ${e.temporal_end?.slice(0, 10) ?? "?"}` : "n/a") },
  { key: "o", header: "Origin", render: (e) => <OriginBadge origin={e.synthetic ? "SYNTHETIC_FIXTURE" : e.data_origin} /> },
  { key: "cv", header: "Valid / AOI coverage", render: (e) => `${coveragePct(e.coverage?.valid_percent)} / ${coveragePct(e.coverage?.aoi_coverage_percent)}` },
  { key: "h", header: "Lineage", render: (e) => <span className="font-mono text-xs" title={e.lineage_hash ?? "no lineage hash"}>{shortHash(e.lineage_hash)}</span> },
  { key: "r", header: "Reason", render: (e) => e.reason ?? "" },
];

export function ManifestTab({ areaId }: { areaId: string }) {
  const m = useApi((s) => getManifest(areaId, s));
  if (m.isLoading && !m.data) return <LoadingState label="Loading manifest" />;
  if (m.error) return <ErrorState title="Could not load manifest" message={m.error.message} onRetry={m.refetch} />;
  const d = m.data;
  if (!d || d.entries.length === 0) {
    return <EmptyState icon={FileJson} title="No manifest entries" description="No datasets are recorded for this area yet. Process the area from the Overview tab." />;
  }
  const g = d.reference_grid;
  const c = manifestCounts(d.entries);
  const bounds = g?.bounds === undefined || g?.bounds === null ? "n/a" : JSON.stringify(g.bounds);
  const warnings = Array.isArray(g?.warnings) ? (g.warnings as unknown[]).filter((w): w is string => typeof w === "string") : [];
  return (
    <div className="space-y-4">
      <Notice>
        Data stack inventory. Validation status: {d.validation_status}; real-data validation: {d.real_data_validation}. Missing values are shown as n/a, never as zero.
      </Notice>
      {d.contains_synthetic_data && (
        <p role="alert" className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-sm font-semibold text-warn">
          SYNTHETIC TEST DATA: this stack contains synthetic entries that are not real measurements.
        </p>
      )}
      <Card><CardContent className="space-y-1 text-sm">
        <h2 className="font-semibold">Reference grid</h2>
        {g ? (
          <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
            <div>CRS: {str(g.crs)}{g.epsg ? ` (EPSG:${str(g.epsg)})` : ""}</div>
            <div>Resolution: {formatResolution(g.resolution as Record<string, unknown> | undefined)}</div>
            <div>Size: {str(g.width)} x {str(g.height)} px</div>
            <div>Chosen by: {str(g.chosen_by)}</div>
            <div className="sm:col-span-2 break-all">Bounds: {bounds}</div>
          </dl>
        ) : <p className="text-ink-muted">No reference grid recorded (n/a).</p>}
        <AlertBlock title="Grid warnings" items={warnings} />
      </CardContent></Card>
      <Card><CardContent className="space-y-1 text-sm">
        <h2 className="font-semibold">Counts</h2>
        <p>Raster {c.raster} · series {c.series} · vector {c.vector} · static {c.static} · dynamic {c.dynamic} · synthetic {c.synthetic}</p>
      </CardContent></Card>
      <Card><CardContent className="space-y-3">
        <DataTable caption="Manifest entries" columns={cols} rows={d.entries} rowKey={(e) => `${e.layer_type}:${e.layer_id ?? e.source?.dataset_name ?? ""}`} emptyMessage="None." />
        <AlertBlock title="Notes" items={d.notes} />
        <Button onClick={() => download(d)}>Download manifest JSON</Button>
      </CardContent></Card>
    </div>
  );
}
