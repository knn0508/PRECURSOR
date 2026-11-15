"use client";

import { Search } from "lucide-react";
import { useState } from "react";
import { ErrorState } from "@/components/dashboard/error-state";
import { EmptyState } from "@/components/dashboard/empty-state";
import { AlertBlock, Notice } from "@/components/data/badges";
import { AoiFields, EMPTY_AOI, type AoiState } from "@/components/data/aoi-fields";
import { DataHeader } from "@/components/data/data-tabs";
import { DownloadJobsList } from "@/components/data/data-downloads";
import { GranuleTable } from "@/components/data/granule-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import { IMERG_NOTE, buildAoi, buildDateRange } from "@/lib/data-helpers";
import { acquireEnvironmental, createDownloads, searchData } from "@/services/data";
import type {
  DownloadCreateResponse, EnvironmentalAcquireResponse, Maturity, SearchResponse,
} from "@/types/data";

const PRODUCTS = ["GUNW", "GCOV", "GSLC", "GOFF", "SME2"];
const MATURITIES: Maturity[] = ["VALIDATED", "PROVISIONAL", "BETA"];

function toggle<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

function CheckGroup<T extends string>({ legend, options, value, onChange }: {
  legend: string; options: T[]; value: T[]; onChange: (v: T[]) => void;
}) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {options.map((o) => (
          <label key={o} className="flex items-center gap-1.5 text-sm text-ink-muted">
            <input type="checkbox" checked={value.includes(o)} onChange={() => onChange(toggle(value, o))} />
            {o}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : "Unexpected error");

function SearchPanel() {
  const [aoi, setAoi] = useState<AoiState>(EMPTY_AOI);
  const [providers, setProviders] = useState<string[]>(["NISAR"]);
  const [products, setProducts] = useState(["GUNW", "GCOV", "GSLC"]);
  const [maturities, setMaturities] = useState<Maturity[]>(["VALIDATED"]);
  const [maxResults, setMaxResults] = useState(10);
  const [dryRun, setDryRun] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [res, setRes] = useState<SearchResponse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [queuing, setQueuing] = useState(false);
  const [queued, setQueued] = useState<DownloadCreateResponse | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const a = buildAoi(aoi.areaId, aoi.geojson);
    const d = buildDateRange(aoi.start, aoi.end);
    if (!a.ok) return setFormError(a.error);
    if (!d.ok) return setFormError(d.error);
    if (providers.length === 0) return setFormError("Select at least one catalog.");
    if (providers.includes("NISAR") && (products.length === 0 || maturities.length === 0)) return setFormError("Select at least one NISAR product and one maturity.");
    if (!Number.isInteger(maxResults) || maxResults < 1 || maxResults > 100) return setFormError("Max results must be 1 to 100.");
    setFormError(null);
    setBusy(true);
    setApiError(null);
    setQueued(null);
    setSelected(new Set());
    try {
      setRes(await searchData({
        aoi: a.aoi, start_date: d.start_date, end_date: d.end_date,
        providers: providers as ("NISAR" | "OPERA" | "NASADEM" | "GPM")[], products, maturities, max_results: maxResults, dry_run: dryRun,
      }));
    } catch (err) {
      setRes(null);
      setApiError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  async function queue() {
    setQueuing(true);
    setQueueError(null);
    try {
      setQueued(await createDownloads([...selected]));
      setSelected(new Set());
    } catch (err) {
      setQueueError(errMsg(err));
    } finally {
      setQueuing(false);
    }
  }

  const hasGpm = res?.results.some((r) => r.provider === "GPM");
  return (
    <Card>
      <CardHeader><CardTitle>Search NASA catalog (CMR)</CardTitle></CardHeader>
      <CardContent className="space-y-5">
        <form onSubmit={submit} className="space-y-5">
          <AoiFields idp="s" value={aoi} onChange={setAoi} />
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5 md:col-span-2">
              <CheckGroup legend="Catalogs" options={["NISAR", "OPERA", "NASADEM", "GPM"]} value={providers} onChange={setProviders} />
              <p className="text-xs text-ink-muted">Search reads metadata only (no login, nothing is downloaded). Products and maturity below apply to NISAR.</p>
            </div>
            <div className="space-y-1.5">
              <CheckGroup legend="Products" options={PRODUCTS} value={products} onChange={setProducts} />
              <p className="text-xs text-ink-muted">SME2 has no VALIDATED collection: only PROVISIONAL/BETA results can exist.</p>
            </div>
            <div className="space-y-1.5">
              <CheckGroup legend="Maturity (NISAR)" options={MATURITIES} value={maturities} onChange={setMaturities} />
              <p className="text-xs text-ink-muted">Default is VALIDATED only. PROVISIONAL and BETA are lower maturity and stay labelled.</p>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="s-max" className="text-sm font-medium">Max results (1 to 100)</label>
              <input id="s-max" type="number" min={1} max={100} value={maxResults}
                onChange={(e) => setMaxResults(Number(e.target.value))}
                className="w-28 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink" />
            </div>
            <label className="flex items-center gap-2 self-end text-sm">
              <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
              Dry run: do not register results
            </label>
          </div>
          {formError && <p role="alert" className="text-sm text-danger">{formError}</p>}
          <Button type="submit" variant="primary" disabled={busy}>
            <Search aria-hidden className="h-4 w-4" />
            {busy ? "Searching..." : "Search"}
          </Button>
        </form>

        <div aria-live="polite" className="space-y-4">
          {busy && <p className="text-sm text-ink-muted">Searching NASA CMR...</p>}
          {apiError && <ErrorState title="Search failed" message={apiError} />}
          {res && (
            <>
              <AlertBlock title="Warnings" items={res.warnings} />
              <AlertBlock title="Provider errors" tone="danger" items={Object.entries(res.provider_errors).map(([k, v]) => `${k}: ${v}`)} />
              {hasGpm && <Notice>{IMERG_NOTE}</Notice>}
              {res.dry_run && <Notice>Dry run: nothing was registered, so these rows cannot be queued for download.</Notice>}
              {res.results.length === 0 ? (
                <EmptyState icon={Search} title="No granules found" description={`No results for ${res.aoi_name} with these filters.`} />
              ) : (
                <>
                  <GranuleTable
                    caption={`Search results for ${res.aoi_name}`}
                    rows={res.results}
                    selected={selected}
                    onToggle={(id) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; })}
                  />
                  {!res.dry_run && (
                    <div className="space-y-2">
                      <Notice>
                        Downloads require an Earthdata login (credentials are configured on the server, never here). GUNW files are
                        about 1.4 GB each and take a while; track them on the Downloads tab.
                      </Notice>
                      <Button variant="primary" disabled={selected.size === 0 || queuing} onClick={queue}>
                        {queuing ? "Queuing..." : `Queue download (${selected.size})`}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </>
          )}
          {queueError && <ErrorState title="Could not queue downloads" message={queueError} />}
          {queued && (
            <div className="space-y-3">
              {queued.jobs.length > 0 && <DownloadJobsList jobs={queued.jobs} caption="Newly queued download jobs" />}
              <AlertBlock title="Skipped (not queued)" items={Object.entries(queued.skipped).map(([id, why]) => `${id}: ${why}`)} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function EnvironmentalPanel() {
  const [aoi, setAoi] = useState<AoiState>(EMPTY_AOI);
  const [smap, setSmap] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [res, setRes] = useState<EnvironmentalAcquireResponse | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const a = buildAoi(aoi.areaId, aoi.geojson);
    const d = buildDateRange(aoi.start, aoi.end);
    if (!a.ok) return setFormError(a.error);
    if (!d.ok) return setFormError(d.error);
    if (!d.start_date || !d.end_date) return setFormError("Environmental data needs both a start and an end date.");
    setFormError(null);
    setBusy(true);
    setApiError(null);
    try {
      setRes(await acquireEnvironmental({ aoi: a.aoi, start_date: d.start_date, end_date: d.end_date, include_smap: smap, dry_run: dryRun }));
    } catch (err) {
      setRes(null);
      setApiError(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Environmental data (NASADEM, GPM IMERG, optional SMAP)</CardTitle></CardHeader>
      <CardContent className="space-y-5">
        <Notice>{IMERG_NOTE}</Notice>
        <form onSubmit={submit} className="space-y-5">
          <AoiFields idp="e" value={aoi} onChange={setAoi} />
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={smap} onChange={(e) => setSmap(e.target.checked)} />Include SMAP (optional)</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />Dry run (report only, no download)</label>
          </div>
          {formError && <p role="alert" className="text-sm text-danger">{formError}</p>}
          <Button type="submit" variant="primary" disabled={busy}>{busy ? "Working..." : dryRun ? "Preview environmental data" : "Acquire environmental data"}</Button>
        </form>
        <div aria-live="polite" className="space-y-4">
          {apiError && <ErrorState title="Environmental acquisition failed" message={apiError} />}
          {res && (
            <>
              <AlertBlock title="Warnings" items={res.warnings} />
              <AlertBlock title="Provider errors" tone="danger" items={Object.entries(res.provider_errors).map(([k, v]) => `${k}: ${v}`)} />
              {res.dry_run && <Notice>Dry run: listed granules were not downloaded.</Notice>}
              {res.results.length === 0 ? (
                <EmptyState icon={Search} title="No environmental granules" description="Nothing matched this area and date range." />
              ) : (
                <GranuleTable caption="Environmental data results" rows={res.results} />
              )}
              {res.jobs.length > 0 && <DownloadJobsList jobs={res.jobs} caption="Download jobs created" />}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function DataSearch() {
  return (
    <div className="space-y-6">
      <DataHeader title="Search NASA data" description="Find granules for an area and date range. Search results are metadata only until downloaded." />
      <SearchPanel />
      <EnvironmentalPanel />
    </div>
  );
}
