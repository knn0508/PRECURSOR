"use client";

import { useEffect, useRef, useState } from "react";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { colorLimit, divergingColor, smoothGrid } from "@/lib/displacement-helpers";
import { getAreaBacktest, getBacktestGrids } from "@/services/displacement";
import type { BacktestDate, BacktestMetrics } from "@/types/displacement";

const CELL = 3;
type Grid = (number | null)[][];

function GridMap({ grid, limit, title, note }: { grid: Grid; limit: number; title: string; note: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const h = grid.length, w = grid[0]?.length ?? 0;
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(w * CELL, h * CELL);
    for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) {
      const col = divergingColor(grid[r][c], limit);
      for (let dy = 0; dy < CELL; dy++) for (let dx = 0; dx < CELL; dx++) img.data.set(col, ((r * CELL + dy) * w * CELL + c * CELL + dx) * 4);
    }
    ctx.putImageData(img, 0, 0);
  }, [grid, limit, h, w]);
  return (
    <figure className="space-y-1">
      <figcaption className="text-xs font-medium">{title}</figcaption>
      <canvas ref={ref} width={w * CELL} height={h * CELL} role="img" aria-label={`${title}; transparent cells have no value`} className="h-auto w-full rounded-lg border border-line bg-surface-2" />
      <p className="text-[11px] text-ink-muted">{note}</p>
    </figure>
  );
}

const f2 = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "n/a" : v.toFixed(d));

function Row({ label, m }: { label: string; m: BacktestMetrics | BacktestDate }) {
  return (
    <tr className="border-t border-line">
      <td className="py-1 pr-3">{label}</td><td className="pr-3">{m.n_pixels}</td><td className="pr-3">{f2(m.MAE_model_mm)}</td><td className="pr-3">{f2(m.MAE_zero_mm)}</td>
      <td className="pr-3">{f2(m.MAE_ridge_mm)}</td><td className="pr-3">{f2(m.skill_vs_zero_pct, 1)}%</td><td className="pr-3">{f2(m.skill_vs_ridge_pct, 1)}%</td>
      <td className="pr-3">{(m.cov80 * 100).toFixed(0)}%</td><td className="pr-3">{f2(m.corr_forecast_vs_last_change)}</td><td>{f2(m.corr_forecast_vs_actual)}</td>
    </tr>
  );
}

function Result({ issues }: { issues: string[] }) {
  const [issue, setIssue] = useState(issues[0]);
  const [smooth, setSmooth] = useState(false);
  const g = useApi((s) => getBacktestGrids(issue, s));
  const d = g.data;
  const mk = (x: Grid) => (smooth ? smoothGrid(x) : x);
  const lim = d ? colorLimit(d.actual_mm.map((r, i) => r.map((v, j) => v ?? d.forecast.q50_mm[i][j]))) : 1;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-ink-muted">Issue date D:</span>
        {issues.map((i) => (
          <button key={i} type="button" aria-pressed={issue === i} onClick={() => setIssue(i)}
            className={`rounded-md border px-2 py-1 ${issue === i ? "border-accent text-accent" : "border-line text-ink-muted"}`}>{i}</button>
        ))}
        <label className="ml-auto flex items-center gap-1 text-ink-muted"><input type="checkbox" checked={smooth} onChange={(e) => setSmooth(e.target.checked)} />Smooth (display only)</label>
      </div>
      {g.error ? <ErrorState title="Could not load maps" message={g.error.message} onRetry={g.refetch} /> : !d ? <LoadingState label="Loading maps" /> : (
        <>
          <p className="text-xs text-ink-muted">Forecast issued {d.issue} for {d.target} (12 days) using only data up to {d.issue}. Colour limit +/-{lim.toFixed(1)} mm, red toward the satellite, blue away, transparent = no value.</p>
          <div className="grid gap-3 md:grid-cols-3">
            <GridMap grid={mk(d.forecast.q50_mm)} limit={lim} title={`Forecast (q50), made ${d.issue}`} note="What the model predicted." />
            <GridMap grid={mk(d.actual_mm)} limit={lim} title={`Observed (OPERA), ${d.issue} to ${d.target}`} note="Measured increment. Transparent = masked or missing, not zero." />
            <GridMap grid={mk(d.difference_mm)} limit={lim} title="Forecast minus observed" note="Only where both exist." />
          </div>
          <p className="text-xs text-ink-muted">This date: model MAE {f2(d.metrics.MAE_model_mm)} mm, zero-motion {f2(d.metrics.MAE_zero_mm)} mm; an observation exists on {d.metrics.actual_available_pct.toFixed(0)}% of pixels.</p>
        </>
      )}
    </div>
  );
}

export function BacktestPanel({ areaId }: { areaId: string }) {
  const r = useApi((s) => getAreaBacktest(areaId, s));
  if (r.isLoading && !r.data) return <LoadingState label="Checking coverage" />;
  if (r.error) return <ErrorState title="Could not load the backtest" message={r.error.message} onRetry={r.refetch} />;
  const a = r.data;
  if (!a) return null;
  if (!a.covered || !a.result) {
    return (
      <Card><CardContent className="space-y-1 text-sm">
        <p className="font-medium">No forecast or backtest for {a.area_name}</p>
        <p className="text-xs text-ink-muted">{a.reason ?? "This area is not covered by the OPERA frame data, so nothing is shown."}</p>
      </CardContent></Card>
    );
  }
  const b = a.result;
  const p = b.pooled;
  const ridgeCi = p.MAE_diff_model_minus_ridge_ci95_mm;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Forecast vs reality: {a.area_name}</CardTitle>
        <div className="flex gap-1.5"><Badge variant="demo">Research</Badge><Badge>Inferred</Badge><Badge variant="demo">Not a warning</Badge></div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p role="note" className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
          Backtest, exploratory. Period: {b.test_period}. Newest OPERA data available: {b.latest_data_date}. {b.held_out_note}
        </p>
        <p className="text-xs text-ink-muted">Area covered by the data footprint: {a.area_covered_pct.toFixed(0)}%. {b.scoring}</p>
        <Result issues={b.issue_dates} />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-ink-muted"><tr><th className="py-1 pr-3">Issue D</th><th className="pr-3">Pixels</th><th className="pr-3">MAE model</th><th className="pr-3">MAE zero</th><th className="pr-3">MAE ridge</th>
              <th className="pr-3">vs zero</th><th className="pr-3">vs ridge</th><th className="pr-3">80% cov.</th><th className="pr-3">r(fc, last change)</th><th>r(fc, actual)</th></tr></thead>
            <tbody>{b.per_date.map((m) => <Row key={m.issue} label={m.issue} m={m} />)}<Row label="All dates" m={p} /></tbody>
          </table>
        </div>
        <ul className="list-disc space-y-1 pl-5 text-xs text-ink-muted">
          <li>Versus zero-motion: {f2(p.skill_vs_zero_pct, 1)}% lower MAE (95% CI of the MAE difference {f2(p.MAE_diff_model_minus_zero_ci95_mm?.[0])} to {f2(p.MAE_diff_model_minus_zero_ci95_mm?.[1])} mm).</li>
          <li>Versus a plain ridge regression: {f2(p.skill_vs_ridge_pct, 1)}% (CI {f2(ridgeCi?.[0])} to {f2(ridgeCi?.[1])} mm){ridgeCi && ridgeCi[0] < 0 && ridgeCi[1] > 0 ? ": no detectable advantage." : "."}</li>
          <li>80% intervals contain the observation {(p.cov80 * 100).toFixed(0)}% of the time (target 80%).</li>
          <li>The forecast correlates {f2(p.corr_forecast_vs_last_change)} with the last observed change, and the observed change itself correlates {f2(p.corr_actual_vs_last_change)} with the last one: the model mostly predicts noise reversal, not slope motion.</li>
          <li>{b.ci_note} {b.no_leakage}</li>
        </ul>
      </CardContent>
    </Card>
  );
}
