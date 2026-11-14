"use client";

import { useEffect, useState } from "react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { OriginBadge, ToneBadge, layerStatusTone } from "@/components/environmental/shared";
import { AlertBlock, Notice } from "@/components/data/badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { ApiError } from "@/lib/api-client";
import {
  buildProcessConfig, formatPercent, layerTypeLabel, runStatusLabel, runStatusTone, shouldPoll, stageLabel, validateDateRange, validateGridCrs, validateGridResolution,
} from "@/lib/environmental-helpers";
import { formatDateTime } from "@/lib/utils";
import { getCoverage, getRun, startProcessing } from "@/services/environmental";
import type { CoverageItem } from "@/types/environmental";

const POLL_MS = 2000;

function RunPanel({ runId, onDone }: { runId: string; onDone: () => void }) {
  const run = useApi((s) => getRun(runId, s));
  const status = run.data?.status;
  useEffect(() => {
    if (!status) return;
    if (!shouldPoll(status)) { onDone(); return; }
    const t = setTimeout(run.refetch, POLL_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, run.data?.current_stage]);

  if (run.isLoading && !run.data) return <LoadingState label="Loading run" />;
  if (run.error || !run.data) return <ErrorState title="Could not load run" message={run.error?.message ?? "Unknown error"} onRetry={run.refetch} />;
  const r = run.data;
  return (
    <Card>
      <CardContent className="space-y-3 text-sm" aria-live="polite">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold">Run {r.id.slice(0, 8)}</h3>
          <ToneBadge tone={runStatusTone(r.status)}>{runStatusLabel(r.status)}</ToneBadge>
          {r.status === "PARTIAL" && <span className="text-xs text-warn">Not a full success: see stages below.</span>}
        </div>
        {r.error_message && <AlertBlock tone={r.status === "FAILED" ? "danger" : "warn"} title="Run message" items={[r.error_message]} />}
        <ol aria-label="Stages" className="space-y-1">
          {r.stages.map((s) => {
            const l = stageLabel(s.status);
            return (
              <li key={s.name} className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{s.name}</span>
                <ToneBadge tone={l.tone}>{l.text}</ToneBadge>
                {s.message && <span className="text-xs text-ink-muted">{s.message}</span>}
              </li>
            );
          })}
        </ol>
        <AlertBlock title="Warnings" items={r.warnings} />
      </CardContent>
    </Card>
  );
}

export function OverviewTab({ areaId }: { areaId: string }) {
  const coverage = useApi((s) => getCoverage(areaId, s));
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [gridCrs, setGridCrs] = useState("");
  const [gridRes, setGridRes] = useState("");
  const [rainfall, setRainfall] = useState("daily");
  const rangeError = validateDateRange(start, end);
  const crsError = validateGridCrs(gridCrs);
  const resError = validateGridResolution(gridRes);
  const invalid = !!(rangeError || crsError || resError);

  async function process() {
    setBusy(true);
    setErr(null);
    const cfg = buildProcessConfig({ start, end, gridCrs, gridRes, rainfall });
    try {
      setRunId((await startProcessing(areaId, cfg)).run.id);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  const cols: Column<CoverageItem>[] = [
    { key: "t", header: "Layer", render: (i) => <span className="text-ink">{layerTypeLabel(i.layer_type)}</span> },
    { key: "a", header: "Available", render: (i) => (i.available ? "Yes" : "No") },
    { key: "s", header: "Status", render: (i) => <ToneBadge tone={layerStatusTone(i.status)}>{i.status.replaceAll("_", " ")}</ToneBadge> },
    { key: "o", header: "Origin", render: (i) => (i.available || i.data_origin ? <OriginBadge origin={i.data_origin} /> : "-") },
    { key: "v", header: "Valid / missing", render: (i) => (i.available ? `${formatPercent(i.valid_percent)} / ${formatPercent(i.missing_percent)}` : "no data") },
    { key: "c", header: "AOI coverage", render: (i) => (i.available ? formatPercent(i.aoi_coverage_percent) : "no data") },
    { key: "p", header: "Period", render: (i) => (i.temporal_start ? `${i.temporal_start.slice(0, 10)} to ${i.temporal_end?.slice(0, 10) ?? "?"}` : "-") },
    { key: "r", header: "Reason", render: (i) => (i.available ? "" : i.reason ?? "No input available") },
  ];

  return (
    <div className="space-y-6">
      <section aria-label="Coverage" className="space-y-2">
        <h2 className="text-sm font-semibold">Data coverage</h2>
        {coverage.isLoading && !coverage.data ? <LoadingState label="Loading coverage" /> :
          coverage.error ? <ErrorState title="Could not load coverage" message={coverage.error.message} onRetry={coverage.refetch} /> :
          coverage.data && coverage.data.items.length === 0 ? (
            <Notice>No layers processed for this area yet. Use Process below. Missing data is shown as missing, never as zero.</Notice>
          ) : coverage.data ? (
            <Card><CardContent className="space-y-3">
              <DataTable caption="Layer coverage" columns={cols} rows={coverage.data.items} rowKey={(i) => `${i.layer_type}:${i.layer_id ?? ''}`} emptyMessage="None." />
              <AlertBlock title="Missing datasets" items={coverage.data.missing_datasets.map(layerTypeLabel)} />
              <p className="text-xs text-ink-muted">
                Last processed: {coverage.data.last_processed_at ? formatDateTime(coverage.data.last_processed_at) : "never"}. {coverage.data.note}
              </p>
            </CardContent></Card>
          ) : null}
      </section>

      <section aria-label="Process" className="space-y-2">
        <h2 className="text-sm font-semibold">Process this area</h2>
        <Card><CardContent className="space-y-3">
          <p className="text-xs text-ink-muted">Optional window for rainfall and seismic data (leave both blank for the default).</p>
          <div className="flex flex-wrap items-end gap-3 text-sm">
            <label className="flex flex-col gap-1">Start date
              <input type="date" value={start} onChange={(e) => setStart(e.target.value)} aria-invalid={!!rangeError}
                className="h-8 rounded border border-line bg-surface-2 px-2" /></label>
            <label className="flex flex-col gap-1">End date
              <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} aria-invalid={!!rangeError}
                className="h-8 rounded border border-line bg-surface-2 px-2" /></label>
          </div>
          <p className="text-xs text-ink-muted">Optional reference grid and rainfall product (blank = backend defaults).</p>
          <div className="flex flex-wrap items-end gap-3 text-sm">
            <label className="flex flex-col gap-1">Grid CRS
              <input type="text" placeholder="EPSG:32650" value={gridCrs} onChange={(e) => setGridCrs(e.target.value)} aria-invalid={!!crsError}
                className="h-8 w-36 rounded border border-line bg-surface-2 px-2" /></label>
            <label className="flex flex-col gap-1">Grid resolution (m)
              <input type="text" inputMode="decimal" placeholder="30" value={gridRes} onChange={(e) => setGridRes(e.target.value)} aria-invalid={!!resError}
                className="h-8 w-28 rounded border border-line bg-surface-2 px-2" /></label>
            <label className="flex flex-col gap-1">Rainfall product
              <select value={rainfall} onChange={(e) => setRainfall(e.target.value)} className="h-8 rounded border border-line bg-surface-2 px-2">
                <option value="daily">Daily (default)</option>
                <option value="half_hourly">Half-hourly</option>
              </select></label>
            <Button variant="primary" disabled={busy || invalid} onClick={process}>
              {busy ? "Starting..." : "Process"}
            </Button>
          </div>
          {[rangeError, crsError, resError].map((m) => m && <p key={m} role="alert" className="text-xs text-danger">{m}</p>)}
          {err && <ErrorState title="Could not start processing" message={err} />}
        </CardContent></Card>
        {runId && <RunPanel key={runId} runId={runId} onDone={coverage.refetch} />}
      </section>
    </div>
  );
}
