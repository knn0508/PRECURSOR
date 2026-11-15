"use client";

import { CheckCircle2, Download, FileCheck2, HardDrive, Loader2, Mountain, XCircle } from "lucide-react";
import { DataHeader } from "@/components/data/data-tabs";
import { Notice } from "@/components/data/badges";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { StatCard } from "@/components/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { EARTHDATA_BANNER, IMERG_NOTE, formatBytes } from "@/lib/data-helpers";
import { formatDateTime } from "@/lib/utils";
import { getDataStatus } from "@/services/data";
import type { ProviderName, ProviderStatus } from "@/types/data";

const TITLES: Record<ProviderName, string> = {
  NISAR: "NISAR",
  NASADEM: "NASADEM",
  GPM: "GPM IMERG",
  LANDSLIDE_CATALOG: "Global Landslide Catalog",
  SMAP: "SMAP",
  OPERA: "OPERA DISP-S1",
};
const ORDER: ProviderName[] = ["NISAR", "NASADEM", "GPM", "OPERA", "LANDSLIDE_CATALOG", "SMAP"];
const AUTH_LABEL = {
  not_required: "Not required",
  configured: "Configured",
  missing: "Missing",
  failed: "Failed",
} as const;

function ProviderCard({ p }: { p: ProviderStatus }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{TITLES[p.name]}</CardTitle>
        <div className="flex gap-1.5">
          <Badge variant={p.enabled ? "ok" : "neutral"}>{p.enabled ? "Enabled" : "Disabled"}</Badge>
          {p.optional && <Badge>Optional</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-ink-muted">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt>Authentication</dt>
          <dd className={p.authentication === "failed" || p.authentication === "missing" ? "text-warn" : "text-ink"}>
            {AUTH_LABEL[p.authentication]}
          </dd>
          <dt>Collections discovered</dt>
          <dd className="font-mono text-ink">{p.collections_discovered}</dd>
          <dt>Last successful acquisition</dt>
          <dd className="text-ink">
            {p.last_successful_acquisition ? formatDateTime(p.last_successful_acquisition) : "none yet"}
          </dd>
        </dl>
        {p.name === "GPM" && <p className="text-warn">{IMERG_NOTE}</p>}
        {p.name === "NISAR" && (
          <p>NISAR products carry a maturity label (VALIDATED / PROVISIONAL / BETA); lower maturity is flagged wherever shown.</p>
        )}
        {p.note && <p>{p.note}</p>}
      </CardContent>
    </Card>
  );
}

export function DataOverview() {
  const { data, error, isLoading, refetch } = useApi(getDataStatus);

  return (
    <div className="space-y-6">
      <DataHeader
        title="Data Acquisition"
        description="NASA data sources, authentication state and acquisition totals, as reported by the backend."
      />
      {isLoading ? (
        <LoadingState label="Loading data acquisition status" />
      ) : error ? (
        <ErrorState title="Could not load data acquisition status" message={error.message} onRetry={refetch} />
      ) : data ? (
        <>
          {!data.earthdata_credentials_configured && (
            <div role="alert" className="rounded-lg border border-warn/40 bg-warn/5 p-4 text-sm text-ink">
              {EARTHDATA_BANNER}
            </div>
          )}
          <section aria-label="Quick stats" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Registered" value={data.acquisitions_registered} icon={Mountain} hint="Acquisitions in the database" />
            <StatCard label="Downloaded" value={data.files_downloaded} icon={Download} hint="Files on disk" />
            <StatCard label="Passed integrity checks" value={data.files_validated} icon={FileCheck2} tone="ok" hint="Not scientific validation" />
            <StatCard label="Failed jobs" value={data.jobs_failed} icon={XCircle} tone={data.jobs_failed > 0 ? "danger" : "default"} />
            <StatCard label="Active jobs" value={data.jobs_active} icon={Loader2} />
            <StatCard label="Landslide events" value={data.landslide_events} icon={CheckCircle2} />
            <StatCard label="Storage used" value={formatBytes(data.storage_used_bytes)} icon={HardDrive} hint={data.data_root} />
            <StatCard label="Storage free" value={formatBytes(data.storage_free_bytes)} icon={HardDrive} />
          </section>
          <section aria-labelledby="providers-h" className="space-y-3">
            <h2 id="providers-h" className="text-sm font-semibold">Data sources</h2>
            <Notice>{IMERG_NOTE}</Notice>
            <div className="grid gap-4 lg:grid-cols-2">
              {ORDER.map((n) => data.providers.find((p) => p.name === n)).filter((p): p is ProviderStatus => !!p).map((p) => (
                <ProviderCard key={p.name} p={p} />
              ))}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
