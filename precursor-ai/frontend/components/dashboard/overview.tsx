"use client";

import { AlertTriangle, CheckCircle2, MapPinned, ShieldAlert, ShieldCheck } from "lucide-react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { StatCard } from "@/components/dashboard/stat-card";
import { StatusIndicator } from "@/components/dashboard/status-indicator";
import { AreaMapPanel } from "@/components/maps/area-map-panel";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { formatDateTime } from "@/lib/utils";
import { listAcquisitions } from "@/services/acquisitions";
import { listAreas } from "@/services/areas";
import { getHealth, getSystemInfo } from "@/services/system";
import type { SatelliteAcquisition } from "@/types/api";

const RISK_HINT = "Not available: risk assessment is not implemented yet";

const ACQ_COLUMNS: Column<SatelliteAcquisition>[] = [
  { key: "date", header: "Acquired", render: (r) => formatDateTime(r.acquisition_date) },
  { key: "src", header: "Source", render: (r) => r.satellite_source },
  { key: "orbit", header: "Orbit", render: (r) => r.orbit_direction ?? "-" },
  { key: "pol", header: "Pol.", render: (r) => r.polarization ?? "-" },
  { key: "status", header: "Status", render: (r) => <Badge>{r.processing_status}</Badge> },
];

export function Overview() {
  const health = useApi(getHealth);
  const info = useApi(getSystemInfo);
  const areas = useApi(listAreas);
  const acquisitions = useApi((s) => listAcquisitions(5, s));

  const planned = info.data?.modules.filter((m) => m.status === "planned").length ?? 0;
  const available = info.data?.modules.filter((m) => m.status === "available").length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Foundation phase: no SAR products have been processed and no risk model exists. Risk figures show N/A.
        </p>
      </div>

      <section aria-label="Key figures" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Monitored areas"
          icon={MapPinned}
          value={areas.isLoading ? "..." : (areas.data?.total ?? null)}
          hint={areas.error ? "Could not load areas" : "From the database"}
        />
        <StatCard label="High risk" icon={ShieldAlert} tone="danger" value={null} hint={RISK_HINT} />
        <StatCard label="Medium risk" icon={AlertTriangle} tone="warn" value={null} hint={RISK_HINT} />
        <StatCard label="Low risk" icon={ShieldCheck} tone="ok" value={null} hint={RISK_HINT} />
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Monitoring map</CardTitle>
            <Badge variant="neutral">Placeholder</Badge>
          </CardHeader>
          <CardContent>
            {areas.error ? (
              <ErrorState title="Could not load areas" message={areas.error.message} onRetry={areas.refetch} />
            ) : (
              <AreaMapPanel areas={areas.data?.items ?? []} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>System status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {health.isLoading ? (
              <LoadingState label="Checking system" />
            ) : health.error ? (
              <ErrorState title="API unreachable" message={health.error.message} onRetry={health.refetch} />
            ) : (
              health.data && (
                <dl className="space-y-3 text-sm">
                  <Row label="API">
                    <StatusIndicator status="ok" label={`${health.data.app_name} v${health.data.version}`} />
                  </Row>
                  <Row label="Database">
                    <StatusIndicator
                      status={health.data.database === "connected" ? "ok" : "down"}
                      label={health.data.database}
                    />
                  </Row>
                  <Row label="Environment">{info.data?.environment ?? "-"}</Row>
                  <Row label="Modules">
                    {info.data ? `${available} available, ${planned} planned` : "-"}
                  </Row>
                </dl>
              )
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Latest satellite acquisitions</CardTitle>
          </CardHeader>
          <CardContent>
            {acquisitions.isLoading ? (
              <LoadingState label="Loading acquisitions" />
            ) : acquisitions.error ? (
              <ErrorState message={acquisitions.error.message} onRetry={acquisitions.refetch} />
            ) : (
              <DataTable
                caption="Latest satellite acquisitions"
                columns={ACQ_COLUMNS}
                rows={acquisitions.data?.items ?? []}
                rowKey={(r) => r.id}
                emptyMessage="No acquisitions ingested yet."
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent system activity</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3 text-sm text-ink-muted">
              {health.data && (
                <Activity>
                  Health check: {health.data.status === "ok" ? "passed" : "degraded"} (database {health.data.database})
                </Activity>
              )}
              {areas.data && <Activity>{areas.data.total} monitored area(s) registered</Activity>}
              {acquisitions.data && <Activity>{acquisitions.data.total} acquisition record(s) catalogued</Activity>}
              {!health.data && !areas.data && !acquisitions.data && (
                <li className="text-ink-faint">No activity to show.</li>
              )}
            </ul>
            <p className="mt-4 text-[11px] text-ink-faint">Live values from the API at page load, not a persisted log.</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="text-right text-ink-muted">{children}</dd>
    </div>
  );
}

function Activity({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      <CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
      <span>{children}</span>
    </li>
  );
}
