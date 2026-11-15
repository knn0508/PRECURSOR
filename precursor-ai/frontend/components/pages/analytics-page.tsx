"use client";

import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { skillPct, sortByMae } from "@/lib/displacement-helpers";
import { getDisplacementMetrics } from "@/services/displacement";

export function AnalyticsPage() {
  const m = useApi((s) => getDisplacementMetrics(s));
  const rows = m.data ? sortByMae(m.data.benchmark) : [];
  const naive = m.data?.best_naive_mae ?? 0;
  const mae = rows.map((r) => ({ name: `${r.experiment} ${r.model}`, MAE: Number((r.MAE_mm as number).toFixed(3)) }));
  const cov = rows.filter((r) => r.cov80 !== null && !Number.isNaN(r.cov80)).map((r) => ({ name: `${r.experiment} ${r.model}`, coverage: Math.round((r.cov80 as number) * 100) }));
  const v = m.data?.verification;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold">Analytics</h1>
        <div className="flex gap-2"><Badge variant="demo">Research</Badge><Badge>Third-party results, not re-run here</Badge></div>
        <p className="text-sm text-ink-muted">Held-out diagnostics of the displacement forecast (one site, test 2024 to 2026). Per-area time series analysis lives under <Link href="/dashboard/workspace" className="text-accent hover:underline">Workspace</Link>; the forecast map is on <Link href="/dashboard/displacement" className="text-accent hover:underline">Displacement Forecast</Link>.</p>
      </div>
      {m.error ? <ErrorState title="Could not load diagnostics" message={m.error.message} onRetry={m.refetch} /> :
        !m.data || !v ? <LoadingState label="Loading diagnostics" /> : (
          <>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader><CardTitle>12-day MAE by model (mm, lower is better)</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-72" role="img" aria-label="Bar chart of mean absolute error per model">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={mae} layout="vertical" margin={{ left: 40 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" domain={[2, "auto"]} /><YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11 }} />
                        <Tooltip /><ReferenceLine x={naive} stroke="#d97706" strokeDasharray="4 4" label={{ value: "zero-motion", fontSize: 10 }} />
                        <Bar dataKey="MAE" fill="#4f8cff" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>80% interval coverage (%, target 80)</CardTitle></CardHeader>
                <CardContent>
                  <div className="h-72" role="img" aria-label="Bar chart of interval coverage per model">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={cov} layout="vertical" margin={{ left: 40 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis type="number" domain={[0, 100]} /><YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11 }} />
                        <Tooltip /><ReferenceLine x={80} stroke="#16a34a" strokeDasharray="4 4" />
                        <Bar dataKey="coverage" fill="#8b5cf6" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </CardContent>
              </Card>
            </div>
            <Card>
              <CardHeader><CardTitle>Reading the numbers</CardTitle></CardHeader>
              <CardContent>
                <ul className="list-disc space-y-1 pl-5 text-sm text-ink-muted">
                  <li>Best model ({rows[0]?.model}) improves on zero-motion by {skillPct(rows[0]?.MAE_mm ?? naive, naive).toFixed(1)}%.</li>
                  <li>Stable ground ({(v.noise_floor.share_of_test_samples_stable * 100).toFixed(0)}% of test samples): zero-motion MAE {v.noise_floor.zero_motion_MAE_stable_mm.toFixed(2)} mm, model {v.noise_floor.primary_MAE_stable_mm.toFixed(2)} mm.</li>
                  <li>Model beats zero-motion on {(v.per_pixel.share_pixels_model_better * 100).toFixed(0)}% of {v.per_pixel.n_pixels} pixels; median pixel skill {v.per_pixel.median_pixel_skill_pct.toFixed(1)}%.</li>
                  <li>Published landslide rates (14.5 to 43.5 mm/day) are far above the maximum measured OPERA LOS rate ({Number(v.ground_truth_coverage.max_measured_LOS_rate_JunNov2024_mm_day).toFixed(1)} mm/day): fast motion is not captured or validated.</li>
                </ul>
              </CardContent>
            </Card>
          </>
        )}
    </div>
  );
}
