"use client";

import { CheckCircle2, Gauge, MapPinned, Satellite, TrendingUp } from "lucide-react";
import { useMemo } from "react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { StatCard } from "@/components/dashboard/stat-card";
import { StatusIndicator } from "@/components/dashboard/status-indicator";
import { AreaMapPanel } from "@/components/maps/area-map-panel";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { colorLimit, gridToDataUrl, skillPct, smoothGrid } from "@/lib/displacement-helpers";
import { formatDateTime } from "@/lib/utils";
import { getDisplacementForecast, getDisplacementMetrics, getDisplacementStatus } from "@/services/displacement";
import { getDataStatus } from "@/services/data";
import { listAcquisitions } from "@/services/acquisitions";
import { listAreas } from "@/services/areas";
import { getHealth, getSystemInfo } from "@/services/system";
import type { SatelliteAcquisition } from "@/types/api";

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

  const forecast = useApi((s) => getDisplacementForecast(s));
  const metrics = useApi((s) => getDisplacementMetrics(s));
  const dstatus = useApi((s) => getDisplacementStatus(s));
  const data = useApi((s) => getDataStatus(s));
  const overlay = useMemo(() => {
    const g = forecast.data;
    if (!g) return null;
    const sm = smoothGrid(g.bands.q50_mm);
    const url = gridToDataUrl(sm, colorLimit(sm));
    const b = g.bounds;
    return url ? { imageUrl: url, bounds: [b.west, b.south, b.east, b.north] as [number, number, number, number], corners: g.corners, label: "12-day LOS forecast (q50)" } : null;
  }, [forecast.data]);
  const prov = dstatus.data?.provenance;
  const best = metrics.data ? Math.min(...metrics.data.benchmark.filter((r) => r.MAE_mm !== null).map((r) => r.MAE_mm as number)) : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Live platform state. The map shows the research displacement forecast; no high/medium/low risk classes are issued because no validated, calibrated model exists.
        </p>
      </div>

      <section aria-label="Key figures" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Monitored areas"
          icon={MapPinned}
          value={areas.isLoading ? "..." : (areas.data?.total ?? null)}
          hint={areas.error ? "Could not load areas" : "From the database"}
        />
        <StatCard label="Forecast coverage" icon={Gauge} value={prov ? `${Math.round((prov.pixels_with_estimate / prov.pixels_total) * 100)}%` : null}
          hint={prov ? `${prov.pixels_with_estimate} of ${prov.pixels_total} 30 m pixels have an estimate` : "Displacement bundle not loaded"} />
        <StatCard label="Skill vs zero-motion" icon={TrendingUp} tone="warn" value={best !== null && metrics.data ? `${skillPct(best, metrics.data.best_naive_mae).toFixed(1)}%` : null}
          hint="12-day MAE, held-out test, one site (research)" />
        <StatCard label="Registered granules" icon={Satellite} value={data.data ? data.data.acquisitions_registered : null} hint="NASA catalog records in the database" />
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Monitoring map</CardTitle>
            <Badge variant="demo">{overlay ? "Research layer" : "No layer"}</Badge>
          </CardHeader>
          <CardContent>
            {areas.error ? (
              <ErrorState title="Could not load areas" message={areas.error.message} onRetry={areas.refetch} />
            ) : (
              <>
                <AreaMapPanel areas={areas.data?.items ?? []} overlay={overlay} />
                <p className="mt-2 text-xs text-ink-muted">
                  {overlay ? `Portuguese Bend, CA: 12-day LOS displacement forecast issued ${forecast.data?.issue_time.slice(0, 10)} (red toward satellite, blue away; transparent = no reliable estimate). Research, inferred, not a warning. ` : ""}
                  <a href="/dashboard/displacement" className="text-accent hover:underline">Details</a>
                </p>
              </>
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
