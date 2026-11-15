"use client";

import Link from "next/link";
import { BellOff, CheckCircle2, XCircle } from "lucide-react";
import { EmptyState } from "@/components/dashboard/empty-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { getPredictionStatus } from "@/services/prediction";
import { getDisplacementMetrics } from "@/services/displacement";
import { listAreas } from "@/services/areas";

interface Check { label: string; ok: boolean | null; detail: string }

/** Alerts are never generated. This page shows, from live API state, why none can be issued yet. */
export function AlertsPage() {
  const pred = useApi((s) => getPredictionStatus(s));
  const disp = useApi((s) => getDisplacementMetrics(s));
  const areas = useApi((s) => listAreas(s));
  const loading = pred.isLoading || disp.isLoading || areas.isLoading;
  const checks: Check[] = [
    { label: "Monitored area registered", ok: areas.data ? areas.data.total > 0 : null, detail: areas.data ? `${areas.data.total} area(s)` : "unknown" },
    { label: "Calibrated susceptibility/trigger model registered", ok: pred.data ? pred.data.registered_models > 0 : null,
      detail: pred.data ? `${pred.data.status}: ${pred.data.registered_models} model(s)` : "unknown" },
    { label: "Displacement forecast validated on the landslide core", ok: false,
      detail: "Not validated: the core is largely masked in OPERA 2024-25; strong-motion interval coverage is poor (source author's own audit)." },
    { label: "Operational validation against independent ground truth", ok: false, detail: "Not performed (early-warning validation protocol only)." },
  ];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Alerts</h1>
        <p className="mt-1 text-sm text-ink-muted">PRECURSOR AI is a research platform. It does not issue landslide warnings, and no number here is a probability.</p>
      </div>
      <EmptyState icon={BellOff} title="No alerts issued" description="Alerting requires a validated, calibrated model and ground-truth validation. None exists yet, so this list is intentionally empty rather than invented." />
      <Card>
        <CardHeader><CardTitle>Alert readiness (live)</CardTitle></CardHeader>
        <CardContent>
          {loading ? <LoadingState label="Checking readiness" /> : (
            <ul className="space-y-2 text-sm">
              {checks.map((c) => (
                <li key={c.label} className="flex items-start gap-2">
                  {c.ok ? <CheckCircle2 aria-hidden className="mt-0.5 h-4 w-4 text-ok" /> : <XCircle aria-hidden className="mt-0.5 h-4 w-4 text-warn" />}
                  <span><strong>{c.label}</strong>: <span className="text-ink-muted">{c.detail}</span></span>
                </li>
              ))}
            </ul>
          )}
          {disp.error && <p className="mt-2 text-xs text-ink-muted">Displacement bundle unavailable.</p>}
          <p className="mt-3 text-xs text-ink-muted">Research outputs: <Link href="/dashboard/displacement" className="text-accent hover:underline">Displacement forecast</Link> (inferred, not a warning) and <Link href="/dashboard/risk-map" className="text-accent hover:underline">Susceptibility</Link> (no model yet).</p>
        </CardContent>
      </Card>
    </div>
  );
}
