"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingState } from "@/components/dashboard/loading-state";
import { useApi } from "@/hooks/use-api";
import { DISPLACEMENT_DISCLAIMER, skillPct } from "@/lib/displacement-helpers";
import { getDisplacementMetrics, getDisplacementStatus } from "@/services/displacement";

/** Third "head" on the Predictions page: the real (research) displacement forecast, kept apart from the N/A susceptibility/trigger heads. */
export function DisplacementSummary() {
  const s = useApi((x) => getDisplacementStatus(x));
  const m = useApi((x) => getDisplacementMetrics(x));
  const p = s.data?.provenance;
  const r = s.data?.reproduction;
  const best = m.data ? Math.min(...m.data.benchmark.filter((b) => b.MAE_mm !== null).map((b) => b.MAE_mm as number)) : null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Displacement forecast (12-day LOS increment)</CardTitle>
        <div className="flex gap-1.5"><Badge variant="demo">Research</Badge><Badge>Inferred</Badge><Badge variant="demo">Not a warning</Badge></div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {!p ? (s.isLoading ? <LoadingState label="Loading" /> : <p className="text-ink-muted">Result bundle not found on the server.</p>) : (
          <>
            <p>Issued {p.issue_time.slice(0, 10)} for {p.horizon_days} days ahead, {p.resolution_m} m, frame {p.frame} ({p.orbit.toLowerCase()}). Estimates for {p.pixels_with_estimate} of {p.pixels_total} pixels; the rest are no reliable estimate.</p>
            {best !== null && m.data && <p>Held-out 12-day MAE beats zero-motion by {skillPct(best, m.data.best_naive_mae).toFixed(1)}%, close to a plain ridge regression.</p>}
            {r && <p className="text-xs text-ok">Reproduced here with the saved weights on {r.device.toUpperCase()}: max difference {r.max_abs_diff_mm.toFixed(4)} mm vs the author's map.</p>}
            <p className="text-xs text-ink-muted">{DISPLACEMENT_DISCLAIMER}</p>
            <Link href="/dashboard/displacement" className="text-xs text-accent hover:underline">Open the forecast map and benchmark</Link>
          </>
        )}
      </CardContent>
    </Card>
  );
}
