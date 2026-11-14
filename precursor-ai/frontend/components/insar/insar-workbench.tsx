"use client";

import { Radar } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { AlertBlock, Notice } from "@/components/data/badges";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { ApiError } from "@/lib/api-client";
import { formatBytes } from "@/lib/data-helpers";
import {
  INSAR_DISCLAIMER, PRODUCT_LABEL, formatStat, hasActiveRuns, isSynthetic, isTerminal, originLabel, parseThreshold,
  statusLabel, statusTone,
} from "@/lib/insar-helpers";
import { formatDateTime } from "@/lib/utils";
import {
  cancelInsarRun, createInsarRun, getInsarQuality, getInsarRun, inspectInsarProduct, listInsarProducts, listInsarRuns,
  previewUrl, rasterUrl, type InputRef,
} from "@/services/insar";
import type { InspectionReport, ProcessableProduct, RunStatus } from "@/types/insar";

const POLL_MS = 2000;
const refOf = (p: ProcessableProduct): InputRef =>
  p.source === "SAMPLE" ? { sample_file: p.name } : { acquisition_id: p.id };

function OriginBanner({ origin }: { origin: Parameters<typeof originLabel>[0] }) {
  return (
    <p role={isSynthetic(origin) ? "alert" : undefined}
      className={isSynthetic(origin) ? "rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-sm font-semibold text-warn" : "text-xs text-ink-muted"}>
      {originLabel(origin)}
    </p>
  );
}

function RunStatusBadge({ status }: { status: RunStatus }) {
  const t = statusTone(status);
  return <Badge variant={t === "ok" ? "ok" : t === "accent" ? "accent" : t === "warn" ? "demo" : "neutral"}
    className={t === "danger" ? "border-danger/40 bg-danger/10 text-danger" : undefined}>{statusLabel(status)}</Badge>;
}

function InspectionView({ r }: { r: InspectionReport }) {
  return (
    <Card>
      <CardContent className="space-y-3 text-sm">
        <h3 className="font-semibold">Inspection: {r.file_name}</h3>
        <OriginBanner origin={r.data_origin} />
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
          <div><dt className="text-ink-muted">Product</dt><dd>{r.product_kind} {r.product_version ?? ""}</dd></div>
          <div><dt className="text-ink-muted">Size</dt><dd>{formatBytes(r.file_size_bytes)}</dd></div>
          <div><dt className="text-ink-muted">Orbit</dt><dd>{r.orbit_direction ?? "unknown"}</dd></div>
          <div><dt className="text-ink-muted">Wavelength</dt><dd>{r.wavelength_m ? `${(r.wavelength_m * 100).toFixed(2)} cm` : "unknown"}</dd></div>
          <div><dt className="text-ink-muted">Reference</dt><dd>{r.reference_time ? formatDateTime(r.reference_time) : "unknown"}</dd></div>
          <div><dt className="text-ink-muted">Secondary</dt><dd>{r.secondary_time ? formatDateTime(r.secondary_time) : "unknown"}</dd></div>
        </dl>
        <p>Displacement can be derived from this file: <strong>{r.displacement_supported ? "yes (per its own metadata)" : "no"}</strong></p>
        <AlertBlock title="Why displacement is not supported" items={r.displacement_blockers} />
        <AlertBlock title="Missing metadata" items={r.missing} />
        <AlertBlock title="Warnings" items={r.warnings} />
      </CardContent>
    </Card>
  );
}

function RunDetail({ id }: { id: string }) {
  const run = useApi((s) => getInsarRun(id, s));
  const status = run.data?.status;
  // The quality report exists only once the run is terminal: do not request it earlier (it would 404).
  const done = useRef(false);
  done.current = !!status && isTerminal(status);
  const quality = useApi((s) => (done.current ? getInsarQuality(id, s).catch(() => null) : Promise.resolve(null)));
  useEffect(() => {
    if (!status || isTerminal(status)) {
      if (status) quality.refetch();
      return;
    }
    const t = setTimeout(run.refetch, POLL_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, run.data?.progress]);

  if (run.isLoading && !run.data) return <LoadingState label="Loading run" />;
  if (run.error || !run.data) return <ErrorState title="Could not load run" message={run.error?.message ?? "Unknown error"} onRetry={run.refetch} />;
  const r = run.data;
  const q = quality.data;
  return (
    <Card>
      <CardContent className="space-y-4 text-sm" aria-live="polite">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold">Run {r.id.slice(0, 8)}: {r.input_ref}</h3>
          <RunStatusBadge status={r.status} />
          {!isTerminal(r.status) && <span>{Math.round(r.progress * 100)}%</span>}
        </div>
        <OriginBanner origin={r.data_origin} />
        {r.error_message && <AlertBlock tone={r.status === "FAILED" ? "danger" : "warn"}
          title={r.status === "BLOCKED_MISSING_INPUT" ? "Blocked (not a processing failure)" : r.status === "FAILED" ? "Processing failed" : "Stopped"}
          items={[r.error_message]} />}
        <ol aria-label="Stages" className="space-y-0.5">
          {r.stages.map((s) => (
            <li key={s.name}><span className="font-mono text-xs">{s.name}</span>: {s.status}{s.message ? ` (${s.message})` : ""}</li>
          ))}
        </ol>
        {r.status === "COMPLETED" && r.products.length === 0 && (
          <Notice>Inspection-only run: this product type cannot yield displacement, so no raster was produced.</Notice>
        )}
        {r.products.map((p) => (
          <figure key={p.id} className="space-y-1 rounded-lg border border-line p-3">
            <figcaption className="font-medium">{PRODUCT_LABEL[p.product_type]} <span className="text-ink-muted">[{p.units}]</span></figcaption>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={previewUrl(p.id)} alt={`${PRODUCT_LABEL[p.product_type]} quick-look, ${p.units}`}
              className="max-h-72 rounded border border-line bg-surface-2" />
            <p className="text-xs text-ink-muted">
              {p.product_type === "COHERENCE" ? "Grayscale: dark = high coherence. Transparent = no data." :
                "Blue = negative, red = positive, symmetric auto scale (98th percentile of |value|). Transparent = no data (never zero)."}
            </p>
            <p className="text-xs">
              min {formatStat(p.statistics.min, p.units)} · max {formatStat(p.statistics.max, p.units)} · mean {formatStat(p.statistics.mean, p.units)} ·
              no-data {typeof p.statistics.nodata_percent === "number" ? `${p.statistics.nodata_percent.toFixed(1)}%` : "n/a"} · {p.crs ?? "CRS unknown"}
            </p>
            {p.sign_convention && <p className="text-xs text-warn">Sign convention (unverified): {p.sign_convention}</p>}
            <a className="text-xs text-accent underline" href={rasterUrl(p.id)}>Download GeoTIFF (COG)</a>
          </figure>
        ))}
        {q && (
          <div className="space-y-2">
            <p><strong>Real-data validation:</strong> {q.real_data_validation}. <strong>Scientifically validated:</strong> {q.scientifically_validated ? "yes" : "no"}.</p>
            <AlertBlock title="Quality warnings" items={q.warnings} />
            <AlertBlock title="Limitations" items={q.limitations} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function InsarWorkbench() {
  const products = useApi((s) => listInsarProducts(s));
  const runs = useApi((s) => listInsarRuns({ limit: 50 }, s));
  const [inspection, setInspection] = useState<InspectionReport | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [threshold, setThreshold] = useState("");
  const [velocity, setVelocity] = useState(true);
  const t = parseThreshold(threshold);

  useEffect(() => {
    if (!runs.data || !hasActiveRuns(runs.data.items)) return;
    const timer = setTimeout(runs.refetch, POLL_MS);
    return () => clearTimeout(timer);
  }, [runs.data, runs.refetch]);

  async function act<T>(key: string, fn: () => Promise<T>, then?: (v: T) => void) {
    setBusy(key);
    setActionError(null);
    try {
      then?.(await fn());
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : "Request failed");
    } finally {
      setBusy(null);
    }
  }

  const productCols: Column<ProcessableProduct>[] = [
    { key: "n", header: "File", render: (p) => <span className="break-all font-mono text-xs text-ink">{p.name}</span> },
    { key: "t", header: "Type", render: (p) => p.product_type },
    { key: "s", header: "Source", render: (p) => <Badge variant={p.source === "SAMPLE" ? "demo" : "accent"}>{p.source === "SAMPLE" ? "Local sample" : "Phase 2 download"}</Badge> },
    { key: "z", header: "Size", render: (p) => formatBytes(p.size_bytes) },
    { key: "a", header: "Actions", render: (p) => (
      <div className="flex gap-2">
        <Button size="sm" disabled={busy !== null} onClick={() => act(`i${p.id}`, () => inspectInsarProduct(refOf(p)), setInspection)}>Inspect</Button>
        <Button size="sm" variant="primary" disabled={busy !== null || t === undefined}
          onClick={() => act(`p${p.id}`, () => createInsarRun(refOf(p), { coherence_threshold: t ?? null, compute_velocity: velocity }),
            (r) => { setSelected(r.run.id); runs.refetch(); })}>Process</Button>
      </div>) },
  ];
  const runCols: Column<NonNullable<typeof runs.data>["items"][number]>[] = [
    { key: "i", header: "Input", render: (r) => <span className="break-all font-mono text-xs text-ink">{r.input_ref}</span> },
    { key: "k", header: "Type", render: (r) => r.product_kind ?? "-" },
    { key: "s", header: "Status", render: (r) => <RunStatusBadge status={r.status} /> },
    { key: "o", header: "Origin", render: (r) => (isSynthetic(r.data_origin) ? <Badge variant="demo">Synthetic</Badge> : r.data_origin ? "Unvalidated" : "-") },
    { key: "c", header: "Created", render: (r) => formatDateTime(r.created_at) },
    { key: "a", header: "", render: (r) => (
      <div className="flex gap-2">
        <Button size="sm" onClick={() => setSelected(r.id)}>View</Button>
        {!isTerminal(r.status) && <Button size="sm" disabled={busy !== null} onClick={() => act(`c${r.id}`, () => cancelInsarRun(r.id), runs.refetch)}>Cancel</Button>}
      </div>) },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Deformation (InSAR)</h1>
        <p className="mt-1 text-sm text-ink-muted">{INSAR_DISCLAIMER}</p>
      </div>
      <div aria-live="polite">{actionError && <ErrorState title="Action failed" message={actionError} />}</div>

      <section aria-label="Input products" className="space-y-2">
        <h2 className="text-sm font-semibold">Input products (files already on disk)</h2>
        {products.isLoading && !products.data ? <LoadingState label="Loading products" /> :
          products.error ? <ErrorState title="Could not load products" message={products.error.message} onRetry={products.refetch} /> :
          products.data && products.data.items.length === 0 ? (
            <EmptyState icon={Radar} title="No processable SAR files"
              description="Only NISAR GUNW/GSLC/GCOV files that were downloaded in Phase 2 (or placed in data/samples/insar) appear here. Catalog search hits are metadata only and nothing is downloaded automatically."
              action={<Link className="text-sm text-accent underline" href="/dashboard/data/downloads">Open Data Acquisition</Link>} />
          ) : products.data ? (
            <Card><CardContent className="space-y-3">
              <label className="flex flex-wrap items-center gap-2 text-sm">
                Coherence threshold (blank = no masking)
                <input inputMode="decimal" value={threshold} onChange={(e) => setThreshold(e.target.value)} aria-invalid={t === undefined}
                  className="h-8 w-24 rounded border border-line bg-surface-2 px-2" placeholder="none" />
                <span className="text-xs text-ink-muted">No universal threshold exists; masked pixels become no-data, never zero.</span>
              </label>
              {t === undefined && <p role="alert" className="text-xs text-danger">Enter a number between 0 and 1, or leave blank.</p>}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={velocity} onChange={(e) => setVelocity(e.target.checked)} /> Also compute mean LOS velocity (needs both acquisition dates)
              </label>
              <DataTable caption="Processable SAR products" columns={productCols} rows={products.data.items} rowKey={(p) => p.id} emptyMessage="None." />
            </CardContent></Card>
          ) : null}
      </section>

      {inspection && <InspectionView r={inspection} />}

      <section aria-label="Processing runs" className="space-y-2">
        <h2 className="text-sm font-semibold">Processing runs</h2>
        {runs.error ? <ErrorState title="Could not load runs" message={runs.error.message} onRetry={runs.refetch} /> :
          runs.data && runs.data.items.length === 0 ? <Notice>No runs yet.</Notice> :
          runs.data ? <Card><CardContent><DataTable caption="Processing runs" columns={runCols} rows={runs.data.items} rowKey={(r) => r.id} emptyMessage="None." /></CardContent></Card> : <LoadingState label="Loading runs" />}
      </section>

      {selected && <RunDetail key={selected} id={selected} />}
    </div>
  );
}
