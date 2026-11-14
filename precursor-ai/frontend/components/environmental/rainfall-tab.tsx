"use client";

import { CloudRain } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { AlertBlock, Notice } from "@/components/data/badges";
import { OriginBadge, OriginBanner } from "@/components/environmental/shared";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { IMERG_NOTE, countSeries, mergeRolling, toSeries } from "@/lib/environmental-helpers";
import { getRainfall } from "@/services/environmental";
import type { RainfallPoint } from "@/types/environmental";

const AXIS = { fontSize: 11, fill: "#94a3b8" };
const TIP = { background: "#0f172a", border: "1px solid #334155" };
const LINE_COLORS = ["#38bdf8", "#a78bfa", "#f472b6", "#34d399"];

/** Bars for observed values; missing periods get a distinct amber marker bar. A null value is never drawn as zero. */
function PrecipBars({ title, points }: { title: string; points: RainfallPoint[] }) {
  const series = toSeries(points);
  const { observed, missing } = countSeries(series);
  const top = Math.max(1, ...series.map((p) => p.value ?? 0));
  const data = series.map((p) => ({ date: p.date, mm: p.value, missing: p.missing ? top : null }));
  const summary = `${observed} observed, ${missing} missing. Maximum ${Math.max(0, ...series.map((p) => p.value ?? 0)).toFixed(1)} mm.`;
  return (
    <figure className="space-y-1">
      <figcaption className="text-sm font-medium">{title} <span className="font-normal text-ink-muted">(observed {observed} / missing {missing})</span></figcaption>
      <div className="h-64 w-full" role="img" aria-label={`${title}, accumulated precipitation in mm. ${summary}`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={AXIS} minTickGap={32} />
            <YAxis tick={AXIS} unit=" mm" width={56} />
            <Tooltip contentStyle={TIP} formatter={(v, n) => (n === "Missing (not observed)" ? "no observation" : `${v} mm`)} />
            <Legend />
            <Bar dataKey="mm" name="Accumulated precipitation (mm)" fill="#38bdf8" isAnimationActive={false} />
            <Bar dataKey="missing" name="Missing (not observed)" fill="#f59e0b" fillOpacity={0.35} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-ink-muted">{summary}</p>
    </figure>
  );
}

function RollingChart({ rolling }: { rolling: Record<string, RainfallPoint[]> }) {
  const { keys, rows } = mergeRolling(rolling);
  if (keys.length === 0) return <p className="text-sm text-ink-muted">No rolling totals reported.</p>;
  return (
    <figure className="space-y-1">
      <figcaption className="text-sm font-medium">Rolling accumulated totals <span className="font-normal text-ink-muted">(gaps = window not fully observed)</span></figcaption>
      <div className="h-64 w-full" role="img" aria-label={`Rolling ${keys.join(", ")} accumulated precipitation in mm. Gaps mean the window was not fully observed.`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={AXIS} minTickGap={32} />
            <YAxis tick={AXIS} unit=" mm" width={56} />
            <Tooltip contentStyle={TIP} />
            <Legend />
            {keys.map((k, i) => (
              <Line key={k} dataKey={k} name={`${k} total`} stroke={LINE_COLORS[i % LINE_COLORS.length]} dot={false}
                connectNulls={false} isAnimationActive={false} strokeWidth={1.5} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

export function RainfallTab({ areaId }: { areaId: string }) {
  const r = useApi((s) => getRainfall(areaId, s));
  if (r.isLoading && !r.data) return <LoadingState label="Loading rainfall" />;
  if (r.error) return <ErrorState title="Could not load rainfall" message={r.error.message} onRetry={r.refetch} />;
  const d = r.data;
  if (!d || d.status === "NOT_AVAILABLE" || d.daily.length === 0) {
    return <EmptyState icon={CloudRain} title="No rainfall data" description="No rainfall layer is available for this area. Missing days are never plotted as zero rainfall." />;
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <OriginBadge origin={d.data_origin} />
        <span className="text-ink-muted">Source: {d.source ?? "unknown"}</span>
      </div>
      <OriginBanner origin={d.data_origin} />
      <Notice>{IMERG_NOTE}</Notice>
      <p className="text-sm text-ink-muted">
        {d.quantity} · units {d.units} · period {d.temporal_start?.slice(0, 10) ?? "?"} to {d.temporal_end?.slice(0, 10) ?? "?"} ·
        {" "}<strong className="text-ink">observed {d.observed_days} days / missing {d.missing_days} days</strong>
      </p>
      <AlertBlock title="Notes" items={d.notes} />
      <Card><CardContent><PrecipBars title="Daily precipitation" points={d.daily} /></CardContent></Card>
      <Card><CardContent>
        {d.monthly.length ? <PrecipBars title="Monthly totals (missing if any day is missing)" points={d.monthly} /> : <p className="text-sm text-ink-muted">No monthly totals reported.</p>}
      </CardContent></Card>
      <Card><CardContent><RollingChart rolling={d.rolling} /></CardContent></Card>
    </div>
  );
}
