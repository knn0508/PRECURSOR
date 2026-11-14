"use client";

import { Database, Download, FileCheck2, XCircle } from "lucide-react";
import { useState } from "react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { StatCard } from "@/components/dashboard/stat-card";
import { MaturityBadge, Notice, StatusBadge } from "@/components/data/badges";
import { inputCls } from "@/components/data/aoi-fields";
import { DataHeader } from "@/components/data/data-tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { ApiError } from "@/lib/api-client";
import { formatBytes } from "@/lib/data-helpers";
import { formatDateTime } from "@/lib/utils";
import { getDataStatus, importLandslideEvents, listDataAcquisitions, listLandslideEvents } from "@/services/data";
import type {
  AcquisitionRead, AcquisitionStatus, LandslideEventRead, LandslideImportResponse, Maturity,
} from "@/types/data";

const STATUSES: AcquisitionStatus[] = [
  "DISCOVERED", "QUEUED", "DOWNLOADING", "DOWNLOADED", "VALIDATING", "VALIDATED", "FAILED", "SKIPPED", "UNAVAILABLE",
];
const PRODUCTS = ["GUNW", "GCOV", "GSLC", "GOFF", "SME2"];
const MATURITIES: Maturity[] = ["VALIDATED", "PROVISIONAL", "BETA"];
const PAGE = 10;

function Counts() {
  const { data, error, isLoading, refetch } = useApi(getDataStatus);
  if (isLoading) return <LoadingState label="Loading inventory counts" />;
  if (error) return <ErrorState title="Could not load inventory counts" message={error.message} onRetry={refetch} />;
  if (!data) return null;
  const dist = Object.entries(data.product_distribution);
  const max = Math.max(1, ...dist.map(([, n]) => n));
  return (
    <>
      <section aria-label="Inventory counts" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total acquisitions" value={data.acquisitions_registered} icon={Database} />
        <StatCard label="Downloaded" value={data.files_downloaded} icon={Download} />
        <StatCard label="Passed integrity checks" value={data.files_validated} icon={FileCheck2} tone="ok" hint="Not scientific validation" />
        <StatCard label="Failed jobs" value={data.jobs_failed} icon={XCircle} tone={data.jobs_failed > 0 ? "danger" : "default"} />
      </section>
      <Card>
        <CardHeader><CardTitle>Product distribution</CardTitle></CardHeader>
        <CardContent>
          {dist.length === 0 ? (
            <p className="text-sm text-ink-muted">No acquisitions registered yet.</p>
          ) : (
            <ul className="space-y-2">
              {dist.map(([k, n]) => (
                <li key={k} className="grid grid-cols-[5rem_1fr_3rem] items-center gap-3 text-sm">
                  <span>{k}</span>
                  <div className="h-3 rounded bg-surface-2" aria-hidden>
                    <div className="h-full rounded bg-accent" style={{ width: `${(n / max) * 100}%` }} />
                  </div>
                  <span className="text-right font-mono">{n}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </>
  );
}

const ACQ_COLS: Column<AcquisitionRead>[] = [
  { key: "g", header: "Granule", render: (r) => <span className="break-all font-mono text-xs text-ink">{r.granule_id}</span> },
  { key: "p", header: "Product", render: (r) => `${r.provider} ${r.product_type}` },
  { key: "a", header: "Acquired", render: (r) => (r.acquisition_start ? formatDateTime(r.acquisition_start) : "unknown") },
  { key: "sz", header: "Size", render: (r) => formatBytes(r.file_size_bytes) },
  { key: "m", header: "Maturity", render: (r) => <MaturityBadge maturity={r.maturity} /> },
  { key: "s", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
  { key: "e", header: "Error", render: (r) => (r.error_message ? <span className="text-danger">{r.error_message}</span> : "-") },
];

// Remounted (via key) when filters change, so useApi refetches without extra effect plumbing.
function AcquisitionsTable({ product, status, maturity }: { product: string; status: string; maturity: string }) {
  const { data, error, isLoading, refetch } = useApi((s) =>
    listDataAcquisitions({ product_type: product, status: status as AcquisitionStatus | "", maturity: maturity as Maturity | "", limit: 20 }, s));
  if (isLoading) return <LoadingState label="Loading acquisitions" />;
  if (error) return <ErrorState title="Could not load acquisitions" message={error.message} onRetry={refetch} />;
  if (!data || data.items.length === 0) {
    return <EmptyState icon={Database} title="No acquisitions" description="Nothing registered matches these filters. Run a non-dry-run search to register granules." />;
  }
  return (
    <>
      <DataTable caption="Recent acquisitions" columns={ACQ_COLS} rows={data.items} rowKey={(r) => r.id} emptyMessage="" />
      <p className="px-3 pt-2 text-xs text-ink-muted">Showing {data.items.length} of {data.total}.</p>
    </>
  );
}

function Select({ id, label, value, onChange, options }: {
  id: string; label: string; value: string; onChange: (v: string) => void; options: string[];
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      <select id={id} className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

const EVENT_COLS: Column<LandslideEventRead>[] = [
  { key: "id", header: "Event", render: (r) => <span className="font-mono text-xs text-ink">{r.external_event_id}</span> },
  { key: "d", header: "Date", render: (r) => (r.event_date ? formatDateTime(r.event_date) : "unknown") },
  { key: "l", header: "Location", render: (r) => [r.location_name, r.country].filter(Boolean).join(", ") || "-" },
  { key: "t", header: "Trigger", render: (r) => r.trigger ?? "-" },
  { key: "ty", header: "Type", render: (r) => r.landslide_type ?? "-" },
  { key: "c", header: "Lon, Lat", render: (r) => `${r.longitude.toFixed(3)}, ${r.latitude.toFixed(3)}` },
];

function LandslideEvents({ offset, onPage }: { offset: number; onPage: (o: number) => void }) {
  const { data, error, isLoading, refetch } = useApi((s) => listLandslideEvents({ offset, limit: PAGE }, s));
  if (isLoading) return <LoadingState label="Loading landslide events" />;
  if (error) return <ErrorState title="Could not load landslide events" message={error.message} onRetry={refetch} />;
  if (!data) return null;
  return (
    <div className="space-y-3">
      <div role="note" className="rounded-lg border border-warn/40 bg-warn/5 p-3 text-sm text-ink">
        <strong className="text-warn">Limitations: </strong>{data.limitations}
      </div>
      {data.items.length === 0 ? (
        <EmptyState icon={Database} title="No landslide events imported" description="Use Import catalog to load the official NASA export." />
      ) : (
        <>
          <DataTable caption="Global Landslide Catalog events" columns={EVENT_COLS} rows={data.items} rowKey={(r) => r.id} emptyMessage="" />
          <div className="flex items-center justify-between text-sm text-ink-muted">
            <span>{offset + 1} to {offset + data.items.length} of {data.total}</span>
            <div className="flex gap-2">
              <Button size="sm" disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - PAGE))}>Previous</Button>
              <Button size="sm" disabled={offset + PAGE >= data.total} onClick={() => onPage(offset + PAGE)}>Next</Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function LandslidePanel() {
  const [offset, setOffset] = useState(0);
  const [version, setVersion] = useState(0); // bump to remount the list after an import
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LandslideImportResponse | null>(null);

  async function doImport() {
    if (!window.confirm("This downloads the official NASA Global Landslide Catalog CSV (a few MB) and imports it into the database. Continue?")) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await importLandslideEvents({ force: false }));
      setOffset(0);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Global Landslide Catalog</CardTitle>
        <Button size="sm" onClick={doImport} disabled={busy}>{busy ? "Importing..." : "Import catalog"}</Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div aria-live="polite" className="space-y-3">
          {error && <ErrorState title="Import failed" message={error} />}
          {result && (
            <Notice>
              Imported {result.dataset_version}: {result.inserted} inserted, {result.updated} updated, {result.skipped_invalid} skipped
              as invalid (source: {result.source_file}). {result.limitations}
            </Notice>
          )}
        </div>
        <LandslideEvents key={`${version}-${offset}`} offset={offset} onPage={setOffset} />
      </CardContent>
    </Card>
  );
}

export function DataInventory() {
  const [product, setProduct] = useState("");
  const [status, setStatus] = useState("");
  const [maturity, setMaturity] = useState("");
  return (
    <div className="space-y-6">
      <DataHeader title="Inventory" description="What has been registered, downloaded and checked, plus the historical landslide catalog." />
      <Counts />
      <Card>
        <CardHeader><CardTitle>Recent acquisitions</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4">
            <Select id="f-product" label="Product" value={product} onChange={setProduct} options={PRODUCTS} />
            <Select id="f-status" label="Status" value={status} onChange={setStatus} options={STATUSES} />
            <Select id="f-maturity" label="Maturity" value={maturity} onChange={setMaturity} options={MATURITIES} />
          </div>
          <AcquisitionsTable key={`${product}|${status}|${maturity}`} product={product} status={status} maturity={maturity} />
        </CardContent>
      </Card>
      <LandslidePanel />
    </div>
  );
}
