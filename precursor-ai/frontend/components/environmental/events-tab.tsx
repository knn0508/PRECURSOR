"use client";

import { Activity } from "lucide-react";
import { useState } from "react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { AlertBlock } from "@/components/data/badges";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { ApiError } from "@/lib/api-client";
import { eventFeatures, parseMagnitude, validateDateRange } from "@/lib/environmental-helpers";
import { getLandslides, getSeismic, refreshSeismic } from "@/services/environmental";
import type { EventFeature, EventsRead, SeismicRefreshResponse } from "@/types/environmental";

const show = (v: unknown) => (v === null || v === undefined || v === "" ? "n/a" : typeof v === "object" ? JSON.stringify(v) : String(v));

function EventTable({ title, data, emptyText, caveat }: { title: string; data: EventsRead; emptyText: string; caveat: string }) {
  const feats = eventFeatures(data.geojson);
  // columns come from the properties actually present (first 6 keys), so nothing is invented
  const keys = [...new Set(feats.flatMap((f) => Object.keys(f.properties ?? {})))].slice(0, 6);
  const cols: Column<EventFeature>[] = keys.map((k) => ({ key: k, header: k.replaceAll("_", " "), render: (f) => show(f.properties?.[k]) }));
  return (
    <section aria-label={title} className="space-y-2">
      <h2 className="text-sm font-semibold">{title} <span className="font-normal text-ink-muted">({data.total} in this area)</span></h2>
      <p role="note" className="rounded-lg border border-warn/40 bg-warn/5 px-3 py-2 text-sm text-warn">{caveat}</p>
      <AlertBlock title="Limitations" items={data.limitations} />
      {feats.length === 0 ? (
        <p className="text-sm text-ink-muted">{emptyText}</p>
      ) : (
        <Card><CardContent>
          <DataTable caption={title} columns={cols} rows={feats} rowKey={(f) => String(f.properties?.id ?? JSON.stringify(f.geometry) + JSON.stringify(f.properties))} emptyMessage="None." />
        </CardContent></Card>
      )}
    </section>
  );
}

function SeismicRefresh({ areaId, onDone }: { areaId: string; onDone: () => void }) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [mag, setMag] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<SeismicRefreshResponse | null>(null);
  const [armed, setArmed] = useState(false); // explicit confirmation: this contacts an external public service
  const rangeError = validateDateRange(start, end, { required: true });
  const m = parseMagnitude(mag);

  async function submit() {
    setBusy(true); setErr(null); setRes(null); setArmed(false);
    try {
      setRes(await refreshSeismic(areaId, { start_date: start, end_date: end, min_magnitude: m ?? null }));
      onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  const field = "h-8 rounded border border-line bg-surface-2 px-2";
  return (
    <Card><CardContent className="space-y-3 text-sm">
      <h3 className="font-semibold">Refresh earthquake catalog</h3>
      <p className="text-xs text-ink-muted">Fetches earthquakes for this area from the public USGS catalog (anonymous, read-only). The area bounding box, dates and an optional minimum magnitude are sent; new records are stored, duplicates ignored. Asks for confirmation first.</p>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">Start date<input type="date" className={field} value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="flex flex-col gap-1">End date<input type="date" className={field} value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        <label className="flex flex-col gap-1">Min magnitude (optional)
          <input inputMode="decimal" className={`${field} w-28`} value={mag} onChange={(e) => setMag(e.target.value)} aria-invalid={m === undefined} placeholder="none" /></label>
        {armed ? (
          <>
            <Button variant="primary" disabled={busy} onClick={submit}>Confirm: contact the public USGS service</Button>
            <Button disabled={busy} onClick={() => setArmed(false)}>Cancel</Button>
          </>
        ) : (
          <Button variant="primary" disabled={busy || !!rangeError || m === undefined} onClick={() => setArmed(true)}>{busy ? "Fetching..." : "Refresh"}</Button>
        )}
      </div>
      {start && end && rangeError && <p role="alert" className="text-xs text-danger">{rangeError}</p>}
      {m === undefined && <p role="alert" className="text-xs text-danger">Magnitude must be a number between 0 and 10, or blank.</p>}
      {err && <ErrorState title="Refresh failed" message={err} />}
      {res && (
        <div aria-live="polite" className="space-y-2">
          <p>Fetched {res.fetched} · inserted <strong>{res.inserted}</strong> · duplicates {res.duplicates}</p>
          <AlertBlock title="Warnings" items={res.warnings} />
        </div>
      )}
    </CardContent></Card>
  );
}

export function EventsTab({ areaId }: { areaId: string }) {
  const ls = useApi((s) => getLandslides(areaId, s));
  const eq = useApi((s) => getSeismic(areaId, s));
  return (
    <div className="space-y-6">
      <p className="text-sm text-ink-muted">
        Cataloged historical events, not a complete inventory. Absence of an event proves nothing. Earthquakes are independent observations; neither list is a risk indicator.
      </p>
      {ls.isLoading && !ls.data ? <LoadingState label="Loading landslide catalog" /> :
        ls.error ? <ErrorState title="Could not load landslide events" message={ls.error.message} onRetry={ls.refetch} /> :
        !ls.data || ls.data.status === "NOT_AVAILABLE" ? (
          <EmptyState icon={Activity} title="Landslide catalog not available" description="No historical landslide catalog layer exists for this area. This does not mean no landslides occurred." />
        ) : <EventTable title="Historical landslide catalog events" data={ls.data}
          emptyText="No cataloged events inside this area. The catalog is incomplete, so this is not evidence of none."
          caveat="Cataloged historical events, not a complete inventory." />}

      {eq.isLoading && !eq.data ? <LoadingState label="Loading earthquakes" /> :
        eq.error ? <ErrorState title="Could not load earthquakes" message={eq.error.message} onRetry={eq.refetch} /> :
        !eq.data || eq.data.status === "NOT_AVAILABLE" ? (
          <EmptyState icon={Activity} title="No earthquake data" description="Use the refresh form below to fetch the earthquake catalog for this area." />
        ) : <EventTable title="Earthquakes" data={eq.data} emptyText="No earthquakes in the fetched window."
          caveat="Earthquakes are independent observations, not an indicator of landslide occurrence or risk." />}

      <SeismicRefresh areaId={areaId} onDone={eq.refetch} />
    </div>
  );
}
