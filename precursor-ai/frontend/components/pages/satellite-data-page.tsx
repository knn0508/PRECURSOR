"use client";

import Link from "next/link";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { StatCard } from "@/components/dashboard/stat-card";
import { DataTable } from "@/components/dashboard/data-table";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Database, FileCheck2, HardDrive, Satellite } from "lucide-react";
import { useApi } from "@/hooks/use-api";
import { formatBytes } from "@/lib/data-helpers";
import { formatDateTime } from "@/lib/utils";
import { getDataStatus, listDataAcquisitions } from "@/services/data";
import { getDisplacementStatus } from "@/services/displacement";
import type { AcquisitionRead } from "@/types/data";

export function SatelliteDataPage() {
  const status = useApi((s) => getDataStatus(s));
  const acq = useApi((s) => listDataAcquisitions({ limit: 25 }, s));
  const disp = useApi((s) => getDisplacementStatus(s));
  const p = disp.data?.provenance;
  const st = status.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Satellite data</h1>
        <p className="mt-1 text-sm text-ink-muted">What is registered, downloaded and validated, plus the satellite data behind the displacement forecast. A catalog hit is not a download; a download is not scientific validation.</p>
      </div>

      {status.error ? <ErrorState title="Could not load data status" message={status.error.message} onRetry={status.refetch} /> :
        !st ? <LoadingState label="Loading data status" /> : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Registered granules" value={st.acquisitions_registered} icon={Satellite} hint="metadata in the database" />
            <StatCard label="Files downloaded" value={st.files_downloaded} icon={Database} />
            <StatCard label="Files validated" value={st.files_validated} icon={FileCheck2} hint="integrity only" />
            <StatCard label="Free storage" value={st.storage_free_bytes === null ? null : formatBytes(st.storage_free_bytes)} icon={HardDrive} />
          </div>
        )}

      <Card>
        <CardHeader><CardTitle>Acquisition catalog</CardTitle><Link href="/dashboard/data/search" className="text-xs text-accent hover:underline">Search and register</Link></CardHeader>
        <CardContent>
          {acq.error ? <ErrorState title="Could not load acquisitions" message={acq.error.message} onRetry={acq.refetch} /> :
            !acq.data ? <LoadingState label="Loading acquisitions" /> : (
              <DataTable<AcquisitionRead> rows={acq.data.items} rowKey={(r) => r.id}
                emptyMessage="Nothing registered yet. Use Data Acquisition to search NASA catalogs (search needs no login; downloads need approved files)."
                columns={[
                  { key: "p", header: "Provider", render: (r) => r.provider },
                  { key: "g", header: "Granule", render: (r) => <span className="font-mono text-xs">{r.granule_id}</span> },
                  { key: "t", header: "Start", render: (r) => (r.acquisition_start ? formatDateTime(r.acquisition_start) : "unknown") },
                  { key: "o", header: "Orbit", render: (r) => r.orbit_direction ?? "unknown" },
                  { key: "m", header: "Maturity", render: (r) => <Badge variant={r.maturity === "VALIDATED" ? "ok" : "demo"}>{r.maturity ?? "unknown"}</Badge> },
                  { key: "s", header: "Status", render: (r) => <Badge>{r.status}</Badge> },
                ]} />
            )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Data behind the displacement forecast (third-party bundle)</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          {!p ? <p className="text-ink-muted">{disp.isLoading ? "Loading" : "Result bundle not found."}</p> : (
            <>
              <p>Sentinel-1 C-band, OPERA DISP-S1 frame {p.frame}, {p.orbit.toLowerCase()} track {p.track}, {p.resolution_m} m. Train {p.train_period[0]} to {p.train_period[1]}; test {p.test_period[0]} to {p.test_period[1]}.</p>
              <p className="text-xs text-ink-muted">NISAR ({p.nisar_observation.maturity}) is displayed as an observation only and was never used for training. These files were not downloaded by this platform; only the author's result artifacts are stored.</p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
