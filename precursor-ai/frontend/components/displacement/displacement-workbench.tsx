"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import {
  DISPLACEMENT_DISCLAIMER, cellAt, colorLimit, divergingColor, fmtMm, skillPct, smoothGrid, sortByMae,
} from "@/lib/displacement-helpers";
import {
  displacementDocUrl, displacementImageUrl, getDisplacementForecast, getDisplacementMetrics, getDisplacementStatus,
} from "@/services/displacement";
import type { ForecastGrid } from "@/types/displacement";

type Band = "q10_mm" | "q50_mm" | "q90_mm";
const CELL = 4; // canvas pixels per grid cell
const FIGURES: [string, string][] = [
  ["forecast_map", "Latest 12-day forecast (author's figure)"], ["heldout_poi", "Held-out forecast at the point of interest"],
  ["verification_skill_map", "Per-pixel skill vs zero-motion"], ["verification_coverage", "Interval coverage"],
  ["verification_timeseries", "Most active pixel: forecast vs observed"], ["opera_overview", "OPERA overview"],
  ["nisar_observation", "NISAR observation layer (never a model input)"],
];
const DOCS: [string, string][] = [
  ["limitations_v2", "Limitations (v2)"], ["limitations_v3", "Limitations (v3)"], ["final_comparison_v3", "What improved / failed (v3)"],
];

function Heatmap({ grid }: { grid: ForecastGrid }) {
  const [band, setBand] = useState<Band>("q50_mm");
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null);
  const ref = useRef<HTMLCanvasElement>(null);
  const [smooth, setSmooth] = useState(true);
  const shown = useMemo(() => (smooth ? smoothGrid(grid.bands[band]) : grid.bands[band]), [grid, band, smooth]);
  const limit = colorLimit(smooth ? smoothGrid(grid.bands.q50_mm) : grid.bands.q50_mm);

  useEffect(() => {
    const cv = ref.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;
    const img = ctx.createImageData(grid.width * CELL, grid.height * CELL);
    const g = shown;
    for (let r = 0; r < grid.height; r++)
      for (let c = 0; c < grid.width; c++) {
        const col = divergingColor(g[r][c], limit);
        for (let dy = 0; dy < CELL; dy++)
          for (let dx = 0; dx < CELL; dx++) img.data.set(col, (((r * CELL + dy) * grid.width * CELL) + c * CELL + dx) * 4);
      }
    ctx.putImageData(img, 0, 0);
  }, [grid, shown, limit]);

  const onMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const b = e.currentTarget.getBoundingClientRect();
    const cell = cellAt(e.clientX - b.left, e.clientY - b.top, b.width, b.height, grid.width, grid.height);
    setHover(cell ? { r: cell[0], c: cell[1] } : null);
  };
  const h = hover;
  const lon = h ? grid.bounds.west + ((h.c + 0.5) / grid.width) * (grid.bounds.east - grid.bounds.west) : null;
  const lat = h ? grid.bounds.north - ((h.r + 0.5) / grid.height) * (grid.bounds.north - grid.bounds.south) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>12-day LOS increment forecast, issued {grid.issue_time.slice(0, 10)}</CardTitle>
        <label className="flex items-center gap-1 text-xs text-ink-muted"><input type="checkbox" checked={smooth} onChange={(e) => setSmooth(e.target.checked)} />Smooth (display only)</label>
        <div className="flex gap-1" role="group" aria-label="Quantile">
          {(["q10_mm", "q50_mm", "q90_mm"] as Band[]).map((b) => (
            <button key={b} type="button" onClick={() => setBand(b)} aria-pressed={band === b}
              className={`rounded-md border px-2 py-1 text-xs ${band === b ? "border-accent text-accent" : "border-line text-ink-muted"}`}>
              {b.slice(0, 3)}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="relative inline-block max-w-full overflow-hidden rounded-lg border border-line bg-surface-2">
          <canvas ref={ref} width={grid.width * CELL} height={grid.height * CELL} onMouseMove={onMove} onMouseLeave={() => setHover(null)}
            role="img" aria-label="Forecast heatmap; transparent cells have no reliable estimate" className="block h-auto max-w-full cursor-crosshair" />
        </div>
        <p className="text-xs text-ink-muted" aria-live="polite">
          {h && lat !== null && lon !== null
            ? `${lat.toFixed(4)}N ${lon.toFixed(4)}E: q10 ${fmtMm(grid.bands.q10_mm[h.r][h.c])}, q50 ${fmtMm(grid.bands.q50_mm[h.r][h.c])}, q90 ${fmtMm(grid.bands.q90_mm[h.r][h.c])}`
            : "Hover a cell. Transparent = no reliable estimate."}
        </p>
        <p className="text-xs text-ink-muted">
          Red = toward the satellite, blue = away (colour limit +/-{limit.toFixed(1)} mm). {(grid.no_estimate_share * 100).toFixed(0)}% of cells have no reliable estimate.
          Median error is about the noise level of OPERA itself; see the benchmark and limitations below.
        </p>
      </CardContent>
    </Card>
  );
}

function DocViewer() {
  const [name, setName] = useState<string | null>(null);
  const [text, setText] = useState("");
  useEffect(() => {
    if (!name) return;
    const c = new AbortController();
    fetch(displacementDocUrl(name), { signal: c.signal }).then((r) => r.text()).then(setText).catch(() => setText("Could not load document."));
    return () => c.abort();
  }, [name]);
  return (
    <Card>
      <CardHeader><CardTitle>Limitations and findings</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {DOCS.map(([k, l]) => (
            <button key={k} type="button" onClick={() => setName(k)} aria-pressed={name === k}
              className={`rounded-md border px-2 py-1 text-xs ${name === k ? "border-accent text-accent" : "border-line text-ink-muted"}`}>{l}</button>
          ))}
        </div>
        {name ? <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-xs">{text}</pre>
          : <p className="text-xs text-ink-muted">Select a document. These are the repository author's own notes, including what failed.</p>}
      </CardContent>
    </Card>
  );
}

export function DisplacementWorkbench() {
  const status = useApi((s) => getDisplacementStatus(s));
  const metrics = useApi((s) => getDisplacementMetrics(s));
  const forecast = useApi((s) => getDisplacementForecast(s));
  const p = status.data?.provenance;
  const rows = metrics.data ? sortByMae(metrics.data.benchmark) : [];
  const naive = metrics.data?.best_naive_mae ?? 0;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold">Displacement forecast (InSAR time series)</h1>
        <div className="flex flex-wrap gap-2"><Badge variant="demo">Research</Badge><Badge variant="neutral">Inferred</Badge><Badge variant="demo">Not a warning</Badge></div>
        <p role="note" className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-sm text-warn">{DISPLACEMENT_DISCLAIMER}</p>
        <p className="text-xs text-ink-muted">
          Model, training and benchmark metrics come from a third-party research bundle (Farid145678/NASA_SPACE_APPS) ported into ai_engine/time_series;
          the training and metrics were not re-run here. The susceptibility track (static map) is separate and unaffected.
        </p>
      </div>

      {status.error ? <ErrorState title="Could not load status" message={status.error.message} onRetry={status.refetch} /> :
        !p ? (status.isLoading ? <LoadingState label="Loading status" /> : <p className="text-sm text-ink-muted">Result bundle not found on the server.</p>) : (
          <Card><CardContent>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
              <div><dt className="text-ink-muted">Model</dt><dd>{p.model}</dd></div>
              <div><dt className="text-ink-muted">Training data</dt><dd>{p.training_data}</dd></div>
              <div><dt className="text-ink-muted">Frame / orbit</dt><dd>{p.frame} / {p.orbit} (track {p.track})</dd></div>
              <div><dt className="text-ink-muted">Resolution</dt><dd>{p.resolution_m} m</dd></div>
              <div><dt className="text-ink-muted">Horizon</dt><dd>{p.horizon_days} days</dd></div>
              <div><dt className="text-ink-muted">Train period</dt><dd>{p.train_period[0]} to {p.train_period[1]}</dd></div>
              <div><dt className="text-ink-muted">Test period</dt><dd>{p.test_period[0]} to {p.test_period[1]}</dd></div>
              <div><dt className="text-ink-muted">Pixels with estimate</dt><dd>{p.pixels_with_estimate} / {p.pixels_total}</dd></div>
            </dl>
            {status.data?.reproduction && (
              <p className="mt-2 text-xs text-ok" role="note">
                Forecast reproduced here with the saved weights (no retraining, {status.data.reproduction.device.toUpperCase()}): {status.data.reproduction.pixels_compared} pixels,
                same no-estimate pattern: {String(status.data.reproduction.nan_pattern_equal)}, max difference {status.data.reproduction.max_abs_diff_mm.toFixed(4)} mm vs the author's map.
              </p>
            )}
            {typeof status.data?.reproduction?.corr_forecast_vs_last_observed_increment === "number" && (
              <p className="mt-2 text-xs text-warn" role="note">
                Read the map with care: the forecast correlates {status.data.reproduction.corr_forecast_vs_last_observed_increment.toFixed(2)} with the last observed 12-day change, i.e. it mostly
                predicts that the last change reverses (measurement-noise reversal, as the source author also found). The broad red/blue pattern is not predicted slope movement.
              </p>
            )}
            <p className="mt-2 text-xs text-ink-muted">NISAR ({p.nisar_observation.maturity}) is shown only as an observation; used for training: {String(p.nisar_observation.used_for_training)}.</p>
          </CardContent></Card>
        )}

      {forecast.error ? <ErrorState title="Could not load forecast" message={forecast.error.message} onRetry={forecast.refetch} /> :
        forecast.data ? <Heatmap grid={forecast.data} /> : <LoadingState label="Loading forecast grid" />}

      <Card>
        <CardHeader><CardTitle>Held-out benchmark (test 2024 to 2026, one site)</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {metrics.error ? <ErrorState title="Could not load metrics" message={metrics.error.message} onRetry={metrics.refetch} /> :
            !metrics.data ? <LoadingState label="Loading metrics" /> : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="text-ink-muted"><tr><th className="py-1 pr-3">Experiment</th><th className="pr-3">Model</th><th className="pr-3">MAE (mm)</th><th className="pr-3">Skill vs zero-motion</th><th className="pr-3">80% coverage</th></tr></thead>
                    <tbody>{rows.map((r) => (
                      <tr key={`${r.experiment}-${r.model}`} className="border-t border-line">
                        <td className="py-1 pr-3">{r.experiment}</td><td className="pr-3">{r.model}</td>
                        <td className="pr-3">{(r.MAE_mm as number).toFixed(3)}</td>
                        <td className="pr-3">{skillPct(r.MAE_mm as number, naive).toFixed(1)}%</td>
                        <td className="pr-3">{r.cov80 === null || Number.isNaN(r.cov80) ? "n/a" : (r.cov80 * 100).toFixed(0) + "%"}</td>
                      </tr>))}</tbody>
                  </table>
                </div>
                <ul className="list-disc space-y-1 pl-5 text-xs text-ink-muted">
                  <li>Best deep model beats zero-motion by about {skillPct(rows[0]?.MAE_mm ?? naive, naive).toFixed(0)}%, but a plain ridge regression is close: the gain over a linear model is small.</li>
                  <li>Stable ground: zero-motion MAE {metrics.data.verification.noise_floor.zero_motion_MAE_stable_mm.toFixed(2)} mm vs model {metrics.data.verification.noise_floor.primary_MAE_stable_mm.toFixed(2)} mm. Most of a 12-day increment is measurement noise.</li>
                  <li>The landslide core is largely unmeasurable by OPERA in 2024-25 (masked), so fast motion is not validated. Interval coverage for strong motion is poor.</li>
                  <li>One site, one geometry, the test period was inspected repeatedly: every number is exploratory.</li>
                </ul>
              </>
            )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Figures</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          {FIGURES.map(([k, cap]) => (
            <figure key={k} className="space-y-1">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={displacementImageUrl(k)} alt={cap} loading="lazy" className="w-full rounded-lg border border-line bg-white" />
              <figcaption className="text-xs text-ink-muted">{cap}</figcaption>
            </figure>
          ))}
        </CardContent>
      </Card>

      <DocViewer />
    </div>
  );
}
