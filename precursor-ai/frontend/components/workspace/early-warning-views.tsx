import { Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NA_TEXT, RESEARCH_NOTICE, formatProbability } from "@/lib/early-warning";
import {
  MOCK_BADGE_TEXT, MOCK_BANNER_TEXT, mockContributions, mockSusceptibilityGrid, mockTriggerSeries, neutralRamp,
} from "@/lib/mock-predictions";
import type { ExplainResponse, Head, PredictionResponse, UncertaintyReport } from "@/types/prediction";
import { SourceBadge } from "@/components/workspace/source-badge";

// Presentational views only (props in, markup out) so they are testable without a browser. Real and mock views never share a component.

export function ResearchNotice() {
  return <p role="note" className="flex items-start gap-2 text-xs text-ink-muted"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{RESEARCH_NOTICE}</p>;
}

/** Default view while no model exists. No numbers, no map, no chart. */
export function NotAvailableView({ head, message }: { head: Head; message?: string }) {
  return (
    <Card>
      <CardHeader><CardTitle>{head === "susceptibility" ? "Susceptibility" : "Trigger / early warning"}</CardTitle><SourceBadge kind="PLACEHOLDER" /></CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-lg font-semibold" data-testid="na-value">N/A</p>
        <p className="text-ink-muted">{NA_TEXT}.</p>
        {message && <p className="text-xs text-ink-faint">API: {message}</p>}
        <ResearchNotice />
      </CardContent>
    </Card>
  );
}

/** Persistent banner + badge. Rendered by every mock element. */
export function MockBanner() {
  return (
    <div role="alert" data-mock-banner className="flex flex-wrap items-center gap-2 rounded-lg border-2 border-dashed border-ink px-3 py-2 text-sm font-bold uppercase tracking-wider text-ink">
      <Badge variant="neutral" className="border-ink text-ink" data-mock-badge>{MOCK_BADGE_TEXT}</Badge>
      {MOCK_BANNER_TEXT}
    </div>
  );
}

function MockGridSvg({ seed }: { seed: number }) {
  const g = mockSusceptibilityGrid(seed);
  return (
    <svg viewBox={`0 0 ${g.cols} ${g.rows}`} role="img" className="h-64 w-64 rounded border border-line"
      aria-label={`${MOCK_BANNER_TEXT}. Seeded random pattern, unrelated to any location.`}>
      {g.values.map((v, i) => <rect key={i} x={i % g.cols} y={Math.floor(i / g.cols)} width={1.02} height={1.02} fill={neutralRamp(v)} />)}
      <text x={g.cols / 2} y={g.rows / 2} textAnchor="middle" dominantBaseline="middle" fill="white" opacity={0.55} fontSize={2.2} fontWeight="bold" transform={`rotate(-20 ${g.cols / 2} ${g.rows / 2})`}>{MOCK_BANNER_TEXT}</text>
    </svg>
  );
}

function MockTriggerSvg({ seed, day }: { seed: number; day: number }) {
  const s = mockTriggerSeries(seed + day);
  const pts = s.values.map((v, i) => `${(i / (s.values.length - 1)) * 100},${30 - v * 28}`).join(" ");
  return (
    <svg viewBox="0 0 100 32" role="img" className="h-24 w-full rounded border border-line bg-surface-2" aria-label={`${MOCK_BANNER_TEXT}. Seeded random line.`}>
      <polyline points={pts} fill="none" stroke="rgb(203,213,225)" strokeWidth={0.8} />
      <text x={50} y={16} textAnchor="middle" fill="white" opacity={0.4} fontSize={4} fontWeight="bold">{MOCK_BANNER_TEXT}</text>
    </svg>
  );
}

/** Time slider: a plain range input, keyboard operable. */
export function TimeSlider({ id, label, value, max, onChange }: { id: string; label: string; value: number; max: number; onChange: (v: number) => void }) {
  return (
    <label htmlFor={id} className="flex items-center gap-2 text-xs">{label}
      <input id={id} type="range" min={0} max={max} step={1} value={value} onChange={(e) => onChange(Number(e.target.value))} aria-valuetext={`day ${value + 1}`} />
      day {value + 1}
    </label>
  );
}

/** The whole mock early-warning area. Only rendered when the build flag is on AND the API says MODEL_NOT_TRAINED. */
export function MockView({ head, seed, day = 0, onDay }: { head: Head; seed: number; day?: number; onDay?: (d: number) => void }) {
  const contributions = mockContributions(seed);
  return (
    <Card data-view="mock">
      <CardHeader><CardTitle>{head === "susceptibility" ? "Susceptibility layer" : "Trigger forecast view"}</CardTitle><SourceBadge kind="PLACEHOLDER" /></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <MockBanner />
        {head === "susceptibility" ? <MockGridSvg seed={seed} /> : (
          <>
            <MockTriggerSvg seed={seed} day={day} />
            {onDay && <TimeSlider id="mock-day" label="Mock forecast day" value={day} max={13} onChange={onDay} />}
          </>
        )}
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg border border-dashed border-line p-3"><p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Uncertainty ({MOCK_BADGE_TEXT})</p>
            <p className="text-xs text-ink-muted">Mock placeholder only. A real method and a real model are required before any interval exists.</p></div>
          <div className="rounded-lg border border-dashed border-line p-3"><p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">Explanation ({MOCK_BADGE_TEXT})</p>
            <ul className="text-xs text-ink-muted">{contributions.map((c) => <li key={c.feature}>{c.feature}: {c.contribution.toFixed(2)}</li>)}</ul></div>
        </div>
        <p className="text-xs text-ink-muted">Not exportable. Not derived from any real input. Calibration: none (this is a layout test).</p>
        <ResearchNotice />
      </CardContent>
    </Card>
  );
}

/** Real-response view: renders a registered model's output. Built and tested with TEST_FIXTURE responses; activates when the API answers OK. */
export function RealView({ response, explain, uncertainty, modelCardPath }: {
  response: PredictionResponse; explain: ExplainResponse | null; uncertainty: UncertaintyReport | null; modelCardPath: string | null;
}) {
  const o = response.output;
  if (!o) return <NotAvailableView head={response.head} message={response.message} />;
  return (
    <Card data-view="real">
      <CardHeader><CardTitle>{o.head === "susceptibility" ? "Susceptibility" : "Trigger / early warning"}: {o.model_id} {o.model_version}</CardTitle><SourceBadge kind="MODEL_PREDICTION" /></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div>
          <p className="text-2xl font-semibold" data-testid="real-probability">{formatProbability(o.probability)}</p>
          <p className="text-xs text-ink-muted">Model output ({o.risk_class ? `class: ${o.risk_class}` : "no class assigned"}){o.horizon_days ? `, horizon ${o.horizon_days} d` : ""}</p>
        </div>
        <p className="text-xs text-ink-muted" data-testid="calibration">
          {o.calibration.calibrated ? `Calibrated (${o.calibration.method ?? "method not stated"}).` : "NOT calibrated: do not read this number as a probability of occurrence."}
        </p>
        <p className="text-xs text-ink-muted">Valid time: {o.valid_time.start}{o.valid_time.end ? ` to ${o.valid_time.end}` : " onward"}. Valid region: {JSON.stringify(o.valid_region)}.</p>
        <p className="text-xs text-ink-muted">Uncertainty: {o.uncertainty ? JSON.stringify(o.uncertainty) : "not provided by the model"}. Data-quality items: {uncertainty ? uncertainty.items.length : "not loaded"}.</p>
        {explain?.status === "OK" && explain.explanation ? (
          <ul className="text-xs" aria-label="Feature contributions">{explain.explanation.contributions.map((c) => <li key={c.feature}>{c.feature}: {c.contribution}</li>)}
            <li className="text-ink-muted">{explain.explanation.caveats.join(" ")}</li></ul>
        ) : <p className="text-xs text-ink-muted">Explanation: not available for this model.</p>}
        <p className="text-xs text-ink-muted">Model card: {modelCardPath ?? "not provided"}</p>
        <ResearchNotice />
      </CardContent>
    </Card>
  );
}
